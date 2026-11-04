"""All-work recovery and delivery rendering, with no network or credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4
import zipfile
from libya_landcover.assistant import TRIPOLI
from libya_landcover.map_assistant import MapAssistant
from libya_landcover.map_view import tile_spec
from libya_landcover.job_store import JobStore
from libya_landcover.pilot import create_pilot
from libya_landcover.downloads import export_rows,download_cards,result_links
from libya_landcover.workspace import save_workspace,restore_workspace
from libya_landcover.jobs import checked_mapping_bundle
from test_jobs import bundle_files


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('socket.socket.connect',side_effect=AssertionError('Offline tests only'))
        self.network.start();self.addCleanup(self.network.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.a=MapAssistant(JobStore(self.root/'original'),engine_commit='a'*40,launcher=Mock())
        archive=self.root/'old.zip'
        with zipfile.ZipFile(archive,'w') as out:
            for name,data in bundle_files().items():out.writestr('run/'+name,data)
        self.mapping=self.a.import_archive(archive);self.mid=self.a.mapping_id()
    def export(self,column,state,uri=None):
        artifact=self.mapping['outputs'][0]['artifact_id']
        job=create_pilot(self.a.store,self.mid,artifact,{'spec':tile_spec(column,-339968)})
        return self.a.store.update(job,state=state,operation_name='projects/example-project/operations/op'+str(column),drive_folder='Recorded_'+str(column),destination_uris=[uri] if uri else [])
    def test_all_downloads_graphs_and_failed_job_evidence_survive_restore_and_resave(self):
        first=self.export(36864,'completed','https://drive.google.com/drive/folders/one')
        second=self.export(37888,'running')
        failed=self.a.store.create('mapping','failed-example',{},state='failed')
        folder=self.a.store.folder(failed['job_id']);folder.mkdir(parents=True)
        (folder/'worker.log').write_text('Retain this failure evidence')
        self.a.selected=first['job_id'];self.a.choose_tile(tile_spec(36864,-339968),self.mid)
        draft=self.a._draft({'action':'pilot','mapping_job_id':self.mid,'artifact_id':first['inputs']['artifact_id'],'plan':{'spec':first['inputs']['spec']}})
        expected=checked_mapping_bundle(self.a.store,self.a.store.get(self.mid))['files']
        saved=save_workspace(self.a,self.root/'all.zip',history=['escaped old conversation'])
        other=MapAssistant(JobStore(self.root/'other'),engine_commit='a'*40,launcher=Mock())
        restore_workspace(other,saved)
        self.assertIsNone(other.pending) # A different session cannot revive an executable approval.
        rows=export_rows(other.store)
        self.assertEqual({r['state'] for r in rows},{'completed','running'})
        self.assertEqual(other.describe()['original_job_id'],first['job_id'])
        self.assertEqual(other.tile['spec'],first['inputs']['spec'])
        restored_map=other.store.get(other.mapping_id())
        self.assertEqual(checked_mapping_bundle(other.store,restored_map)['files'],expected)
        old_evidence=list((other.store.root/'workspace-history').rglob('worker.log'))
        self.assertEqual(old_evidence[0].read_text(),'Retain this failure evidence')
        again=save_workspace(other,self.root/'again.zip')
        with zipfile.ZipFile(again) as z:
            self.assertTrue(any(n.endswith('worker.log') for n in z.namelist()))
            self.assertTrue(any(n.startswith('history/') for n in z.namelist()))
        other.launcher.assert_not_called();self.a.launcher.assert_not_called()
        self.assertEqual(self.a.pending,draft['draft_id'])
    def test_tampered_export_or_traversal_is_rejected_before_import(self):
        self.export(36864,'running');saved=save_workspace(self.a,self.root/'good.zip')
        with zipfile.ZipFile(saved) as z:entries={n:z.read(n) for n in z.namelist()}
        manifest=json.loads(entries['workspace.json'])
        next(r for r in manifest['records'] if r['kind']=='export')['ee_request_id']=str(uuid4())
        entries['workspace.json']=json.dumps(manifest).encode()
        bad=self.root/'bad.zip'
        with zipfile.ZipFile(bad,'w') as z:
            for n,data in entries.items():z.writestr(n,data)
        other=MapAssistant(JobStore(self.root/'other'),engine_commit='a'*40)
        with self.assertRaises(ValueError):restore_workspace(other,bad)
        self.assertEqual(other.store.list(),[])
        with zipfile.ZipFile(bad,'a') as z:z.writestr('../outside','no')
        with self.assertRaises(ValueError):restore_workspace(other,bad)
        self.assertEqual(other.store.list(),[])
    def test_fallback_is_labelled_search_and_only_shown_after_completion(self):
        job=self.export(36864,'running')
        self.assertNotIn('drive/u/0/search',download_cards(export_rows(self.a.store)))
        self.a.store.update(job,state='completed')
        body=download_cards(export_rows(self.a.store))
        self.assertIn('Find exported folder in Google Drive',body)
        self.assertIn('Recorded_36864',body)
        self.assertNotIn('Open download in Google Drive',body)
    def test_result_links_support_archived_markdown_without_untrusted_destinations(self):
        good='https://drive.google.com/drive/folders/result'
        self.assertEqual(result_links(['['+good+']('+good+')',good,'javascript:alert(1)','https://drive.google.com.evil.test/x']),[good])
