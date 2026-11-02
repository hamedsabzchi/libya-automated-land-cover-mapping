"""Saved accuracy only: sockets, credentials, launch and display backends forbidden."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from libya_landcover.accuracy import render_accuracy
from libya_landcover.chat_language import GuidedParser, intent
from libya_landcover.job_store import JobStore
from libya_landcover.local_language import LocalParser
from libya_landcover.map_assistant import MapAssistant
from libya_landcover.map_view import tile_spec
from libya_landcover.pilot import create_pilot, save_handoff
from libya_landcover.workspace import save_workspace, restore_workspace
from test_jobs import bundle_files


class AccuracyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for target in ('socket.socket.connect', 'google.auth.default'):
            guard = patch(target, side_effect=AssertionError('Offline accuracy test'))
            guard.start(); self.addCleanup(guard.stop)
        self.generate = Mock(side_effect=AssertionError('No inference needed'))
        self.live = Mock(side_effect=AssertionError('No Earth Engine call'))
        self.a = MapAssistant(JobStore(self.root/'store'), engine_commit='a'*40,
                              parser=LocalParser(self.generate), launcher=self.live, before_live=self.live, viewer=Mock())
        self.files = bundle_files()
        self.result = json.loads(self.files['result.json'])
        matrix = [[0]*12 for _ in range(12)]
        matrix[0][0], matrix[0][1], matrix[1][0], matrix[1][1] = 8, 2, 1, 9
        self.result['metrics'] = {'overall': .85, 'kappa': .7, 'producer': [.8,.9]+[None]*10,
                                  'confusion': matrix, 'sampled_validation_count': 20}
        self.files['result.json'] = json.dumps(self.result).encode()
        self.archive = self.root/'input.zip'
        with zipfile.ZipFile(self.archive, 'w') as z:
            for name, data in self.files.items(): z.writestr('run/'+name, data)
        self.mapping = self.a.import_archive(self.archive)
        self.mid = self.a.selected

    def export(self):
        job = create_pilot(self.a.store, self.mid, self.mapping['outputs'][0]['artifact_id'],
                           {'spec': tile_spec(36864, -339968)})
        job = self.a.store.update(job, state='completed', destination_uris=['https://drive.google.com/drive/folders/test'])
        self.a.selected = job['job_id']
        return job

    def test_saved_values_and_percentages_no_reevaluation(self):
        report = self.a.say('classification accuracy')
        self.assertEqual(report['metrics'], self.result['metrics'])
        self.assertEqual(report['classes'][0]['producer_percent'], 80)
        self.assertAlmostEqual(report['classes'][0]['user_percent'], 8/9*100)
        self.assertIsNone(report['classes'][2]['producer_percent'])
        self.assertIsNone(report['classes'][2]['user_percent'])
        html = render_accuracy(report)
        for text in ('85.00%', '0.7000', '88.89%', 'Confusion matrix', 'Not available', self.mid):
            self.assertIn(text, html)
        self.assertNotIn('70.00%', html)  # Kappa is not a percentage.
        self.assertEqual(len(report['classes']), 12)
        self.live.assert_not_called(); self.generate.assert_not_called()

    def test_read_preserves_selected_export_tile_draft_and_records(self):
        job = self.export()
        self.a.choose_tile(job['inputs']['spec'], self.mid)
        self.a._draft({'action':'pilot','mapping_job_id':self.mid,'artifact_id':job['inputs']['artifact_id'],
                       'plan':{'spec':job['inputs']['spec']}})
        before = deepcopy((self.a.selected, self.a.tile, self.a.pending, self.a.store.list()))
        for text in ('Model accuracy', 'What is the classification accuracy?', 'Show confusion matrix',
                     'accuracy by class', 'Kappa', 'producer accuracy', '/accuracy '+self.mid):
            self.assertEqual(self.a.say(text)['mapping_job_id'], self.mid)
        self.assertEqual(before, (self.a.selected, self.a.tile, self.a.pending, self.a.store.list()))
        self.generate.assert_not_called(); self.live.assert_not_called()

    def test_generated_accuracy_intent_is_read_only_too(self):
        self.a.prepare_mapping({'target_year':2023}); draft = self.a.pending
        self.a.parser = LocalParser(lambda _:json.dumps(intent('accuracy')))
        self.assertEqual(self.a.say('How well did the classifier perform?')['metrics'], self.result['metrics'])
        self.assertEqual(self.a.pending, draft)
        self.assertEqual(self.a.store.get(draft)['state'], 'prepared')

    def test_guided_and_local_parsers_support_accuracy_without_weights(self):
        for parser in (GuidedParser(), LocalParser(self.generate)):
            for text in ('classification accuracy', 'What is the model accuracy?', 'show confusion matrix'):
                self.assertEqual(parser.parse(text,{})['action'], 'accuracy')
        self.assertEqual(GuidedParser().parse('area under each class',{})['action'], 'help')
        self.generate.assert_not_called()

    def test_no_selection_pending_failed_and_bad_bundle_never_invent_metrics(self):
        self.a.selected = None
        self.assertNotIn('metrics', self.a.accuracy())
        for state in ('queued','running','failed'):
            job = self.a.store.create('mapping', state, {}, state=state)
            self.assertNotIn('metrics', self.a.accuracy(job['job_id']))
        self.a.selected = self.mid
        (self.a.store.folder(self.mid)/'bundle/result.json').write_text('{}')
        report = self.a.accuracy()
        self.assertEqual(report['state'], 'unavailable')
        self.assertNotIn('metrics', report)
        self.live.assert_not_called()

    def test_legacy_pilot_snapshot_and_all_work_backup_keep_accuracy(self):
        job = self.export()
        handoff = self.root/'pilot.zip'
        save_handoff(self.a.store, job['job_id'], {'spec':job['inputs']['spec']}, handoff, service_commit='a'*40)
        other = MapAssistant(JobStore(self.root/'other'), engine_commit='a'*40, before_live=self.live)
        other.import_archive(handoff)
        self.assertEqual(other.store.get(other.selected)['kind'], 'assistant_snapshot')
        self.assertEqual(other.say('accuracy')['metrics'], self.result['metrics'])
        saved = save_workspace(other, self.root/'all.zip')
        fresh = MapAssistant(JobStore(self.root/'fresh'), engine_commit='a'*40, before_live=self.live)
        restore_workspace(fresh, saved)
        self.assertEqual(fresh.say('accuracy')['metrics'], self.result['metrics'])
        self.live.assert_not_called()

    def test_null_and_zero_are_not_confused_and_html_is_escaped(self):
        report = self.a.accuracy()
        report['metrics']['overall'] = 0; report['metrics']['kappa'] = None
        report['message'] = '<script>unsafe</script>'
        html = render_accuracy(report)
        self.assertIn('0.00%', html); self.assertIn('Not available', html)
        self.assertNotIn('<script>', html)

    def test_chat_button_and_typed_query_do_not_open_map_or_poll(self):
        from libya_landcover.map_ui import MapUI
        ui = MapUI(self.a, connect=Mock(), auto_poll=False); self.addCleanup(ui.close)
        self.export(); ui.sync()
        original = (self.a.selected, tuple(ui.map.layers), ui.map)
        with patch.object(ui, '_ensure_map', self.live), patch.object(ui, '_checkpoint', self.live), \
             patch('libya_landcover.map_ui.poll_export', self.live):
            ui.accuracy_button.click()
            ui.message.value = 'What is the classification accuracy?'; ui.send.click()
        self.assertIn('85.00%', ui.transcript.value)
        self.assertIn(ui.chat, ui.widget.children)
        self.assertEqual(type(ui.chat).__name__, 'VBox')
        self.assertEqual(original, (self.a.selected, tuple(ui.map.layers), ui.map))
        self.a.viewer.open.assert_not_called(); self.live.assert_not_called()

    def test_in_place_chat_upgrade_keeps_every_map_object_and_choice(self):
        from libya_landcover.map_ui import MapUI
        from libya_landcover.accuracy_chat import upgrade_accuracy_chat
        ui = MapUI(self.a, connect=Mock(), auto_poll=False); self.addCleanup(ui.close)
        job = self.export(); self.a.choose_tile(job['inputs']['spec'], self.mid)
        self.a._draft({'action':'pilot','mapping_job_id':self.mid,'artifact_id':job['inputs']['artifact_id'],
                       'plan':{'spec':job['inputs']['spec']}})
        snapshot = deepcopy((self.a.selected, self.a.tile, self.a.pending, self.a.store.list()))
        widgets = (ui.map, ui.map_slot, ui.downloads, ui.tile_action, ui.grid, ui.highlight, ui.widget)
        guard = self.a.before_live; generator = self.a.parser._generate
        upgrade_accuracy_chat(ui)
        self.assertEqual(widgets, (ui.map, ui.map_slot, ui.downloads, ui.tile_action, ui.grid, ui.highlight, ui.widget))
        self.assertEqual(snapshot, (self.a.selected, self.a.tile, self.a.pending, self.a.store.list()))
        self.assertIs(self.a.before_live, guard); self.assertIs(self.a.parser._generate, generator)
        ui.accuracy_button.click(); self.assertIn('85.00%', ui.transcript.value)
        self.a.viewer.open.assert_not_called(); self.live.assert_not_called()


if __name__ == '__main__': unittest.main()
