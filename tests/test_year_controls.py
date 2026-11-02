"""Existing engine year options reach requests; selecting them never runs work."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile
from libya_landcover.assistant import Assistant
from libya_landcover.chat_language import GuidedParser, intent, validate_intent
from libya_landcover.local_language import LocalParser
from libya_landcover.job_store import JobStore
from libya_landcover.map_assistant import MapAssistant
from libya_landcover.map_ui import MapUI
from libya_landcover.map_view import tile_spec
from libya_landcover.pilot import create_pilot
from test_jobs import bundle_files


class YearControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for target in ('socket.socket.connect','google.auth.default'):
            guard=patch(target,side_effect=AssertionError('Offline only'));guard.start();self.addCleanup(guard.stop)
        self.launcher=Mock(return_value=1);self.generator=Mock(side_effect=AssertionError('No inference for explicit edits'))
        self.a=MapAssistant(JobStore(self.root/'store'),engine_commit='a'*40,launcher=self.launcher,parser=LocalParser(self.generator),viewer=Mock())
        archive=self.root/'previous.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name,data in bundle_files().items():z.writestr('run/'+name,data)
        self.mapping=self.a.import_archive(archive);self.mid=self.a.selected
        self.ui=MapUI(self.a,connect=Mock(),auto_poll=False);self.addCleanup(self.ui.close)
        self.ui.live_ready=True;self.ui.sync()
        self.a.before_live=Mock()

    def test_controls_remain_visible_after_completed_map_and_export(self):
        self.assertEqual(self.ui.choices.layout.display,'')
        job=create_pilot(self.a.store,self.mid,self.mapping['outputs'][0]['artifact_id'],{'spec':tile_spec(36864,-339968)})
        job=self.a.store.update(job,state='completed',destination_uris=['https://drive.google.com/drive/folders/retained'])
        self.a.selected=job['job_id'];self.ui.sync()
        self.assertEqual(self.ui.choices.layout.display,'')
        self.assertIn('retained',self.ui.downloads.value)

    def test_dropdown_changes_keep_jobs_selection_tile_and_map_without_execution(self):
        self.a.choose_tile(tile_spec(36864,-339968),self.mid)
        before=deepcopy((self.a.selected,self.a.tile,self.a.store.list()))
        widgets=(self.ui.map,self.ui.grid,self.ui.highlight,self.ui.downloads)
        self.ui.year.value=2023;self.ui.fallback_year.value=2022
        self.assertEqual(before,(self.a.selected,self.a.tile,self.a.store.list()))
        self.assertEqual(widgets,(self.ui.map,self.ui.grid,self.ui.highlight,self.ui.downloads))
        self.launcher.assert_not_called();self.a.before_live.assert_not_called();self.a.viewer.open.assert_not_called()

    def test_create_forwards_both_years_keeps_old_map_and_prevents_duplicate_run(self):
        old=self.a.store.get(self.mid)
        self.ui.year.value=2023;self.ui.fallback_year.value=2022
        with patch.object(self.ui,'_ensure_map'),patch.object(self.ui,'_checkpoint'):
            self.ui.prepare.click();self.ui.prepare.click()
        self.launcher.assert_called_once()
        job=self.a.store.get(self.a.selected)
        self.assertEqual(job['inputs']['request']['target_year'],2023)
        self.assertEqual(job['inputs']['request']['fallback_year'],2022)
        self.assertEqual(job['inputs']['request']['aoi_asset'],self.mapping['request']['aoi_asset'])
        self.assertEqual(self.a.store.get(self.mid),old)
        self.assertEqual(len(self.a.store.list(kind='mapping')),2)

    def test_fallback_only_change_is_a_distinct_mapping_request(self):
        before=self.a.request_defaults()
        preview=self.a.prepare_mapping({'fallback_year':2022})
        self.assertEqual(preview['type'],'preview')
        request=preview['settings']['request']
        for key in ('target_year','aoi_asset','training_asset','trees','year_count'):
            self.assertEqual(request[key],before[key])
        self.assertEqual(request['fallback_year'],2022)
        self.launcher.assert_not_called()

    def test_explicit_chat_edits_preserve_the_other_year_and_pending_data(self):
        preview=self.a.say('Set target year to 2023 and fallback year to 2022')
        request=preview['settings']['request']
        self.assertEqual((request['target_year'],request['fallback_year']),(2023,2022))
        again=self.a.say('Set the fallback year to 2021')['settings']['request']
        self.assertEqual((again['target_year'],again['fallback_year']),(2023,2021))
        self.assertEqual(again['training_asset'],request['training_asset'])
        self.generator.assert_not_called();self.launcher.assert_not_called()

    def test_chat_preview_and_form_stay_in_sync_without_auto_execution(self):
        self.ui.year.value=2023
        self.ui.message.value='Set fallback year to 2022'
        with patch.object(self.ui,'_ensure_map'),patch.object(self.ui,'_checkpoint'):
            self.ui.send.click()
        draft=self.a.store.get(self.a.pending)
        self.assertEqual(draft['inputs']['request']['target_year'],2023)
        self.assertEqual((self.ui.year.value,self.ui.fallback_year.value),(2023,2022))
        self.assertIn('Fallback year',self.ui.preview.value)
        self.assertEqual(self.ui.prepare.layout.display,'none')
        self.ui.fallback_year.value=2021
        self.assertIsNone(self.a.pending);self.assertEqual(self.a.store.get(draft['job_id'])['state'],'discarded')
        self.assertEqual(self.ui.prepare.layout.display,'')
        self.assertEqual(self.ui.year.value,2023)
        self.launcher.assert_not_called()

    def test_grounded_fallback_parser_and_unchanged_model_limits(self):
        for parser in (GuidedParser(),LocalParser(self.generator)):
            parsed=parser.parse('map 2023 with fallback 2022',{})
            self.assertEqual(parsed['settings'],{'target_year':2023,'fallback_year':2022})
        bad=LocalParser(lambda _:json.dumps(intent('mapping',settings={'fallback_year':2020})))
        self.assertEqual(bad.parse('Please prepare a map for 2023',{})['action'],'clarify')
        for value in (2016,2025,True,'2022'):
            with self.assertRaises(ValueError):self.a.prepare_mapping({'fallback_year':value})
        with self.assertRaises(ValueError):validate_intent(intent('mapping',settings={'trees':10}))
        self.launcher.assert_not_called()

    def test_active_mapping_keeps_new_run_button_disabled(self):
        self.a.store.create('mapping','active-elsewhere',{},state='running')
        self.ui.sync()
        self.assertTrue(self.ui.prepare.disabled)
        self.assertEqual(self.ui.choices.layout.display,'')


if __name__=='__main__':unittest.main()
