"""One-screen notebook workspace: staged workflow, live map, selected-tile delivery."""
import asyncio
from html import escape
import json
import time
from .chat_ui import ChatUI, render_reply, table, area_name
from .map_view import feature, tile_at, tile_spec, visible_grid, legend_html, MapDisplayError, error_detail
from .exports import poll_export
from .job_store import now
from .notebook_map import NotebookMap, valid_bounds, view_for_bounds
from .downloads import ACTIVE, export_rows, download_cards


class MapUI(ChatUI):
    def __init__(self,assistant,*,download=None,connect=None,auto_poll=True,poll_seconds=20,preserve_draft=False):
        import ipywidgets as w
        from ipyleaflet import GeoJSON,LayersControl,ScaleControl
        self._map_ready=False;self._busy=False;self._polling=False
        self._browser_updates=False;self._browser_callback=None;self._browser_ticking=False
        self._browser_last_poll=None;self._last_view_check=None
        self.last_error=None
        self.display_check=None
        self.map_data=None;self._attempted=None;self._load_task=None;self._poll_task=None
        self.poll_seconds=poll_seconds
        self._poll_wake=asyncio.Event();self._poll_checks={};self._link_checks={};self._poll_index=0
        self._backup_signature=None
        super().__init__(assistant,download=download,connect=connect,preserve_draft=preserve_draft)
        self.prepare=w.Button(description='Create map',button_style='primary',layout=w.Layout(width='190px'))
        self.prepare.on_click(lambda _:self._action(self._create_map))
        self.choices.children=(*self.choices.children[:-1],self.prepare)
        # Use a plain background: no third-party basemap tile requests in Colab.
        self.map=NotebookMap(layers=(),center=(32.7,13.2),zoom=8,scroll_wheel_zoom=True,layout=w.Layout(height='520px',width='100%'))
        self.map.add(LayersControl(position='topright'));self.map.add(ScaleControl(position='bottomleft'))
        self.grid=GeoJSON(data={'type':'FeatureCollection','features':[]},name='Download grid',
            style={'color':'#235b9d','weight':1,'fillOpacity':0.02},hover_style={'color':'#ffbf00','weight':3,'fillOpacity':0.15})
        self.highlight=GeoJSON(data={'type':'FeatureCollection','features':[]},name='Selected download tile',
            style={'color':'#ffb000','weight':4,'fillOpacity':0.15})
        self.map.add(self.grid);self.map.add(self.highlight)
        self.raster=None;self.outline=None
        self.map.observe(lambda change:self._draw_grid(),names='bounds')
        self.map.on_interaction(self._map_click)
        self.grid.on_click(self._grid_click)
        self.map_slot=w.VBox([self.map])
        self.grid_toggle=w.Checkbox(value=True,description='Show download grid')
        self.grid_toggle.observe(lambda change:self._draw_grid(),names='value')
        self.open_button=w.Button(description='Open / reload map',icon='map',button_style='primary',layout=w.Layout(width='190px'))
        self.open_button.on_click(lambda _:self._action(self._open_map))
        self.check_display=w.Button(description='Check map display',icon='stethoscope',layout=w.Layout(width='190px'))
        self.check_display.on_click(lambda _:self._action(self._check_map_display))
        self.restore_display=w.Button(description='Restore map display',icon='refresh',layout=w.Layout(width='190px'))
        self.restore_display.on_click(lambda _:self._action(self._restore_map_display))
        self.display_status=w.HTML()
        self.failure_panel=w.HTML()
        self.failure_report=w.Button(description="Download failure report",icon="download",layout=w.Layout(width="220px"))
        self.failure_report.on_click(lambda _:self._action(self._save_mapping_failure))
        self.fit=w.Button(description='Zoom to study area')
        self.fit.on_click(lambda _:self._fit_map())
        self.tile_action=w.Button(description='Create tile download',icon='download',button_style='success',layout=w.Layout(width='220px'))
        self.tile_action.on_click(lambda _:self._action(self._download_tile))
        self.downloads=w.HTML()
        self.map_note=w.HTML('<p>Plain background. Your land-cover layer will appear here after map preparation.</p>')
        self.selection_note=w.HTML('<p>When the map is ready, click a grid square to choose a download.</p>')
        self.grid_note=w.HTML();self.legend=w.HTML(legend_html())
        self.auto_status=w.HTML('<small>Progress is checked automatically while this notebook is connected.</small>')
        self.notice=w.HTML()
        self.flow=w.HTML()
        self.next_step=w.HTML()
        self.mapping_review=w.VBox()
        self.download_review=w.VBox()
        self.map_tools=w.Accordion(children=[w.VBox([w.HBox([self.open_button,self.restore_display,self.fit],layout=w.Layout(flex_flow='row wrap')),
            w.HBox([self.check_display,self.refresh],layout=w.Layout(flex_flow='row wrap')),self.display_status])],selected_index=None)
        self.map_tools.set_title(0,'Map tools and diagnostics — optional')
        self.help_buttons=[]
        for label,message in [('Explain colours','What do the colours mean?'),('What next?','What should I do next?'),('Check status','status')]:
            button=w.Button(description=label)
            button.on_click(lambda _,text=message:self._action(lambda:assistant.say(text)))
            self.help_buttons.append(button)
        self.chat=w.Accordion(children=[w.VBox([w.HTML('<p>Optional: ask about colours, progress, the selected tile, or another year. You can do every essential step with the buttons above.</p>'),
            self.chat_mode,w.HBox(self.help_buttons),self.transcript,self.message,self.send])],selected_index=None)
        self.chat.set_title(0,'Ask the assistant — optional help')
        self.widget=w.VBox([w.HTML('<h2>Libya Land-Cover Assistant</h2><p>View the study-area map. Select the parts you need to download.</p>'),
            self.flow,self.next_step,self.step,self.connection_box,self.choices,self.mapping_review,self.activity,self.notice,
            self.progress,self.failure_panel,self.failure_report,self.auto_status,self.downloads,
            self.selection_note,self.tile_action,self.download_review,
            self.map_note,self.grid_toggle,self.map_slot,self.legend,self.grid_note,self.map_tools,
            w.HBox([self.backup,self.new],layout=w.Layout(flex_flow='row wrap')),
            self.chat,self.restore,self.support],layout=w.Layout(max_width='1150px',width='100%'))
        self._map_ready=True
        self.history=[]
        self.add({'message':'I can explain the legend, check live progress and prepare the tile selected on your map. To begin, connect Google and choose a year.'})
        self.sync()
        if auto_poll:
            try:self._poll_task=asyncio.get_running_loop().create_task(self._poll_loop())
            except RuntimeError:pass
        self._ensure_map()

    def add(self,reply,*,user=False):
        # One concise response; raw data stays in a single collapsed disclosure.
        message=reply.get('message','')
        if not user and reply.get('type') in {'error','execution_error'} and self._map_ready:
            self.notice.value='<p role="alert" style="padding:12px;background:#fff1df"><b>This step needs attention.</b> '+escape(str(message))+'</p>'
            if reply.get('diagnostic'):
                self.notice.value+='<details open><summary>Error details — share this text for support</summary><pre style="white-space:pre-wrap">'+escape(json.dumps(reply['diagnostic'],indent=2))+'</pre></details>'
        if not user:
            if reply.get('type')=='preview':
                message='Review the choices above, then use the green confirmation button.'
            elif reply.get('type')=='mapping':
                message='Your map is ready to explore.' if reply.get('state')=='completed' else 'Map preparation: '+reply.get('state','unknown')+'. Progress updates automatically.'
            elif reply.get('type')=='export':
                message='Your download is ready. Open the Drive link above.' if reply.get('state')=='completed' else 'Download status: '+reply.get('state','unknown')+'. Progress updates automatically.'
        body='<p style="white-space:pre-wrap">'+escape(str(message))+'</p>'
        details={k:v for k,v in reply.items() if k!='message'}
        if details:body+='<details><summary>Details</summary><pre style="white-space:pre-wrap">'+escape(json.dumps(details,indent=2))+'</pre></details>'
        self.history.append('<div style="padding:8px;border-bottom:1px solid #ddd"><b>'+('You' if user else 'Assistant')+'</b>'+body+'</div>')
        self.history=self.history[-12:];self.transcript.value=''.join(self.history)

    def _mapping(self):
        if not self.assistant.selected:return None
        return self.assistant.store.get(self.assistant.mapping_id())

    def sync(self):
        # One selected-job observation for all visible status/next-step text.
        current=self.assistant.describe() if self.assistant.selected else None
        super().sync(current=current)
        if not self._map_ready:return
        mapping=current if current and current['type']=='mapping' else self._mapping()
        ready=bool(mapping and mapping['state']=='completed')
        failed=bool(current and current['type']=='mapping' and current['state'] in {'failed','interrupted'})
        for widget in (self.map,self.map_slot,self.map_note,self.grid_note,self.selection_note,self.grid_toggle,self.open_button,self.restore_display,self.fit,self.check_display):
            self._visible(widget,not failed)
        self._visible(self.failure_report,failed)
        self._visible(self.failure_panel,failed)
        if failed:
            diagnostic={key:current.get(key) for key in ('job_id','state','error','engine_status','runner_failure')}
            self.failure_panel.value='<details open><summary>Why map preparation stopped</summary><p>Download the failure report below and send it to the project owner. This does not retry the job.</p><pre style="white-space:pre-wrap">'+escape(error_detail(json.dumps(diagnostic,indent=2)))+'</pre></details>'
        else:self.failure_panel.value=''
        if self.map_data and (not mapping or mapping['job_id']!=self.map_data['mapping_id']):self._clear_map()
        self.open_button.disabled=not (ready and self.live_ready) or self._busy or self._polling
        self.fit.disabled=self.map_data is None
        self.check_display.disabled=self.map_data is None or not self.live_ready or self._busy
        self.restore_display.disabled=self.map_data is None or self._busy
        self.tile_action.disabled=not (self.map_data and self.assistant.tile and self.live_ready) or self._busy
        self._visible(self.legend,self.map_data is not None)
        self._visible(self.tile_action,not failed)
        self._visible(self.refresh,bool(self.assistant.selected)) # Never hide progress behind another preview.
        self._visible(self.choices,self.live_ready and not self.assistant.pending and not mapping)
        self._visible(self.backup,ready)
        self._visible(self.new,bool(mapping and mapping['state'] in {'completed','failed','interrupted'}) and not self.assistant.pending)
        stage=1 if not self.live_ready else (3 if self.map_data else 2)
        self.flow.value='<p style="padding:12px;background:#eaf2f8;color:#17324d">'+ ' &nbsp; → &nbsp; '.join(
            ('<b>'+str(i)+'. '+label+'</b>') if i==stage else str(i)+'. '+label
            for i,label in enumerate(['Connect','Prepare map','Explore & download'],1))+'</p>'
        if not self.assistant.pending:
            heading={1:'Connect your Google account',2:'Choose your map',3:'Explore your map and choose a tile'}[stage]
            if self.live_ready and mapping and mapping['state'] in {'queued','running'}:heading='Preparing your map'
            if self.live_ready and ready and not self.map_data:heading='Open your prepared map'
            if failed:heading='Map preparation failed'
            self.step.value='<h3>'+heading+'</h3>'
        self.mapping_review.children=()
        self.download_review.children=()
        if self.assistant.pending:
            data=self.assistant.store.get(self.assistant.pending)['inputs']
            review_slot=self.mapping_review if data['action']=='mapping' else self.download_review
            review_slot.children=(self.review_box,)
            if data['action']=='mapping':
                self.preview.value='<h3>Ready to create your map?</h3>'+table([('Region',area_name(data['request'])),('Year',data['request']['target_year']),('Result','Study-area map with a legend and selectable download tiles')])
                self.confirm.description='Create map'
            else:
                w=data['plan']['spec']['pixel_window']
                self.preview.value='<h3>Download this selected tile?</h3>'+table([('Tile',f"{w['column']//1024}, {w['row']//1024}"),('Coverage','1024 × 1024 pixels · 10 metres per pixel'),('Destination','Your Google Drive'),('Outside the study area','NoData')])
                self.confirm.description='Create tile download'
        if self.assistant.selected:
            r=current;state=r['state']
            if r['type']=='mapping':
                if state=='completed':
                    msg=('Map preparation is saved. Map colours load separately as you explore below.' if self.map_data else
                         'Your prepared map is saved. Use Open / reload map below; do not create it again.' if self.live_ready else
                         'Your prepared map is saved. Connect Google to open it; do not create it again.')
                else:msg='Preparing your map. Keep this notebook connected.'
                if state in {'failed','interrupted'}:msg='Map preparation failed before the map could open. The recorded error is shown below.'
            else:
                msg='Your tile download is ready.' if state=='completed' else 'Your selected download is being prepared. You can continue exploring the map.'
                if state in {'failed','cancelled','submission_unknown'}:msg='The download needs attention. See Details and support; no automatic retry will start.'
            if r.get('source')=='uploaded_archive_snapshot':msg+=' This is a saved result; connect Google to check it live.'
            # Keep existing completed downloads visible even when a map is selected.
            self.progress.value='<h4>'+('Map preparation' if r['type']=='mapping' else 'Tile download')+'</h4><p>'+escape(msg)+'</p>'+render_reply({'state':state,'observed_at':r.get('observed_at'),'destination_uris':r.get('destination_uris',[])})
        self._show_next_step(mapping,current)
        self.downloads.value=download_cards(export_rows(self.assistant.store),self._poll_checks)
        # A chat-created or pre-update review remains a valid single confirmation.
        self._visible(self.tile_action,not failed and not (self.assistant.pending and
            self.assistant.store.get(self.assistant.pending)['inputs']['action']=='pilot'))
        self._draw_grid()

    def _show_next_step(self,mapping,current):
        # UI guidance only: reading saved state must never submit or poll work.
        draft=self.assistant.store.get(self.assistant.pending)['inputs'] if self.assistant.pending else None
        if self.last_error:
            text='Read the error details below. Your saved work is retained; do not create the map again to fix a display problem.'
        elif draft:
            text=('Review your map settings below, then click Create map.' if draft['action']=='mapping' else
                  'Review the selected tile above the map, then click Create tile download. Nothing is sent until you confirm.')
        elif current and current['type']=='export':
            state=current['state']
            if state=='completed':
                text=('Open the Google Drive link in Tile download and get the .tif file(s). Then click Save work for later.' if current.get('destination_uris') else
                      'The export is completed. Find the folder shown in Tile download in your Google Drive, then click Save work for later.')
            elif state in {'failed','cancelled','submission_unknown'}:
                text='The download needs attention. Open Details and support and save its report before retrying.'
            else:
                text=('Wait for your tile download. Progress updates automatically; do not submit it again.' if self.live_ready else
                      'Connect Google to check this saved download. Do not submit it again.')
        elif not self.live_ready:
            text='Click Connect Google and complete the sign-in prompt. If you have a saved-work ZIP, open Continue saved work below first.'
        elif mapping and mapping['state'] in {'queued','running'}:
            text='Wait while your map is prepared. Keep this notebook connected. No additional click is needed.'
        elif mapping and mapping['state'] in {'failed','interrupted'}:
            text='Map preparation stopped. Click Download failure report below. Do not restart the job before the cause is checked.'
        elif mapping and mapping['state']=='completed' and not self.map_data:
            text='Click Open / reload map to view your saved map. You do not need to create it again.'
        elif self.map_data:
            text=('Click Create tile download once. Status and the Drive link will appear in Downloads automatically.' if self.assistant.tile else
                  'Wait for colours to appear, then zoom in and click inside the study-area boundary to select one download tile. If only the boundary is visible, click Check map display.')
        else:
            text='Choose a year, then click Create map once.'
        self.next_step.value='<p role="status" style="padding:12px;border:1px solid #8ba9bf"><b>Next step:</b> '+escape(text)+'</p>'
        if current and current['type']=='export' and current['state']=='completed' and not current.get('destination_uris'):
            folder=current.get('drive_folder')
            self.progress.value+='<p>Google Drive folder: <b>'+escape(folder or 'No folder was recorded. Save the details for support.')+'</b></p>'

    def _clear_map(self):
        for layer in (self.raster,self.outline):
            if layer is not None:self.map.remove(layer)
        self.raster=self.outline=None;self.map_data=None;self.assistant.tile=None;self._attempted=None
        self.display_check=None;self.display_status.value=''
        self.grid.data={'type':'FeatureCollection','features':[]};self.highlight.data=self.grid.data
        self.selection_note.value='<p>Click a grid square after opening the map.</p>'
        self.map_note.value='<p>Plain background. Waiting for your current land-cover layer.</p>'

    def _open_map(self):
        try:
            result=self._mount_map()
            self.last_error=None;self.notice.value=''
            return result
        except MapDisplayError:raise
        except Exception as exc:raise MapDisplayError('open_map_interface',exc) from exc

    def _mount_map(self):
        data=self.assistant.open_map()
        self._install_map(data)
        self.sync()
        return {'message':'The land-cover layer was requested. Zoom in, select a blue square and click Create tile download once. Follow Downloads above.'}

    def _install_map(self,data,*,preserve_selection=False):
        """Publish a complete fresh widget, not incremental layer mutations.

        Colab may retain an empty/stale map view. Remount all layers together
        using cached geometry and URL; this does not call the mapping backend.
        """
        import ipywidgets as w
        from ipyleaflet import TileLayer,GeoJSON,LayersControl,ScaleControl
        center,zoom=view_for_bounds(data['bounds'])
        raster=TileLayer(url=data['url'],name='Land cover '+str(data['request']['target_year']),attribution='Google Earth Engine · The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind.',max_zoom=22,bounds=data['bounds'],no_wrap=True)
        outline=GeoJSON(data=data['outline'],name='Study-area boundary',style={'color':'#222','weight':2,'fillOpacity':0})
        grid_data,_=visible_grid(data['bounds'],data['area_xy']) if self.grid_toggle.value else ({'type':'FeatureCollection','features':[]},False)
        grid=GeoJSON(data=grid_data,name='Download grid',style={'color':'#235b9d','weight':1,'fillOpacity':0.02},hover_style={'color':'#ffbf00','weight':3,'fillOpacity':0.15})
        tile=self.assistant.tile if preserve_selection and self.assistant.map_id==data['mapping_id'] else None
        highlight=GeoJSON(data={'type':'FeatureCollection','features':[feature(tile['spec'])] if tile else []},name='Selected download tile',style={'color':'#ffb000','weight':4,'fillOpacity':0.15})
        fresh=NotebookMap(layers=(raster,outline,grid,highlight),center=center,zoom=zoom,
            scroll_wheel_zoom=True,layout=w.Layout(height='520px',width='100%'))
        fresh.add(LayersControl(position='topright'));fresh.add(ScaleControl(position='bottomleft'))
        old_map=self.map
        self.map=fresh;self.raster=raster;self.outline=outline;self.grid=grid;self.highlight=highlight
        self.assistant.tile=tile;self.assistant.map_id=data['mapping_id'];self._attempted=data['mapping_id']
        self.map_data=data
        fresh.observe(lambda change:self._draw_grid(),names='bounds')
        fresh.on_interaction(self._map_click);grid.on_click(self._grid_click)
        self.map_slot.children=(fresh,)
        old_map.close()
        self.display_check=None;self.display_status.value=''
        self.selection_note.value=('<p><b>Selected tile: '+f"{tile['spec']['pixel_window']['column']//1024}, {tile['spec']['pixel_window']['row']//1024}"+'</b> · 10.24 × 10.24 km · 10 m pixels · TIFF to your Google Drive. Click Create tile download once.</p>' if tile else '<p><b>1.</b> Select a blue square. <b>2.</b> Click Create tile download. The link appears in Downloads automatically.</p>')
        self.map_note.value='<p><b>'+escape(area_name(data['request']))+' · '+str(data['request']['target_year'])+'</b> — Zoom in and select a blue square. Map colours load as you explore; grey areas may still be loading.</p>'

    def _fit_map(self):
        if self.map_data:
            center,zoom=view_for_bounds(self.map_data['bounds'])
            with self.map.hold_sync():
                self.map.center=center;self.map.zoom=zoom

    def _restore_map_display(self):
        if not self.map_data:raise ValueError('Open your prepared map first.')
        self._install_map(self.map_data,preserve_selection=True)
        return {'message':'The map window was rebuilt and centred on the study area. No mapping or export was started. Colours still depend on Earth Engine tile responses.'}

    def _check_map_display(self):
        from .display_diagnostics import check_display_tile
        if not self.map_data:raise ValueError('Open your prepared map first.')
        self.assistant.before_live()
        check=check_display_tile(self.map_data['url'],self.map.center,self.map.zoom)
        check.update(observed_at=now(),mapping_job_id=self.map_data['mapping_id'])
        self.display_check=check
        self.display_status.value='<p>'+escape(check['message'])+'</p><details><summary>Map display check — share this for support</summary><pre style="white-space:pre-wrap">'+escape(json.dumps(check,indent=2))+'</pre></details>'
        from .bundle import write_json
        write_json(self.assistant.store.root/'landcover-display-check.json',check)
        return {'type':'display_check','message':check['message'],'diagnostic':check}

    def _draw_grid(self):
        if not self._map_ready or not self.map_data:return
        bounds=self.map.bounds if valid_bounds(self.map.bounds) else self.map_data['bounds']
        data,limited=visible_grid(bounds,self.map_data['area_xy']) if self.grid_toggle.value else ({'type':'FeatureCollection','features':[]},False)
        self.grid.data=data
        self.grid_note.value='<p>Zoom in to see the download grid. You can still click a location to select its tile.</p>' if limited else '<p>Click a blue grid square. The selected download is outlined in gold. Edge tiles contain NoData outside the study area.</p>'

    def _pick(self,spec):
        if self._busy or not self.map_data:return
        if self.assistant.tile and self.assistant.tile['spec']==spec:return
        self.assistant.choose_tile(spec,self.map_data['mapping_id'])
        self.highlight.data={'type':'FeatureCollection','features':[feature(spec)]}
        w=spec['pixel_window']
        self.selection_note.value=f"<p><b>Selected tile: {w['column']//1024}, {w['row']//1024}</b> · 10.24 × 10.24 km · 10 m pixels · TIFF to your Google Drive. Click Create tile download once.</p>"
        self.sync()

    def _create_map(self):
        draft=self.assistant.prepare_mapping({'target_year':self.year.value})
        return self.assistant.confirm(draft['draft_id']) if draft.get('type')=='preview' else draft

    def _download_tile(self):
        # The labelled button is the user's confirmation; selecting a cell is not.
        draft=self.assistant.prepare_pilot()
        return self.assistant.confirm(draft['draft_id']) if draft.get('type')=='preview' else draft

    def _map_click(self,**event):
        if event.get('type')=='click' and self.map_data and self.grid_toggle.value:
            lat,lon=event['coordinates'];self._pick(tile_at(lon,lat))

    def _grid_click(self,**event):
        props=event.get('properties') or event.get('feature',{}).get('properties',{})
        if 'column' in props and 'row' in props:self._pick(tile_spec(props['column'],props['row']))

    def _action(self,action):
        if self._busy or self._closed:return
        self._busy=True
        def observed():
            try:return action()
            except Exception as exc:
                display_error=isinstance(exc,MapDisplayError)
                self.last_error={'observed_at':now(),'stage':exc.stage if display_error else 'interface_action',
                    'error_type':exc.error_type if display_error else type(exc).__name__,
                    'detail':exc.detail if display_error else error_detail(exc),
                    'selected_job_id':self.assistant.selected}
                return {'type':'error','message':('The land-cover display could not open. Your prepared map is still saved; do not run mapping again. See the error details below.' if display_error else 'This step could not finish. See the error details below.'),
                    'diagnostic':self.last_error}
        try:super()._action(observed)
        finally:
            self._busy=False
            if self._map_ready:
                self.sync();self._ensure_map()
                self._poll_wake.set()
                self._checkpoint()

    def _save_mapping_failure(self):
        path=self.assistant.store.root/'landcover-mapping-failure.json'
        self.assistant.save_report(path)
        if self.download:self.download(str(path))
        return {'message':'Failure report downloaded. No mapping or export was started.'}

    def _save(self,backup):
        if backup:
            from .workspace import save_workspace
            path=save_workspace(self.assistant,self.assistant.store.root/'landcover-workspace.zip',history=self.history)
            if self.download:self.download(str(path))
            return {'message':'All saved maps, download records and support details were saved. Open this ZIP with Continue saved work next time. TIFFs remain in Google Drive.'}
        if self.assistant.selected:
            current=self.assistant.describe()
            if current.get('type')=='export' and current.get('error'):return super()._save(False)
        if not backup and self.display_check and not self.last_error:
            path=self.assistant.store.root/'landcover-display-check.json'
            if self.download:self.download(str(path))
            return {'message':'Map display check saved. No map or export was started.'}
        if backup or not self.last_error:return super()._save(backup)
        from .bundle import write_json
        path=self.assistant.store.root/'landcover-display-error.json'
        write_json(path,self.last_error)
        if self.download:self.download(str(path))
        return {'message':'Display error details saved. Your map and downloads have not been changed.'}

    def _checkpoint(self):
        from .workspace import save_workspace
        signature=tuple((j['job_id'],j['revision']) for j in self.assistant.store.list())
        if not signature or signature==self._backup_signature:return
        try:
            save_workspace(self.assistant,self.assistant.store.root/'landcover-workspace.zip',history=self.history)
            self._backup_signature=signature
        except Exception as exc:
            self.auto_status.value='<small>Work remains in this session. The recovery ZIP could not update: '+escape(error_detail(exc))+'</small>'

    def _upload(self,change):
        if not change['new']:return
        from .workspace import is_workspace,restore_workspace,MAX_WORKSPACE_BYTES
        def action():
            entries=change['new']
            if len(entries)!=1:raise ValueError('Choose one saved-work ZIP.')
            content=bytes(entries[0]['content'])
            if len(content)>MAX_WORKSPACE_BYTES:raise ValueError('Saved-work ZIP exceeds 512 MB.')
            path=self.assistant.store.root/'assistant-upload.zip';path.write_bytes(content)
            try:return restore_workspace(self.assistant,path) if is_workspace(path) else self.assistant.import_archive(path)
            finally:path.unlink(missing_ok=True)
        self._action(action);self.upload.value=();self.restore.selected_index=None

    def _send(self,_):
        text=self.message.value.strip()
        if not text:return
        self.message.value='';self.add({'message':text},user=True)
        def action():
            reply=self.assistant.say(text)
            return self._open_map() if reply.get('type')=='show_map' else reply
        self._action(action)

    def _discard(self,_):
        # Discard only the proposal; never lose the current download selection.
        mapping_draft=self.assistant.pending and self.assistant.store.get(self.assistant.pending)['inputs']['action']=='mapping'
        self.assistant.discard();self.sync()
        if mapping_draft:self._visible(self.choices,self.live_ready)

    def _ensure_map(self):
        if not self._map_ready or not self.live_ready or self._busy or self._closed:return
        if self._browser_updates:return # Colab mounts inside the next browser callback.
        mapping=self._mapping()
        if not mapping or mapping['state']!='completed':return
        key=mapping['job_id']
        if (self.map_data and self.map_data['mapping_id']==key) or self._attempted==key:return
        try:loop=asyncio.get_running_loop()
        except RuntimeError:return
        self._attempted=key
        async def load():
            await asyncio.sleep(0)
            if not self._closed and self._mapping() and self._mapping()['job_id']==key:self._action(self._open_map)
        self._load_task=loop.create_task(load())

    def _poll_candidate(self):
        rows=export_rows(self.assistant.store)
        candidates=[]
        for row in rows:
            state=row['state']
            if state in ACTIVE:candidates.append(row)
            elif state=='completed' and not row.get('destination_uris') and row.get('operation_name'):
                tries,at=self._link_checks.get(row['record_id'],(0,0))
                if tries<3 and time.monotonic()-at>=60:candidates.append(row)
        if not candidates:return None
        job=candidates[self._poll_index%len(candidates)];self._poll_index+=1
        return job

    def _read_export(self,job):
        """Read/reconcile one existing export. Never submit, retry or cancel."""
        identifier=job['record_id']
        if job['snapshot']:
            from .workspace import recover_saved_export
            record=self.assistant.store.get(identifier)
            return recover_saved_export(self.assistant.store,record)['job_id']
        if job['state']=='completed':
            tries,_=self._link_checks.get(identifier,(0,0))
            self._link_checks[identifier]=(tries+1,time.monotonic())
            poll_export(self.assistant.store,identifier,refresh_destination=True)
        else:poll_export(self.assistant.store,identifier)
        return identifier

    def _read_observed(self,job,restored):
        identifier=job['record_id']
        if self.assistant.selected==identifier:self.assistant.selected=restored
        self._poll_checks[identifier]={'at':now()}

    async def _poll_once(self):
        """Read-only remote progress; ordinary notebook fallback."""
        job=self._poll_candidate()
        if not job:return
        self._polling=True
        try:
            restored=await asyncio.to_thread(self._read_export,job)
            self._read_observed(job,restored)
        except Exception as exc:
            self._poll_checks[job['record_id']]={'at':now(),'error':error_detail(exc)}
        finally:self._polling=False

    def _browser_tick(self):
        """Colab invokes this read/display-only callback without user clicks.

        It runs synchronously in an active frontend request, without depending
        on an idle asyncio task or its background widget delivery.
        """
        if self._closed:return {'closed':True}
        if self._busy or self._polling or self._browser_ticking:return {'busy':True}
        from .colab_updates import send_widget_tree
        self._browser_ticking=True
        try:
            self.sync()
            mapping=self._mapping()
            if (self.live_ready and mapping and mapping['state']=='completed' and
                    self.map_data is None and self._attempted!=mapping['job_id']):
                self._attempted=mapping['job_id']
                self._action(self._open_map)
            stamp=time.monotonic()
            if self.live_ready and (self._browser_last_poll is None or stamp-self._browser_last_poll>=self.poll_seconds):
                self._browser_last_poll=stamp
                job=self._poll_candidate()
                if job:
                    self._polling=True
                    try:self._read_observed(job,self._read_export(job))
                    except Exception as exc:self._poll_checks[job['record_id']]={'at':now(),'error':error_detail(exc)}
                    finally:self._polling=False
            self.sync();self._checkpoint()
            self._last_view_check=now()
            self.auto_status.value='<small>Map and download status update automatically. Last checked: '+escape(self._last_view_check)+'</small>'
            # Explicit sends are necessary even when Python values did not change:
            # the preceding background message may never have reached Colab.
            send_widget_tree(self.widget)
            return {'closed':False,'checked_at':self._last_view_check}
        except Exception as exc:
            self.auto_status.value='<small>Display update could not finish: '+escape(error_detail(exc))+'</small>'
            send_widget_tree(self.widget)
            return {'closed':False,'error':error_detail(exc)}
        finally:self._browser_ticking=False

    async def _poll_loop(self):
        while not self._closed:
            if self._closed:return
            try:
                if self.live_ready and not self._busy and not self._browser_updates:await self._poll_once()
                if not self._closed and not self._busy and not self._browser_updates:
                    self.sync();self._ensure_map();self._checkpoint()
                    self.auto_status.value='<small>Downloads update automatically while this notebook is connected. No refresh click is needed.</small>'
            except Exception as exc:
                if not self._closed:self.auto_status.value='<small>Automatic check will retry. '+escape(error_detail(exc))+'</small>'
            try:await asyncio.wait_for(self._poll_wake.wait(),timeout=self.poll_seconds)
            except asyncio.TimeoutError:pass
            self._poll_wake.clear()

    def close(self):
        from .colab_updates import detach_colab_updates
        detach_colab_updates(self)
        super().close()
        if self._map_ready:self.map.close()
        for task in (self._poll_task,self._load_task):
            if task:task.cancel()


def display_map_assistant(assistant,*,download=None,connect=None):
    from IPython.display import display
    ui=MapUI(assistant,download=download,connect=connect)
    display(ui.widget)
    from .colab_updates import attach_colab_updates
    attach_colab_updates(ui)
    return ui


def restore_live_workspace(previous):
    """Replace an existing UI in this runtime using its cached prepared map."""
    if previous._busy or previous._polling:
        raise ValueError('The assistant is busy. Wait for its current action, then run the repair cell again.')
    if previous.map_data and previous.assistant.mapping_id()!=previous.map_data['mapping_id']:
        raise ValueError('Select the prepared map before restoring its display.')
    from IPython.display import display
    assistant=previous.assistant
    old_guard=assistant.before_live
    fresh=None
    try:
        fresh=MapUI(assistant,download=previous.download,connect=previous.connector,auto_poll=False,preserve_draft=True)
        fresh.live_ready=previous.live_ready
        fresh.connection.description='Google connected' if fresh.live_ready else 'Connect Google'
        fresh.year.unobserve(fresh._change_year,names='value')
        fresh.year.value=previous.year.value
        fresh.year.observe(fresh._change_year,names='value')
        fresh.grid_toggle.value=previous.grid_toggle.value
        fresh.message.value=previous.message.value
        if previous.map_data:fresh._install_map(previous.map_data,preserve_selection=True)
        if previous.map_data:
            from .notebook_map import finite_number
            if all(finite_number(v) for v in previous.map.center) and finite_number(previous.map.zoom):
                with fresh.map.hold_sync():
                    fresh.map.center=previous.map.center;fresh.map.zoom=previous.map.zoom
        fresh.history=list(previous.history);fresh.transcript.value=''.join(fresh.history)
        fresh._poll_checks=dict(getattr(previous,'_poll_checks',{}))
        fresh.sync()
    except Exception:
        assistant.before_live=old_guard
        if fresh:fresh.close()
        raise
    previous.close()
    try:fresh._poll_task=asyncio.get_running_loop().create_task(fresh._poll_loop())
    except RuntimeError:pass
    display(fresh.widget)
    from .colab_updates import attach_colab_updates
    attach_colab_updates(fresh)
    if fresh._browser_updates:fresh._browser_tick()
    fresh._checkpoint()
    fresh._ensure_map()
    return fresh
