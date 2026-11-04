"""Persistent download cards over recorded export evidence; no remote side effects."""
from html import escape
import re
from urllib.parse import quote, urlparse

ACTIVE = {'submitting','submitted','running','cancelling','submission_unknown'}


def result_links(uris):
    links=[]
    for value in uris or []:
        if not isinstance(value,str):continue
        value=value.strip()
        match=re.fullmatch(r'\[[^\n]*\]\((https://[^\s]+)\)',value)
        if match:value=match[1]
        parsed=urlparse(value)
        if parsed.scheme=='https' and parsed.netloc in {'drive.google.com','docs.google.com'}:
            if value not in links:links.append(value)
    return links


def export_rows(store,mapping_id=None):
    """Include archived observations; prefer a recovered live operation over its snapshot."""
    rows=[]
    for record in store.list():
        if record['kind'] not in {'export','assistant_snapshot'}:continue
        mid=record['inputs']['mapping_job_id']
        if mapping_id and mid!=mapping_id:continue
        snapshot=record['kind']=='assistant_snapshot'
        job=record['inputs']['context']['export'] if snapshot else record
        rows.append({**job,'record_id':record['job_id'],'mapping_id':mid,'snapshot':snapshot})
    live={(r['mapping_id'],r.get('ee_request_id') or r.get('operation_name')) for r in rows if not r['snapshot']}
    return [r for r in rows if not r['snapshot'] or (r['mapping_id'],r.get('ee_request_id') or r.get('operation_name')) not in live]


def download_cards(rows,checks=None):
    if not rows:return '<h3>Downloads</h3><p>Select a blue square, then click <b>Create tile download</b>. Its status and link will appear here automatically.</p>'
    cards=[]
    for job in reversed(rows):
        window=job['inputs']['spec'].get('pixel_window',{})
        label=(f"Tile {window['column']//1024}, {window['row']//1024}" if window and job['inputs']['spec'].get('folder_prefix')=='LibyaLandCover_Tile' else 'Sample window' if window else 'Region download')
        year=job['inputs'].get('output',{}).get('year')
        if year:label=str(year)+' · '+label
        state=job['state'];links=result_links(job.get('destination_uris'))
        message={'queued':'Not submitted. No file is being created yet.',
            'submitting':'Sending your download request…', 'submitted':'Waiting for Earth Engine to start.',
            'running':'Earth Engine is creating your TIFF. This updates automatically.',
            'cancelling':'Cancellation is being checked.',
            'submission_unknown':'Checking whether Earth Engine received the request. No duplicate will be sent.',
            'completed':'Your TIFF export is complete.', 'failed':'The export failed.',
            'cancelled':'This export was cancelled.'}.get(state,'Checking the saved export record.')
        body=f'<h4>{escape(label)}</h4><p><b>{escape(message)}</b></p>'
        if job['snapshot']:body+='<p>Saved observation. Connect Google to check unfinished work automatically.</p>'
        if state=='completed':
            if links:
                body+=''.join('<p><a target="_blank" rel="noopener noreferrer" style="font-size:16px;font-weight:bold" href="'+escape(uri,quote=True)+'">Open download in Google Drive</a></p>' for uri in links)
            elif job.get('drive_folder'):
                folder=job['drive_folder']
                url='https://drive.google.com/drive/u/0/search?q='+quote(folder,safe='')
                body+='<p>Earth Engine did not return a direct link. Find the completed export in Drive:</p><p><a target="_blank" rel="noopener noreferrer" href="'+escape(url,quote=True)+'">Find exported folder in Google Drive</a></p><p>'+escape(folder)+'</p>'
            else:body+='<p>Earth Engine returned no destination. The recorded operation is retained; details are available below.</p>'
        if state in {'failed','queued'} and job.get('error'):
            from .map_view import error_detail
            body+='<p role="alert">'+escape(error_detail(job['error'].get('message','Export failed.')))+'</p>'
        check=(checks or {}).get(job['record_id'])
        if check:
            body+='<small>Last check: '+escape(check['at'])+'</small>'
            if check.get('error'):body+='<p>Could not reach Earth Engine. The saved status is unchanged; checking will resume automatically.</p>'
        coverage='One window; outside the study area is NoData.' if window else 'Previously requested full-region export.'
        body+='<details><summary>Download details</summary><p>Status: '+escape(state)+'</p><p>Operation: '+escape(job.get('operation_name') or 'Not yet confirmed')+'</p><p>'+coverage+'</p></details>'
        cards.append('<div style="padding:12px;margin-bottom:8px;border:1px solid #8ba9bf;border-radius:6px">'+body+'</div>')
    return '<h3>Downloads</h3>'+''.join(cards)
