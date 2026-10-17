"""Grounded map/legend/download actions over the existing assistant service."""
import re
from .assistant import Assistant
from .jobs import checked_mapping_bundle
from .map_view import MapBackend, CLASS_NAMES


class MapAssistant(Assistant):
    def __init__(self,*args,viewer=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.viewer=viewer or MapBackend(self.store)
        self.tile=None
        self.map_id=None

    def mapping_id(self):
        job=self._choose()
        return job['inputs']['mapping_job_id'] if job['kind'] in {'export','assistant_snapshot'} else job['job_id']

    def _draft(self,inputs):
        if inputs['action']=='mapping':
            target={k:v for k,v in inputs['request'].items() if k!='request_id'}
            for job in reversed(self.store.list(kind='mapping')):
                if job['state'] not in {'queued','running','completed'}:continue
                request=(checked_mapping_bundle(self.store,job)['request'].to_dict() if job['state']=='completed' else job['inputs']['request'])
                project=job['inputs'].get('project')
                if project==inputs['project'] and {k:v for k,v in request.items() if k!='request_id'}==target:
                    # Keep a selected download for this map visible rather than losing it.
                    if self.selected:
                        current=self.store.get(self.selected)
                        if current['inputs'].get('mapping_job_id')==job['job_id']:return self.describe()
                    return self.describe(job['job_id'])
            if any(j['state'] in {'queued','running'} for j in self.store.list(kind='mapping')):
                return {'type':'help','message':'A map is already being prepared. Follow its progress before starting another map.'}
        return super()._draft(inputs)

    def open_map(self):
        self.before_live()
        identifier=self.mapping_id()
        data=self.viewer.open(identifier)
        if self.map_id!=identifier:self.tile=None
        self.map_id=identifier
        return data

    def choose_tile(self,spec,mapping_id):
        self.discard()
        if mapping_id!=self.mapping_id():raise ValueError('Open the current map before choosing a tile.')
        self.tile={'mapping_id':mapping_id,'spec':spec}

    def prepare_pilot(self,job_id=None):
        self.discard()
        if job_id:self._choose(job_id)
        if not self.tile or self.tile['mapping_id']!=self.mapping_id():
            return {'type':'help','message':'Click a grid tile on the map first, then choose Download selected tile.'}
        self.before_live()
        artifact,plan=self.viewer.plan(self.tile['mapping_id'],self.tile['spec'])
        return self._draft({'action':'pilot','mapping_job_id':self.tile['mapping_id'],'artifact_id':artifact,'plan':plan})

    @staticmethod
    def _export_summary(job,**kwargs):
        reply=Assistant._export_summary(job,**kwargs)
        if job['inputs']['spec'].get('folder_prefix')=='LibyaLandCover_Tile':
            reply['coverage']='selected_tile_only'
            reply['message']='This download covers the selected grid tile. Outside the study area is NoData.'
        return reply

    def say(self,text):
        if not isinstance(text,str) or len(text)>4000:return super().say(text)
        clean=text.lower().strip().rstrip('?.!')
        if any(word in clean for word in ('legend','colours','colors')):
            self.discard()
            return {'type':'help','message':'The map colours represent these land-cover classes:\n'+
                '\n'.join(f'{i}. {name}' for i,name in enumerate(CLASS_NAMES,1))+
                '\nTransparent areas have no displayed data. This legend does not calculate class areas.'}
        if clean in {'what next','what should i do next','help','hello','hi'}:
            self.discard()
            if not self.selected:
                message='Connect Google, choose a year and click Review my map. Check the choices and click Create map. You do not need to upload a file.'
            else:
                current=self.describe()
                if current['type']=='export':
                    message=('Your download is ready. Use the Google Drive link above to get the TIFF. You can select another grid tile for another download.' if current['state']=='completed' else 'Follow the download status above. It updates automatically while connected. Do not submit the same download again.')
                elif current['state']=='completed':
                    message='Connect Google if needed, then explore the map. Click a blue grid square and choose Download selected tile. Review it and click Create tile download.'
                elif current['state'] in {'queued','running'}:
                    message='Your map is being prepared. Keep this notebook connected. Progress updates automatically; do not start the same map again.'
                else:message='The map needs attention. Open Details and support and save the error details before starting another map.'
            return {'type':'help','message':message+' I can explain the legend, check progress or prepare the tile you select. Save work for later before ending your session.'}
        if clean in {'status','what is the status','is my map ready','has my export finished','check status','what is the status of my result'}:
            self.discard()
            if not self.selected:return {'message':'Connect Google and choose a year to create your first map.'}
            return self.refresh()
        if re.search(r'\b(download|export)\b',clean) and re.search(r'\b(this|selected)\b',clean) and 'tile' in clean:
            return self.prepare_pilot()
        if clean in {'show map','open map','show my map'}:
            self.discard()
            return {'type':'show_map','message':'Opening your map.'}
        # The local language model continues parsing year/region requests; no execution.
        return super().say(text)
