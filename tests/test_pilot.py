"""Bounded delivery, archive recovery and diagnostic tests; no EE service calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

from test_jobs import bundle_files, Backend
from libya_landcover.job_store import JobStore
from libya_landcover.jobs import import_bundle, checked_mapping_bundle, bundle_digest
from libya_landcover.exports import export_spec, window_bounds, submit_export, poll_export, description, recover_export
from libya_landcover.pilot import (centered_spec, adopt_archive, create_pilot, recover_pilot,
                                   save_diagnostic, save_handoff)


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root/'source.zip'
        self.files = bundle_files()
        with zipfile.ZipFile(self.archive,'w') as z:
            for name,data in self.files.items():z.writestr('run/'+name,data)
        self.store = JobStore(self.root/'store')
        self.mapping = import_bundle(self.store,self.archive)
        self.artifact = json.loads(self.files['result.json'])['outputs'][0]['artifact_id']
        self.plan = {'spec':centered_spec([400005,3600005]),'valid_raster_pixels_verified':False}

    def pilot(self):
        return create_pilot(self.store,self.mapping['job_id'],self.artifact,self.plan)

    def test_window_exact_bounds_negative_rows_and_parent_origin(self):
        spec=centered_spec([400005,3600005])
        self.assertEqual(spec['pixel_window'],{'column':39488,'row':-360513,'width':1024,'height':1024})
        self.assertEqual(window_bounds(spec),[394880,3594890,405120,3605130])
        shifted=centered_spec([400005,3600005],side=512,transform=[10,0,5,0,-10,5])
        self.assertEqual(window_bounds(shifted),[397445,3597445,402565,3602565])
        self.assertEqual(spec['transform'],[10,0,0,0,-10,0])

    def test_window_rejects_unbounded_fractional_and_undersized_cap(self):
        for change in ({'width':1025},{'height':0},{'row':1.5},{'column':True},{'extra':1}):
            spec={**self.plan['spec'],'pixel_window':{**self.plan['spec']['pixel_window'],**change}}
            with self.assertRaises(ValueError):export_spec(spec)
        with self.assertRaises(ValueError):export_spec({**self.plan['spec'],'max_pixels':100})
        for point in ([float('nan'),1],[True,2],[1],None):
            with self.assertRaises(ValueError):centered_spec(point)

    def test_pilot_identity_stable_after_new_store_and_changed_window_is_new(self):
        first=self.pilot();other=JobStore(self.root/'other')
        source=adopt_archive(other,self.archive)['mapping']
        second=create_pilot(other,source['job_id'],self.artifact,self.plan)
        self.assertEqual(first['ee_request_id'],second['ee_request_id'])
        altered=create_pilot(other,source['job_id'],self.artifact,{'spec':centered_spec([420005,3600005])})
        self.assertNotEqual(first['ee_request_id'],altered['ee_request_id'])
        self.assertEqual(first['state'],'queued');self.assertIsNone(first['operation_name'])

    def test_adopt_wp05_backup_ignores_uploaded_database(self):
        checked=checked_mapping_bundle(self.store,self.mapping)
        path=self.root/'backup.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('export-manifest.json',json.dumps({'mapping':self.mapping,'export':{'state':'running'}}))
            z.writestr('jobs.sqlite3',b'NOT A DATABASE')
            for name,data in checked['files'].items():
                z.writestr('jobs/'+self.mapping['job_id']+'/bundle/'+name,data)
        adopted=adopt_archive(JobStore(self.root/'restore'),path)
        self.assertEqual(adopted['mapping']['inputs']['bundle_digest'],bundle_digest(checked))
        self.assertEqual(adopted['previous_manifest']['export']['state'],'running')

    def test_unsafe_or_tampered_archive_rejected(self):
        for filename,data in [('../escape','bad'),('run/graphs/'+self.artifact+'.json','{}')]:
            path=self.root/'bad.zip'
            with zipfile.ZipFile(path,'w') as z:
                for name,content in self.files.items():
                    if 'run/'+name != filename:z.writestr('run/'+name,content)
                z.writestr(filename,data)
            with self.assertRaises(ValueError):adopt_archive(self.store,path)

    def test_recovery_verifies_identity_and_does_not_submit(self):
        job=self.pilot();client=Backend()
        name='projects/example-project/operations/pilot'
        client.response={'name':name,'metadata':{'state':'RUNNING','description':description(job),
                          'attempt':2,'progress':0.56,'stages':[{'displayName':'Create Local Files'}]}}
        recovered=recover_export(self.store,job['job_id'],name,backend=client)
        self.assertEqual(recovered['remote_metadata']['attempt'],2)
        self.assertEqual(recovered['remote_metadata']['progress'],0.56)
        self.assertEqual(client.starts,[])
        self.assertEqual(client.cancels,[])
        with self.assertRaises(ValueError):recover_export(self.store,job['job_id'],'projects/other/operations/pilot',backend=client)
        fresh=create_pilot(self.store,self.mapping['job_id'],self.artifact,{'spec':centered_spec([450000,3600000])})
        with self.assertRaises(ValueError):recover_export(self.store,fresh['job_id'],name,backend=client)

    def test_portable_handoff_restores_plan_operation_and_preserves_history(self):
        job=self.pilot();client=Backend();job=submit_export(self.store,job['job_id'],backend=client)
        client.response={'name':job['operation_name'],'metadata':{'state':'RUNNING','description':description(job),'progress':0.2}}
        save_diagnostic(self.store,job['job_id'],backend=client)
        path=self.root/'handoff.zip'
        save_handoff(self.store,job['job_id'],self.plan,path,service_commit='a'*40,
                     original_operation='projects/example-project/operations/full')
        other=JobStore(self.root/'resumed')
        imported=adopt_archive(other,path)
        resumed=recover_pilot(other,imported['mapping']['job_id'],imported['context'],backend=client)
        self.assertEqual(resumed['operation_name'],job['operation_name'])
        self.assertEqual(resumed['state'],'running')
        self.assertEqual(len(client.starts),1)
        self.assertTrue((other.folder(resumed['job_id'])/'recovered-history.json').exists())
        self.assertTrue((other.folder(resumed['job_id'])/'recovered-diagnostics.json').exists())
        second=self.root/'second.zip'
        save_handoff(other,resumed['job_id'],self.plan,second,service_commit='a'*40)
        with zipfile.ZipFile(second) as z:
            self.assertIn('pilot/recovered-history.json',z.namelist())
            self.assertNotIn('jobs.sqlite3',z.namelist())
            self.assertFalse(json.loads(z.read('pilot-context.json'))['raster_included'])

    def test_diagnostic_failure_does_not_block_backup_or_change_job(self):
        job=self.pilot();client=Backend();job=submit_export(self.store,job['job_id'],backend=client)
        client.response=TimeoutError('private transport detail')
        diagnostic=save_diagnostic(self.store,job['job_id'],backend=client)
        self.assertEqual(diagnostic['lookup_error_type'],'TimeoutError')
        self.assertNotIn('private transport',json.dumps(diagnostic))
        self.assertEqual(self.store.get(job['job_id']),job)
        path=self.root/'backup.zip'
        save_handoff(self.store,job['job_id'],self.plan,path,service_commit='a'*40)
        self.assertTrue(path.is_file())

    def test_failed_operation_message_retained_in_private_diagnostic(self):
        job=self.pilot();client=Backend();job=submit_export(self.store,job['job_id'],backend=client)
        client.response={'name':job['operation_name'],'done':True,'metadata':{'state':'FAILED'},
                         'error':{'code':3,'message':'Detailed export failure'}}
        diagnostic=save_diagnostic(self.store,job['job_id'],backend=client)
        self.assertEqual(diagnostic['operation']['error']['message'],'Detailed export failure')
        self.assertEqual(self.store.get(self.mapping['job_id'])['state'],'completed')
