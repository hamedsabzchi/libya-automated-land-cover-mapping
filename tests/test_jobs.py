"""Persistence, recovery and export side-effect boundaries; no remote jobs."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile

from contracts import RunRequest
from contracts.models import GEE_SHA256
from libya_landcover import cli
from libya_landcover.job_store import JobStore, JobConflict
from libya_landcover.jobs import import_bundle, enqueue_mapping, work_one, checked_mapping_bundle
from libya_landcover.exports import (enqueue_export, submit_export, poll_export,
                                     cancel_export, export_spec, description)

ROOT = Path(__file__).resolve().parents[1]


def bundle_files():
    result = json.loads((ROOT/'contracts/examples/result.json').read_text())
    result['provenance']['engine_commit'] = 'a'*40
    status = json.loads((ROOT/'contracts/examples/status-completed.json').read_text())
    manifest = {'bundle_state':'completed','gee_sha256':GEE_SHA256,'engine_commit':'a'*40,
                'project':'example-project','representation':'serialized_graphs_not_geotiffs'}
    graph = json.dumps({'result':'0','values':{'0':{'constantValue':1}}}).encode()
    index = {'run_id':result['run_id'],'ee_version':'1.7.48',
             'representation':'earthengine_serialized_graph','artifacts':{}}
    files = {}
    for output in result['outputs']:
        identifier = output['artifact_id']
        index['artifacts'][identifier] = {'file':identifier+'.json','sha256':hashlib.sha256(graph).hexdigest()}
        files['graphs/'+identifier+'.json'] = graph
    for name,value in [('request.json',result['request']),('status.json',status),('result.json',result),
                       ('manifest.json',manifest),('graphs/index.json',index)]:
        files[name] = json.dumps(value).encode()
    return files


def spec():
    return {'crs':'EPSG:32633','transform':[10,0,0,0,-10,0]}


class Backend:
    def __init__(self):
        self.starts=[];self.cancels=[];self.operations=[];self.response=None
        self.fail_start=False;self.prepares=0

    def prepare(self, store, job):
        self.prepares+=1
        return {'expression':{'fixture':True},'description':description(job)}

    def start(self, request_id, payload):
        self.starts.append((request_id,deepcopy(payload)))
        if self.fail_start: raise TimeoutError('private remote response')
        return {'name':'projects/example-project/operations/server123','metadata':{'state':'PENDING','description':payload['description']}}

    def get(self, name):
        if isinstance(self.response,Exception): raise self.response
        return {'name':name,**self.response}

    def list(self): return self.operations
    def cancel(self,name): self.cancels.append(name)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=JobStore(self.root/'store')
        self.archive=self.root/'bundle.zip'
        self.files=bundle_files();self.write_archive()

    def write_archive(self,extra=None):
        with zipfile.ZipFile(self.archive,'w') as z:
            for name,data in self.files.items():z.writestr('run/'+name,data)
            for name,data in (extra or {}).items():z.writestr(name,data)

    def mapping(self):return import_bundle(self.store,self.archive)

    def export(self):
        mapping=self.mapping()
        result=json.loads(self.files['result.json'])
        return enqueue_export(self.store,mapping['job_id'],result['outputs'][0]['artifact_id'],spec(),request_id=str(uuid4()))

    def queued(self):
        request=RunRequest(json.loads(self.files['request.json']))
        return enqueue_mapping(self.store,request,project='example-project',engine_commit='a'*40)

    def test_import_is_persistent_idempotent_and_preserves_original_graphs(self):
        job=self.mapping()
        restarted=JobStore(self.root/'store')
        again=import_bundle(restarted,self.archive)
        self.assertEqual(job,again)
        checked=checked_mapping_bundle(restarted,again)
        self.assertEqual(checked['files'],self.files)
        self.assertEqual(len(restarted.events(job['job_id'])),2)

    def test_zip_traversal_duplicate_and_bad_checksum_rejected_before_registration(self):
        self.write_archive({'../outside.txt':'bad'})
        with self.assertRaises(ValueError):self.mapping()
        self.assertFalse((self.root/'outside.txt').exists())
        self.write_archive()
        with zipfile.ZipFile(self.archive,'a') as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');z.writestr('run/request.json','{}')
        with self.assertRaises(ValueError):self.mapping()
        name=next(n for n in self.files if n.startswith('graphs/') and not n.endswith('index.json'))
        self.files[name]=b'{}';self.write_archive()
        with self.assertRaises(ValueError):self.mapping()
        self.assertEqual(self.store.list(),[])

    def test_completed_import_cannot_change_under_same_identity(self):
        job=self.mapping()
        manifest=json.loads(self.files['manifest.json']);manifest['extra']='changed'
        self.files['manifest.json']=json.dumps(manifest).encode();self.write_archive()
        with self.assertRaises(JobConflict):self.mapping()
        self.assertEqual(self.store.get(job['job_id'])['state'],'completed')

    def test_request_identity_conflicts_and_stale_revisions(self):
        job=self.queued();self.assertEqual(job,self.queued())
        request=json.loads(self.files['request.json']);request['target_year']=2023
        with self.assertRaises(JobConflict):enqueue_mapping(self.store,RunRequest(request),project='example-project',engine_commit='a'*40)
        changed=self.store.update(job,state='running')
        with self.assertRaises(JobConflict):self.store.update(job,state='failed')
        self.assertEqual(self.store.events(job['job_id'])[-1],changed)

    def test_interrupted_worker_does_not_retry_model(self):
        job=self.store.update(self.queued(),state='running')
        with patch.object(cli,'main') as execute:
            self.assertIsNone(work_one(self.store))
        execute.assert_not_called()
        self.assertEqual(self.store.get(job['job_id'])['state'],'interrupted')

    def test_worker_recovers_completed_bundle_without_rerunning(self):
        job=self.store.update(self.queued(),state='running')
        folder=self.store.folder(job['job_id'])/'bundle'
        for name,data in self.files.items():
            path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        with patch.object(cli,'main') as execute:
            self.assertIsNone(work_one(self.store))
        execute.assert_not_called()
        self.assertEqual(self.store.get(job['job_id'])['state'],'completed')

    def test_worker_failure_is_terminal_and_not_automatically_retried(self):
        job=self.queued()
        with patch.object(cli,'main',return_value=3) as execute:
            result=work_one(self.store);self.assertIsNone(work_one(self.store))
        self.assertEqual(execute.call_count,1)
        self.assertEqual(result['state'],'failed')
        self.assertEqual(result['error']['exit_code'],3)

    def test_worker_lock_prevents_second_worker_or_early_recovery(self):
        job=self.store.update(self.queued(),state='running')
        with self.store.lock('mapping-worker'):
            with self.assertRaises(JobConflict):work_one(self.store)
        self.assertEqual(self.store.get(job['job_id'])['state'],'running')

    def test_export_creation_requires_matching_artifact_and_completed_source(self):
        mapping=self.mapping()
        with self.assertRaises(ValueError):enqueue_export(self.store,mapping['job_id'],str(uuid4()),spec(),request_id=str(uuid4()))
        queued=self.queued()
        with self.assertRaises(ValueError):enqueue_export(self.store,queued['job_id'],str(uuid4()),spec(),request_id=str(uuid4()))

    def test_spec_rejects_wrong_units_resolution_and_unsupported_fields(self):
        for value in [dict(spec(),crs='EPSG:4326'),dict(spec(),transform=[30,0,0,0,-30,0]),
                      dict(spec(),file_dimensions=1000),dict(spec(),scale=10),dict(spec(),max_pixels=True)]:
            with self.assertRaises(ValueError):export_spec(value)

    def test_export_idempotency_does_not_submit_until_explicit_start(self):
        job=self.export()
        same=enqueue_export(self.store,job['inputs']['mapping_job_id'],job['inputs']['artifact_id'],spec(),request_id=job['request_key'].split(':')[1])
        self.assertEqual(same,job)
        client=Backend()
        submitted=submit_export(self.store,job['job_id'],backend=client)
        self.assertEqual(submitted['state'],'submitted')
        self.assertEqual(submit_export(self.store,job['job_id'],backend=client),submitted)
        self.assertEqual(len(client.starts),1)
        self.assertEqual(client.starts[0][0],job['ee_request_id'])

    def test_same_request_identity_survives_reimport_into_another_local_store(self):
        first=self.export();client=Backend()
        submit_export(self.store,first['job_id'],backend=client)
        other=JobStore(self.root/'second-store')
        mapping=import_bundle(other,self.archive)
        second=enqueue_export(other,mapping['job_id'],first['inputs']['artifact_id'],spec(),
                              request_id=first['ee_request_id'])
        submit_export(other,second['job_id'],backend=client)
        self.assertNotEqual(first['job_id'],second['job_id'])
        self.assertEqual(client.starts[0],client.starts[1])

    def test_lost_response_reconciles_without_new_remote_submission(self):
        job=self.export();client=Backend();client.fail_start=True
        unknown=submit_export(self.store,job['job_id'],backend=client)
        self.assertEqual(unknown['state'],'submission_unknown')
        client.operations=[{'name':'projects/example-project/operations/already_started',
                            'metadata':{'state':'RUNNING','description':description(job)}}]
        recovered=poll_export(JobStore(self.root/'store'),job['job_id'],backend=client)
        self.assertEqual(recovered['state'],'running')
        self.assertEqual(len(client.starts),1)

    def test_explicit_unknown_retry_reuses_exact_payload_and_request_id(self):
        job=self.export();client=Backend();client.fail_start=True
        submit_export(self.store,job['job_id'],backend=client)
        client.fail_start=False
        recovered=submit_export(self.store,job['job_id'],backend=client)
        self.assertEqual(recovered['state'],'submitted')
        self.assertEqual(client.prepares,1)
        self.assertEqual(client.starts[0],client.starts[1])

    def test_failed_poll_preserves_previous_state(self):
        job=self.export();client=Backend();job=submit_export(self.store,job['job_id'],backend=client)
        client.response=TimeoutError('private')
        with self.assertRaises(TimeoutError):poll_export(self.store,job['job_id'],backend=client)
        self.assertEqual(self.store.get(job['job_id']),job)

    def test_completion_records_real_destinations_only_and_keeps_mapping_success(self):
        job=self.export();client=Backend();submit_export(self.store,job['job_id'],backend=client)
        client.response={'done':True,'metadata':{'state':'SUCCEEDED','destinationUris':
                         ['https://drive.google.com/drive/folders/example','javascript:bad','https://other.example/file']}}
        done=poll_export(self.store,job['job_id'],backend=client)
        self.assertEqual(done['state'],'completed')
        self.assertEqual(done['destination_uris'],['https://drive.google.com/drive/folders/example'])
        self.assertEqual(self.store.get(job['inputs']['mapping_job_id'])['state'],'completed')

    def test_late_destination_read_keeps_completed_state_and_never_resubmits(self):
        job=self.export();client=Backend();submit_export(self.store,job['job_id'],backend=client)
        client.response={'done':True,'metadata':{'state':'SUCCEEDED'}}
        done=poll_export(self.store,job['job_id'],backend=client)
        self.assertEqual(done['state'],'completed');self.assertEqual(done['destination_uris'],[])
        client.response={'metadata':{'state':'RUNNING'}}
        self.assertEqual(poll_export(self.store,job['job_id'],backend=client,refresh_destination=True),done)
        client.response={'done':True,'metadata':{'state':'SUCCEEDED','destinationUris':['https://drive.google.com/drive/folders/late']}}
        final=poll_export(self.store,job['job_id'],backend=client,refresh_destination=True)
        self.assertEqual(final['destination_uris'],['https://drive.google.com/drive/folders/late'])
        self.assertEqual(len(client.starts),1)

    def test_failure_never_downgrades_completed_mapping_or_claims_download(self):
        job=self.export();client=Backend();submit_export(self.store,job['job_id'],backend=client)
        client.response={'done':True,'metadata':{'state':'FAILED'},'error':{'code':13,'message':'User memory limit exceeded https://example.test/?access_token=private'}}
        failed=poll_export(self.store,job['job_id'],backend=client)
        self.assertEqual(failed['state'],'failed');self.assertEqual(failed['destination_uris'],[])
        self.assertNotIn('private',json.dumps(failed))
        self.assertIn('User memory limit exceeded',failed['error']['message'])
        self.assertEqual(self.store.get(job['inputs']['mapping_job_id'])['state'],'completed')

    def test_cancel_requires_remote_confirmation_and_handles_completion_race(self):
        job=self.export();client=Backend();submit_export(self.store,job['job_id'],backend=client)
        cancelled=cancel_export(self.store,job['job_id'],backend=client)
        self.assertEqual(cancelled['state'],'cancelling');self.assertEqual(len(client.cancels),1)
        client.response={'done':True,'metadata':{'state':'SUCCEEDED'}}
        self.assertEqual(poll_export(self.store,job['job_id'],backend=client)['state'],'completed')

    def test_cancel_queued_is_local_but_unknown_submission_is_not_false_cancelled(self):
        job=self.export();client=Backend()
        self.assertEqual(cancel_export(self.store,job['job_id'],backend=client)['state'],'cancelled')
        self.assertEqual(client.cancels,[])
        job=self.export();client.fail_start=True;submit_export(self.store,job['job_id'],backend=client)
        with self.assertRaises(JobConflict):cancel_export(self.store,job['job_id'],backend=client)
        self.assertEqual(self.store.get(job['job_id'])['state'],'submission_unknown')

    def test_tampered_persisted_payload_cannot_be_resubmitted(self):
        job=self.export();client=Backend();client.fail_start=True
        submit_export(self.store,job['job_id'],backend=client)
        (self.store.folder(job['job_id'])/'export-request.json').write_text('{}')
        with self.assertRaises(ValueError):submit_export(self.store,job['job_id'],backend=client)
        self.assertEqual(len(client.starts),1)

    def test_database_snapshot_retains_revisions(self):
        job=self.mapping();backup=self.root/'copy.sqlite3';self.store.snapshot(backup)
        import sqlite3
        with sqlite3.connect(backup) as db:
            count=db.execute('SELECT COUNT(*) FROM events WHERE record_id=?',(job['job_id'],)).fetchone()[0]
        self.assertEqual(count,2)


if __name__=='__main__':unittest.main()
