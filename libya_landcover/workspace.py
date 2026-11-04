"""Portable all-work checkpoint. Imports verified graphs, never uploaded SQL or code."""
import json
from pathlib import Path
import stat
import tempfile
from uuid import uuid4
import zipfile

from .bundle import canonical_uuid
from .job_store import now
from .jobs import checked_mapping_bundle, validate_bundle, bundle_digest, MAX_BUNDLE_BYTES

SCHEMA='landcover-workspace.1'
MAX_WORKSPACE_BYTES=512*1024*1024


def save_workspace(assistant,destination,*,history=None):
    records=assistant.store.list()
    manifest={'schema_version':SCHEMA,'created_at':now(),'selected':assistant.selected,
        'tile':getattr(assistant,'tile',None),'profile':assistant.profile,'engine_commit':assistant.engine_commit,
        'records':records,'events':{r['job_id']:assistant.store.events(r['job_id']) for r in records},
        'chat_history':list(history or []),'raster_included':False}
    files={}
    for path in assistant.store.root.glob('landcover-*.json'):
        if path.is_file() and not path.is_symlink():files['evidence/session/'+path.name]=path.read_bytes()
    prior_history=assistant.store.root/'workspace-history'
    if prior_history.exists():
        for path in prior_history.rglob('*'):
            if path.is_file() and not path.is_symlink():
                files['history/'+path.relative_to(prior_history).as_posix()]=path.read_bytes()
    for job in records:
        if job['kind']=='mapping' and job['state']=='completed':
            checked=checked_mapping_bundle(assistant.store,job)
            for name,data in checked['files'].items():files['maps/'+job['job_id']+'/run/'+name]=data
        # Retain diagnostics, failed-run evidence and export payloads as evidence.
        folder=assistant.store.folder(job['job_id'])
        if folder.exists():
            for path in folder.rglob('*'):
                if path.is_file() and not path.is_symlink() and path.suffix in {'.json','.log'}:
                    if job['kind']=='mapping' and job['state']=='completed' and 'bundle' in path.relative_to(folder).parts:continue
                    files['evidence/'+job['job_id']+'/'+path.relative_to(folder).as_posix()]=path.read_bytes()
    files['workspace.json']=json.dumps(manifest,ensure_ascii=False,allow_nan=False).encode()
    if sum(len(v) for v in files.values())>MAX_WORKSPACE_BYTES:raise ValueError('Workspace backup exceeds 512 MB; keep this session and save individual results.')
    destination=Path(destination);temporary=destination.with_suffix('.tmp')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as out:
        for name,data in files.items():out.writestr(name,data)
    temporary.replace(destination)
    return destination


def is_workspace(path):
    with zipfile.ZipFile(path) as source:return 'workspace.json' in source.namelist()


def restore_workspace(assistant,path):
    """Restore all completed maps and export observations, with no remote calls."""
    from .map_view import tile_spec
    from .pilot import pilot_request_id
    with zipfile.ZipFile(path) as source:
        items=source.infolist();names=[i.filename for i in items]
        if len(names)!=len(set(names)) or len(names)>20000 or sum(i.file_size for i in items)>MAX_WORKSPACE_BYTES:raise ValueError('Invalid or oversized workspace archive')
        for item in items:
            p=Path(item.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in item.filename or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Unsafe workspace member')
        manifest=json.loads(source.read('workspace.json'))
        if manifest.get('schema_version')!=SCHEMA:raise ValueError('Unsupported workspace backup')
        records=manifest['records'];checked_maps={};contexts={}
        if not isinstance(records,list) or len(records)>10000:raise ValueError('Invalid workspace records')
        for job in records:
            identifier=canonical_uuid(job['job_id'])
            if job['kind']=='mapping' and job['state']=='completed':
                prefix='maps/'+identifier+'/run/'
                if sum(i.file_size for i in items if i.filename.startswith(prefix))>MAX_BUNDLE_BYTES:raise ValueError('Mapping bundle too large')
                checked_maps[identifier]=validate_bundle(lambda name:source.read(prefix+name))
        for record in records:
            if record['kind'] not in {'export','assistant_snapshot'}:continue
            mid=record['inputs']['mapping_job_id'];checked=checked_maps.get(mid)
            if checked is None:raise ValueError('An export is missing its completed mapping')
            if record['kind']=='assistant_snapshot':context=record['inputs']['context']
            else:
                context={'schema_version':'wp05-pilot.1','created_at':record['updated_at'],
                    'service_commit':manifest['engine_commit'],'bundle_digest':bundle_digest(checked),
                    'export':record,'plan':{'spec':record['inputs']['spec']},'raster_included':False,
                    'recovery_history':{'events':manifest.get('events',{}).get(record['job_id'],[])}}
            old=context['export'];spec=old['inputs']['spec']
            if context.get('bundle_digest')!=bundle_digest(checked) or context['plan']['spec']!=spec:raise ValueError('Export does not match its saved map')
            if 'pixel_window' in spec:
                if pilot_request_id(checked,old['inputs']['artifact_id'],spec)!=old['ee_request_id']:raise ValueError('Export identity does not match')
            else:
                from .exports import export_spec
                canonical_uuid(old['ee_request_id']);export_spec(spec)
                artifacts=json.loads(checked['files']['graphs/index.json'])['artifacts']
                if old['inputs']['artifact_id'] not in artifacts or old['inputs']['project']!=checked['manifest']['project']:raise ValueError('Legacy export does not match its map')
            contexts[record['job_id']]=(mid,context)
        # Validation finished before any persistent mapping is created.
        ids={}
        for old_id,checked in checked_maps.items():
            with tempfile.TemporaryDirectory() as tmp:
                archive=Path(tmp)/'mapping.zip'
                with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as out:
                    for name,data in checked['files'].items():out.writestr('run/'+name,data)
                result=assistant.import_archive(archive);ids[old_id]=result['job_id']
        for old_id,(mid,context) in contexts.items():
            new_mid=ids[mid]
            record=assistant.store.create('assistant_snapshot','snapshot:'+new_mid+':'+context['export']['job_id']+':'+str(context['export']['revision']),
                {'mapping_job_id':new_mid,'context':context},state='recorded')
            ids[old_id]=record['job_id']
        evidence=assistant.store.root/'workspace-history'/str(uuid4());evidence.mkdir(parents=True)
        (evidence/'workspace.json').write_text(json.dumps(manifest,ensure_ascii=False))
        for name in names:
            if name.startswith(('evidence/','history/')):
                dest=evidence/Path(name);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read(name))
    assistant.discard()
    assistant.selected=ids.get(manifest.get('selected'),next(reversed(ids.values()),None))
    tile=manifest.get('tile');assistant.tile=None
    if tile and tile.get('mapping_id') in ids:
        spec=tile['spec'];w=spec['pixel_window']
        if tile_spec(w['column'],w['row'])==spec:
            assistant.tile={'mapping_id':ids[tile['mapping_id']],'spec':spec}
            assistant.map_id=ids[tile['mapping_id']]
    if not assistant.selected:raise ValueError('This archive contains evidence but no completed map to reopen. The evidence was retained for support.')
    return {'type':'workspace_restored','message':'Saved maps and download records restored. Connect Google to continue; no mapping or export was started.',
        'restored_count':len(ids),'job_id':assistant.selected,'state':assistant.describe()['state']}


def recover_saved_export(store,record):
    """Attach an archived operation; never submit a new export."""
    from .pilot import recover_pilot
    context=record['inputs']['context'];mid=record['inputs']['mapping_job_id'];old=context['export']
    if 'pixel_window' in old['inputs']['spec']:return recover_pilot(store,mid,context)
    from .exports import enqueue_export,recover_export
    job=enqueue_export(store,mid,old['inputs']['artifact_id'],old['inputs']['spec'],request_id=old['ee_request_id'])
    if old.get('operation_name'):return recover_export(store,job['job_id'],old['operation_name'])
    if job['state']=='queued' and old['state']!='queued':
        job=store.update(job,state=old['state'] if old['state'] in {'failed','cancelled'} else 'submission_unknown')
    return job
