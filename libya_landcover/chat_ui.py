"""English notebook widgets: no public server, tunnel, API key or code editing."""

from html import escape
import json
from pathlib import Path
from urllib.parse import urlparse

from .chat_language import HELP, GUIDED_HELP, GuidedParser
from .jobs import MAX_BUNDLE_BYTES


def table(rows):
    return '<table style="width:100%;text-align:left">' + ''.join(
        '<tr><th style="padding:5px;vertical-align:top">' + escape(str(key)) +
        '</th><td style="padding:5px;overflow-wrap:anywhere">' + escape(str(value)) + '</td></tr>'
        for key, value in rows) + '</table>'


def render_reply(reply):
    """Escape all text, keep raw metadata secondary, link only actual Drive URLs."""
    message = '<div style="white-space:pre-wrap">' + escape(str(reply.get('message', ''))) + '</div>'
    rows = []
    names = {'state':'Status', 'source':'Evidence source', 'observed_at':'Recorded at',
             'coverage':'Coverage', 'drive_folder':'Drive folder'}
    values = {'uploaded_archive_snapshot':'Imported backup (not a live query)',
              'local_ledger':'Saved job record', 'pilot_window_only':'One pilot window only',
              'requested_full_region':'Full-region export request'}
    for key, label in names.items():
        if reply.get(key) is not None:
            rows.append((label, values.get(str(reply[key]), reply[key])))
    if reply.get('type') == 'preview':
        data = reply['settings']
        if data['action'] == 'mapping':
            request = data['request']
            rows += [('Action','Prepare land-cover maps'), ('Target year',request['target_year']),
                ('Boundary',request['aoi_asset']), ('Training data',request['training_asset']),
                ('Earth Engine project',data['project']), ('Years combined',request['year_count']),
                ('Fallback year',request['fallback_year']), ('Trees',request['trees']),
                ('Training fraction',request['train_fraction']), ('Class field',request['class_field'])]
        else:
            plan = data['plan']; spec = plan['spec']; window = spec['pixel_window']
            rows += [('Action','Export one pilot TIFF'), ('Size',f"{window['width']} × {window['height']} pixels"),
                ('Resolution','10 metres'), ('Projection',spec['crs']), ('Window bounds',plan.get('bounds_xy'))]
    if reply.get('type') == 'mapping' and reply.get('outputs'):
        rows.append(('Available map graphs',len(reply['outputs'])))
    if reply.get('type') == 'jobs':
        rows += [(j['kind'] + ' · ' + j['state'],j['job_id']) for j in reply.get('jobs',[])]
    links = []
    for uri in reply.get('destination_uris',[]):
        if isinstance(uri,str):
            parsed = urlparse(uri)
            if parsed.scheme == 'https' and parsed.netloc == 'drive.google.com':
                links.append('<p><a target="_blank" rel="noopener noreferrer" href="' + escape(uri,quote=True) + '">Open result in Google Drive</a></p>')
    details = {k:v for k,v in reply.items() if k != 'message'}
    metadata = ('<details><summary>Technical details</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">' +
        escape(json.dumps(details,indent=2,ensure_ascii=False)) + '</pre></details>') if details else ''
    return message + table(rows) + ''.join(links) + metadata


class ChatUI:
    def __init__(self, assistant, *, download=None, connect=None):
        import ipywidgets as w
        self.assistant, self.download, self.connector = assistant, download, connect
        self.live_ready = connect is None
        if connect is not None:
            assistant.before_live = self._require_connection
        assistant.discard()
        self._draft_id = None
        self.history = []
        self.transcript = w.HTML()
        self.message = w.Textarea(placeholder='Ask about your result, or ask me to prepare a map…',
            layout=w.Layout(width='100%',height='75px'))
        self.send = w.Button(description='Send',button_style='primary')
        self.confirm = w.Button(description='Run reviewed request',button_style='warning',disabled=True,
            layout=w.Layout(width='200px'))
        self.discard = w.Button(description='Discard preview')
        self.refresh = w.Button(description='Refresh status')
        self.select = w.Dropdown(description='Your work',options=[('Choose a result','')],layout=w.Layout(width='100%'))
        self.report = w.Button(description='Download report')
        self.backup = w.Button(description='Download backup')
        self.status = w.Button(description='Show status')
        self.result = w.Button(description='Show result')
        self.pilot = w.Button(description='Prepare pilot')
        self.prepare = w.Button(description='Prepare map')
        self.year = w.Dropdown(description='Year',options=list(range(2024,2016,-1)),value=assistant.profile['target_year'])
        self.upload = w.FileUpload(accept='.zip',multiple=False,description='Upload result ZIP',layout=w.Layout(width='200px'))
        self.connection = w.Button(description='Connect Earth Engine',layout=w.Layout(width='200px'),disabled=connect is None)
        self.connection_output = w.Output()
        self.activity = w.HTML()
        self.upload.observe(self._upload,names='value')
        self.send.on_click(self._send)
        self.confirm.on_click(self._confirm)
        self.discard.on_click(self._discard)
        self.refresh.on_click(lambda _:self._action(assistant.refresh))
        self.status.on_click(lambda _:self._action(assistant.describe))
        self.result.on_click(lambda _:self._action(assistant.describe))
        self.prepare.on_click(lambda _:self._action(lambda:assistant.prepare_mapping({'target_year':self.year.value})))
        self.pilot.on_click(lambda _:self._action(assistant.prepare_pilot))
        self.report.on_click(lambda _:self._action(lambda:self._save(False)))
        self.backup.on_click(lambda _:self._action(lambda:self._save(True)))
        self.connection.on_click(self._connect)
        self.select.observe(self._selection,names='value')
        mode = w.HTML('<h3>Libya Land-Cover Assistant</h3><p>' + escape(assistant.parser.label) +
            '</p><p>Upload a previous result to explore it, or prepare a new map. Only Run starts new work.</p>')
        profile = w.HTML(table([('Project',assistant.profile['project']),('Boundary',assistant.profile['aoi_asset']),
                              ('Training data',assistant.profile['training_asset'])]))
        profile_panel = w.Accordion(children=[profile],selected_index=None)
        profile_panel.set_title(0,'Configured study area and data')
        self.widget = w.VBox([mode,profile_panel,w.HBox([self.upload,self.connection]),self.connection_output,
            self.select,w.HBox([self.status,self.result,self.refresh]),self.transcript,self.activity,self.message,
            w.HBox([self.send,self.confirm,self.discard]),w.HBox([self.year,self.prepare,self.pilot]),
            w.HBox([self.report,self.backup])])
        self.add({'message':GUIDED_HELP if isinstance(assistant.parser,GuidedParser) else HELP})
        if assistant.selected:
            self.add(assistant.describe())
        self.sync()

    def _require_connection(self):
        if not self.live_ready:
            raise ValueError('Click Connect Earth Engine and complete Google sign-in first. Your preview is still available.')

    def _connect(self,_):
        if self.connector is None:
            return
        self.live_ready = False
        def action():
            with self.connection_output:
                self.connection_output.clear_output(wait=True)
                self.connector()
            self.live_ready = True
            self.connection.description = 'Earth Engine connected'
            return {'message':'Earth Engine is connected. No model or export was started.'}
        self._action(action)

    def _upload(self,change):
        if not change['new']:
            return
        def action():
            entries = change['new']
            if len(entries) != 1:
                raise ValueError('Select one result ZIP at a time.')
            entry = entries[0] # ipywidgets 8 is required
            content = bytes(entry['content'])
            if len(content) > MAX_BUNDLE_BYTES:
                raise ValueError('Result ZIP exceeds the upload size limit.')
            path = self.assistant.store.root / 'assistant-upload.zip'
            path.write_bytes(content)
            try:
                return self.assistant.import_archive(path)
            finally:
                path.unlink(missing_ok=True)
        self._action(action)
        self.upload.value = ()

    def add(self,reply,*,user=False):
        self.history.append('<div style="border-bottom:1px solid #ddd;padding:12px">' +
            ('<b>You</b>' if user else '<b>Assistant</b>') + render_reply(reply) + '</div>')
        self.history = self.history[-30:]
        self.transcript.value = ''.join(self.history)

    def sync(self):
        self._draft_id = self.assistant.pending
        self.confirm.disabled = self._draft_id is None
        labels = {'mapping':'Mapping','export':'Export','assistant_snapshot':'Imported pilot'}
        options = [(labels[j['kind']] + ' · ' + j['state'] + ' · ' + j['job_id'][:8],j['job_id'])
                   for j in self.assistant.jobs()]
        self.select.unobserve(self._selection,names='value')
        try:
            self.select.options = [('Choose a result',''),*options]
            self.select.value = self.assistant.selected or ''
        finally:
            self.select.observe(self._selection,names='value')

    def _action(self,action):
        controls = (self.send,self.confirm,self.refresh,self.report,self.backup,self.discard,
                    self.status,self.result,self.prepare,self.pilot,self.upload,self.connection,self.select,self.year)
        for control in controls:
            control.disabled = True
        self.activity.value = '<p>Working… Please wait. No repeated clicks are needed.</p>'
        try:
            self.add(action())
        except (ValueError,KeyError) as exc:
            self.add({'type':'error','message':str(exc)})
        except Exception as exc:
            self.add({'type':'error','message':'The operation did not finish. Check the connection and job status before retrying.',
                      'error_type':type(exc).__name__})
        finally:
            for control in controls:
                control.disabled = False
            self.connection.disabled = self.connector is None
            self.activity.value = ''
            self.sync()

    def _send(self,_):
        text = self.message.value
        self.message.value = ''
        self.add({'message':text},user=True)
        self._action(lambda:self.assistant.say(text))

    def _confirm(self,_):
        identifier = self._draft_id
        self._action(lambda:self.assistant.confirm(identifier))

    def _discard(self,_):
        self.assistant.discard()
        self.add({'message':'Preview discarded. Existing running jobs are not cancelled.'})
        self.sync()

    def _selection(self,change):
        if change['new']:
            self.assistant.discard()
            self._action(lambda:self.assistant.describe(change['new']))

    def _save(self,backup):
        output = self.assistant.store.root / ('assistant-result.zip' if backup else 'assistant-report.json')
        path = self.assistant.save_backup(output) if backup else self.assistant.save_report(output)
        if self.download:
            self.download(str(path))
        return {'message':'Your file is ready. A backup contains graphs and job information; download the TIFF separately from Drive.',
                'file':str(Path(path))}


def display_chat(assistant,*,download=None,connect=None):
    from IPython.display import display
    ui = ChatUI(assistant,download=download,connect=connect)
    display(ui.widget)
    return ui
