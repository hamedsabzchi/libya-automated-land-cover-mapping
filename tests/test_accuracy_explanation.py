"""Interpret saved evidence without inference, authentication or remote work."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile
from libya_landcover.accuracy import render_accuracy
from libya_landcover.accuracy_explanation import explain_saved_accuracy
from libya_landcover.chat_language import GuidedParser
from libya_landcover.job_store import JobStore
from libya_landcover.local_language import LocalParser
from libya_landcover.map_assistant import MapAssistant
from libya_landcover.map_view import tile_spec
from libya_landcover.pilot import create_pilot
from test_jobs import bundle_files

# User-supplied aggregate counts, used only as offline test inputs.
MATRIX = [
 [19,2,0,0,0,0,0,0,0,0,0,0],[5,22,2,3,0,1,0,0,1,0,0,0],
 [1,2,10,0,1,1,0,0,1,0,0,0],[0,1,0,7,3,0,1,1,0,0,0,0],
 [0,0,1,0,29,6,0,0,0,0,0,0],[0,0,2,1,9,31,0,0,3,0,0,0],
 [0,1,0,0,0,0,73,1,2,0,3,4],[0,0,0,0,0,0,7,8,0,0,0,0],
 [0,0,0,0,0,2,1,0,21,0,0,0],[0,0,0,0,0,0,2,0,0,12,0,0],
 [0,2,0,0,0,0,0,0,0,0,19,3],[0,1,0,0,0,0,2,0,0,0,4,24]]


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for target in ('socket.socket.connect','google.auth.default'):
            guard=patch(target,side_effect=AssertionError('Offline only'))
            guard.start();self.addCleanup(guard.stop)
        self.remote=Mock(side_effect=AssertionError('No EE or worker'))
        self.generate=Mock(side_effect=AssertionError('No inference needed'))
        self.a=MapAssistant(JobStore(self.root/'store'),engine_commit='a'*40,
            parser=LocalParser(self.generate),launcher=self.remote,before_live=self.remote,viewer=Mock())
        files=bundle_files();result=json.loads(files['result.json'])
        result['metrics']={'overall':275/358,'kappa':.7371,'producer':[r[i]/sum(r) for i,r in enumerate(MATRIX)],
                           'confusion':MATRIX,'sampled_validation_count':358}
        files['result.json']=json.dumps(result).encode()
        archive=self.root/'input.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name,data in files.items():z.writestr('run/'+name,data)
        self.mapping=self.a.import_archive(archive);self.mid=self.a.selected

    def answer(self,text):
        r=self.a.say(text);self.assertEqual(r['type'],'accuracy')
        return r,' '.join(r['explanation']['paragraphs'])

    def test_interpret_is_short_with_full_evidence_preserved(self):
        before=self.a.accuracy();r,text=self.answer('Interpret accuracy')
        for fact in ('76.82%','275 of 358','83 were assigned','0.7371','Forest (90.48%)','Rocks (53.33%)'):
            self.assertIn(fact,text)
        self.assertEqual(r['metrics'],before['metrics']);self.assertEqual(r['run_id'],before['run_id'])
        visible,tables=render_accuracy(r).split('<details><summary>View saved accuracy tables and source</summary>',1)
        self.assertNotIn('<table',visible);self.assertIn('275 of 358',visible)
        self.assertIn('Confusion matrix',tables);self.assertIn('Saved result source',tables)
        self.generate.assert_not_called();self.remote.assert_not_called()

    def test_named_class_uses_reference_and_prediction_denominators(self):
        r,text=self.answer('Explain the accuracy of cultivated irrigated land.')
        self.assertEqual(r['explanation']['class_codes'],[5])
        for fact in ('80.56%','69.05%','Of 36 reference samples','29 were classified correctly',
                     '7 were assigned to other classes','Of 42 samples predicted','13 belong to other','Orchards: 6'):
            self.assertIn(fact,text)
        r,text=self.answer('What about orchards?')
        self.assertEqual(r['explanation']['class_codes'],[6]);self.assertIn('Cultivated irrigated: 9',text)
        self.generate.assert_not_called()

    def test_confusions_include_directions_and_ties(self):
        _,text=self.answer('Which classes are most often confused?')
        for fact in ('Cultivated irrigated / Orchards: 15 errors','6 reference Cultivated irrigated',
                     '9 reference Orchards','Bare soil/sand / Rocks: 8 errors',
                     'Forest / Shrubland: 7 errors','Seasonal water / Sebkha: 7 errors'):
            self.assertIn(fact,text)
        self.assertIn('sample counts, not mapped areas',text);self.assertNotIn('76.82%',text)

    def test_definitions_and_kappa_are_not_another_table(self):
        _,text=self.answer('What does producer accuracy mean?')
        self.assertIn('reference row total',text);self.assertIn('prediction column total',text)
        self.assertNotIn('275 of 358',text)
        _,text=self.answer('Explain Kappa')
        self.assertIn('0.7371',text);self.assertIn('not a percentage',text);self.assertNotIn('73.71%',text)

    def test_unknown_class_year_and_cause_are_not_invented(self):
        for query in ('Explain accuracy of mangroves','Explain the accuracy of class 13'):
            r,text=self.answer(query);self.assertEqual(r['explanation']['title'],'Which land-cover class?')
            self.assertNotIn('76.82%',text)
        _,text=self.answer('Interpret accuracy for 2023')
        self.assertIn('selected saved result is for 2024',text);self.assertIn('No new run',text)
        _,text=self.answer('Why are rocks misclassified?')
        self.assertIn('Bare soil/sand: 7',text);self.assertIn('does not identify',text)
        self.remote.assert_not_called()

    def test_null_empty_and_perfect_matrices(self):
        r=self.a.accuracy()
        r['metrics']={'overall':None,'kappa':None,'sampled_validation_count':0,
                      'producer':[None]*12,'confusion':[[0]*12 for _ in range(12)]}
        for row in r['classes']:row.update(producer_percent=None,user_percent=None,samples=0)
        for q in ('Interpret accuracy','Explain Kappa','Which classes are most often confused?','Explain accuracy of rocks'):
            text=' '.join(explain_saved_accuracy(r,q)['explanation']['paragraphs'])
            self.assertNotIn('nan',text);self.assertNotIn('100.00%',text);self.assertNotIn('76.82%',text)
        self.assertIn('no samples',' '.join(explain_saved_accuracy(r,'Interpret accuracy')['explanation']['paragraphs']))
        r=self.a.accuracy();r['metrics']['confusion']=[[int(i==j) for j in range(12)] for i in range(12)]
        self.assertIn('No off-diagonal errors',' '.join(explain_saved_accuracy(r,'Which classes are confused?')['explanation']['paragraphs']))
        r={'type':'accuracy','state':'unavailable','message':'Not recorded'}
        self.assertEqual(explain_saved_accuracy(r,'Interpret accuracy'),r)

    def test_buttons_and_chat_preserve_map_export_draft_and_job_history(self):
        from libya_landcover.map_ui import MapUI
        job=create_pilot(self.a.store,self.mid,self.mapping['outputs'][0]['artifact_id'],{'spec':tile_spec(36864,-339968)})
        self.a.selected=job['job_id']
        ui=MapUI(self.a,connect=Mock(),auto_poll=False);self.addCleanup(ui.close)
        self.a.choose_tile(job['inputs']['spec'],self.mid)
        self.a._draft({'action':'pilot','mapping_job_id':self.mid,'artifact_id':job['inputs']['artifact_id'],
                       'plan':{'spec':job['inputs']['spec']}})
        original=deepcopy((self.a.selected,self.a.tile,self.a.pending,self.a.store.list()))
        widgets=(ui.map,ui.grid,ui.highlight,ui.downloads,ui.tile_action)
        with patch.object(ui,'_ensure_map',self.remote),patch.object(ui,'_checkpoint',self.remote),patch('libya_landcover.map_ui.poll_export',self.remote):
            ui.explain_accuracy_button.click()
            for q in ('Interpret accuracy','Explain the accuracy of cultivated irrigated land',
                      'Which classes are most often confused?','What does producer accuracy mean?'):
                ui.message.value=q;ui.send.click()
        self.assertIn('Accuracy explained',ui.transcript.value);self.assertIn('Class accuracy explained',ui.transcript.value)
        self.assertEqual(original,(self.a.selected,self.a.tile,self.a.pending,self.a.store.list()))
        self.assertEqual(widgets,(ui.map,ui.grid,ui.highlight,ui.downloads,ui.tile_action))
        self.remote.assert_not_called();self.generate.assert_not_called();self.a.viewer.open.assert_not_called()

    def test_guided_questions_work_and_other_commands_are_preserved(self):
        self.a.parser=GuidedParser()
        for q in ('Interpret accuracy','Explain accuracy of class 8','Explain user accuracy'):
            self.assertIn('explanation',self.a.say(q))
        self.assertEqual(GuidedParser().parse('map 2023',{})['action'],'mapping')
        self.assertEqual(GuidedParser().parse('area under each class',{})['action'],'help')
        self.assertNotIn('explanation',self.a.say('Show confusion matrix'))
        self.assertNotIn('explanation',explain_saved_accuracy(self.a.accuracy(),'/accuracy 12345678-2023-4000-8000-123456789012'))


if __name__=='__main__':unittest.main()

