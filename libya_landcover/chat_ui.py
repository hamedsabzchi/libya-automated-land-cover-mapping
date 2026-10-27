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


def area_name(request):
    from .assistant import TRIPOLI
    return ('Tripoli' if request.get('aoi_asset') == TRIPOLI['aoi_asset'] and
            request.get('training_asset') == TRIPOLI['training_asset'] else 'Custom study area')


def friendly_reply(reply):
    """Keep provenance available while giving nontechnical users a next step."""
    reply = dict(reply)
    kind, state = reply.get('type'), reply.get('state')
    if kind == 'preview':
        if reply['settings']['action'] == 'mapping':
            request = reply['settings']['request']
            reply['message'] = f"Ready to prepare {area_name(request)} for {request['target_year']}. Review the card above, then click Start mapping."
        else:
            reply['message'] = 'Ready to export a small sample of your map. Review the card above, then click Create sample file.'
    elif kind == 'mapping':
        reply['message'] = {
            'queued': 'Your map is waiting to start. Keep this notebook open and use Check progress below.',
            'running': 'Your map is being prepared. Keep this notebook open and use Check progress below.',
            'completed': 'Map preparation finished. Next, click Prepare sample download to create a small downloadable file.',
            'failed': 'Map preparation stopped. Open Details and support below to save the error report. No new run has started.',
        }.get(state, 'Your mapping request is recorded. Check its status below.')
    elif kind == 'export':
        if state == 'completed':
            reply['message'] = ('Your sample file is ready. Open the Google Drive folder below and download its .tif file(s). '
                'This download covers one small window, not the whole study area.') if reply.get('coverage') == 'pilot_window_only' else 'The recorded export has finished. Open its Google Drive folder below.'
        elif state in {'failed', 'cancelled', 'unknown'}:
            reply['message'] = 'The download is not ready. Check the status and save a report from Details and support before retrying.'
        else:
            reply['message'] = 'Google Earth Engine is creating your download. Use Check progress below; do not start it again.'
        if reply.get('source') == 'uploaded_archive_snapshot':
            reply['message'] += ' This is a saved result from an earlier session.'
    return reply


def simple_reply(reply):
    """Short chat bubbles; full server evidence is collapsed, never discarded."""
    if reply.get('type') in {'mapping', 'export', 'preview', 'jobs'}:
        return ('<p>' + escape(str(reply.get('message', ''))) + '</p><details><summary>Technical details</summary>' +
                render_reply(reply) + '</details>')
    return render_reply(reply)


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
        self._closed = False
        self.transcript = w.HTML()
        self.message = w.Textarea(placeholder='For example: Prepare a map for Tripoli for 2024',
            layout=w.Layout(width='100%', height='65px'))
        self.send = w.Button(description='Send', button_style='primary')
        self.confirm = w.Button(description='Start mapping', button_style='success', disabled=True,
            layout=w.Layout(width='190px'))
        self.discard = w.Button(description='Change my choices')
        self.refresh = w.Button(description='Check progress', button_style='primary')
        self.select = w.Dropdown(description='Saved work', options=[('Choose saved work', '')], layout=w.Layout(width='100%'))
        self.report = w.Button(description='Save error / details')
        self.backup = w.Button(description='Save work for later', layout=w.Layout(width='190px'))
        self.status = w.Button(description='Show status')
        self.result = w.Button(description='Show result')
        self.pilot = w.Button(description='Prepare sample download', button_style='primary', layout=w.Layout(width='230px'))
        self.prepare = w.Button(description='Review my map', button_style='primary', layout=w.Layout(width='190px'))
        self.year = w.Dropdown(description='Year', options=list(range(2024, 2016, -1)), value=assistant.profile['target_year'])
        self.region = w.Dropdown(description='Region', options=[area_name(assistant.profile)], disabled=True)
        self.upload = w.FileUpload(accept='.zip', multiple=False, description='Open saved work', layout=w.Layout(width='190px'))
        self.connection = w.Button(description='Connect Google', button_style='primary', layout=w.Layout(width='190px'), disabled=connect is None)
        self.connection_output = w.Output()
        self.activity = w.HTML()
        self.step = w.HTML()
        self.preview = w.HTML()
        self.progress = w.HTML()
        self.new = w.Button(description='Start another map')
        self.chat_mode = w.HTML('<p><b>English chat ready.</b> Replies may take about half a minute.</p>' if not isinstance(assistant.parser, GuidedParser)
            else '<p><b>Chat could not load.</b> You can still use the map buttons. Rerun Start assistant to retry chat.</p>')
        self.upload.observe(self._upload, names='value')
        self.send.on_click(self._send)
        self.confirm.on_click(self._confirm)
        self.discard.on_click(self._discard)
        self.refresh.on_click(lambda _: self._action(assistant.refresh))
        self.status.on_click(lambda _: self._action(assistant.describe))
        self.result.on_click(lambda _: self._action(assistant.describe))
        self.prepare.on_click(lambda _: self._action(lambda: assistant.prepare_mapping({'target_year': self.year.value})))
        self.pilot.on_click(lambda _: self._action(assistant.prepare_pilot))
        self.report.on_click(lambda _: self._action(lambda: self._save(False)))
        self.backup.on_click(lambda _: self._action(lambda: self._save(True)))
        self.connection.on_click(self._connect)
        self.select.observe(self._selection, names='value')
        self.year.observe(self._change_year, names='value')
        self.new.on_click(self._new)
        profile = w.HTML(table([('Earth Engine project', assistant.profile['project']),
            ('Boundary', assistant.profile['aoi_asset']), ('Training data', assistant.profile['training_asset'])]))
        support = w.VBox([w.HTML('<p>The project owner configures access to the study area. If Google cannot connect, ask them to grant your account access.</p>'),
            profile, self.select, w.HBox([self.status, self.result, self.report]),
            w.HTML('<p>Save work for later downloads a small recovery file, not the map image. Open it here next time. '
                   'An unfinished map cannot be resumed after Colab deletes its session. '
                   'Free Colab sessions and resources are limited. Keep the notebook open while mapping.</p>')])
        self.support = w.Accordion(children=[support], selected_index=None)
        self.support.set_title(0, 'Details and support')
        self.restore = w.Accordion(children=[w.VBox([w.HTML('<p>Optional: choose a file previously downloaded with Save work for later. '
            'You do not need any file to start a new map.</p>'), self.upload])], selected_index=None)
        self.restore.set_title(0, 'Continue saved work (optional)')
        self.connection_box = w.VBox([w.HTML('<p>Connect the Google account approved for this project. Follow the Google sign-in prompt.</p>'),
            self.connection, self.connection_output])
        self.choices = w.VBox([w.HTML('<p>Choose a year. Tripoli is the study area configured for this notebook.</p>'),
            w.HBox([self.region, self.year], layout=w.Layout(flex_flow='row wrap')), self.prepare])
        self.review_box = w.VBox([self.preview, w.HBox([self.confirm, self.discard], layout=w.Layout(flex_flow='row wrap'))])
        self.work_box = w.VBox([self.progress, self.refresh, self.pilot, self.backup, self.new])
        self.widget = w.VBox([
            w.HTML('<h2>Libya Land-Cover Assistant</h2><p>Create a land-cover map with the configured data and download a small sample.</p>'
                   '<p><b>Current download: a sample window only.</b> Whole-region download is not available yet.</p>'),
            self.step, self.connection_box, self.choices, self.review_box, self.work_box, self.activity,
            w.HTML('<h3>Ask the assistant</h3>'), self.chat_mode, self.transcript, self.message, self.send,
            self.restore, self.support], layout=w.Layout(max_width='880px', width='100%'))
        self.add({'message': 'Welcome. You can start a new map here without uploading anything. Connect Google above, then choose a year. You can also ask me to prepare a map or explain its status.'})
        if not assistant.selected and assistant.jobs():
            assistant.selected = assistant.jobs()[-1]['job_id']
        self.sync()

    @staticmethod
    def _visible(widget, visible):
        widget.layout.display = '' if visible else 'none'

    def _require_connection(self):
        if not self.live_ready:
            raise ValueError('Connect Earth Engine using Connect Google above. Your reviewed choices are still available.')

    def _connect(self, _):
        if self.connector is None:
            return
        self.live_ready = False
        def action():
            with self.connection_output:
                self.connection_output.clear_output(wait=True)
                self.connector()
            self.live_ready = True
            self.connection.description = 'Google connected'
            return {'message': 'Connected. Choose your year and click Review my map. Nothing has started yet.'}
        self._action(action)

    def _upload(self, change):
        if not change['new']:
            return
        def action():
            entries = change['new']
            if len(entries) != 1:
                raise ValueError('Choose one saved-work file.')
            content = bytes(entries[0]['content'])
            if len(content) > MAX_BUNDLE_BYTES:
                raise ValueError('This saved-work file exceeds the size limit.')
            path = self.assistant.store.root / 'assistant-upload.zip'
            path.write_bytes(content)
            try:
                return self.assistant.import_archive(path)
            finally:
                path.unlink(missing_ok=True)
        self._action(action)
        self.upload.value = ()
        self.restore.selected_index = None

    def add(self, reply, *, user=False):
        if not user:
            reply = friendly_reply(reply)
        self.history.append('<div style="border-bottom:1px solid #ddd;padding:8px">' +
            ('<b>You</b>' if user else '<b>Assistant</b>') + simple_reply(reply) + '</div>')
        self.history = self.history[-20:]
        self.transcript.value = ''.join(self.history)

    def sync(self, *, current=None):
        self._draft_id = self.assistant.pending
        self.confirm.disabled = self._draft_id is None
        self.connection.disabled = self.connector is None or self.live_ready
        options = []
        for index, job in enumerate(self.assistant.jobs(), 1):
            label = {'mapping': 'Map', 'export': 'Download', 'assistant_snapshot': 'Saved download'}[job['kind']]
            options.append((f"{index}. {label} · {job['state']}", job['job_id']))
        self.select.unobserve(self._selection, names='value')
        try:
            self.select.options = [('Choose saved work', ''), *options]
            self.select.value = self.assistant.selected or ''
        finally:
            self.select.observe(self._selection, names='value')
        if current is None and self.assistant.selected:
            current = self.assistant.describe()
        active = current is not None and current['state'] in {'queued', 'running', 'submitting', 'submitted', 'cancelling', 'submission_unknown'}
        self._visible(self.connection_box, not self.live_ready)
        self._visible(self.choices, self.live_ready and current is None and not self._draft_id)
        self._visible(self.review_box, bool(self._draft_id))
        self._visible(self.work_box, current is not None)
        self.prepare.disabled = active
        if self._draft_id:
            data = self.assistant.store.get(self._draft_id)['inputs']
            if data['action'] == 'mapping':
                request = data['request']
                self.preview.value = '<h3>Review your map</h3>' + table([
                    ('Region', area_name(request)), ('Target year', request['target_year']),
                    ('Download available afterwards', 'One small sample; whole-region download is not available')])
                self.preview.value += '<details><summary>Data used</summary>' + table([
                    ('Boundary', request['aoi_asset']), ('Training data', request['training_asset'])]) + '</details>'
                self.confirm.description = 'Start mapping'
            else:
                window = data['plan']['spec']['pixel_window']
                self.preview.value = '<h3>Review your sample download</h3>' + table([
                    ('Coverage', 'One small window, not the whole study area'),
                    ('Size', f"{window['width']} × {window['height']} pixels"), ('Pixel size', '10 metres')])
                self.confirm.description = 'Create sample file'
            self.step.value = '<h3>Review, then start</h3>'
        elif current:
            self.step.value = '<h3>Your current work</h3>'
        elif self.live_ready:
            self.step.value = '<h3>2. Choose your map</h3>'
        else:
            self.step.value = '<h3>1. Connect Google</h3>'
        if current:
            reply = friendly_reply(current)
            summary = {'message': reply['message'], 'state': reply['state'],
                'observed_at': reply.get('observed_at'), 'destination_uris': reply.get('destination_uris', [])}
            self.progress.value = render_reply(summary)
            completed_map = current['type'] == 'mapping' and current['state'] == 'completed'
            self._visible(self.pilot, completed_map and not self._draft_id)
            self._visible(self.refresh, not self._draft_id and current['state'] != 'completed')
            self._visible(self.backup, completed_map or current['type'] == 'export')
            self._visible(self.new, not active and not self._draft_id)
        else:
            self.progress.value = ''

    def _action(self, action):
        if self._closed:
            return
        controls = (self.send, self.confirm, self.refresh, self.report, self.backup, self.discard,
                    self.status, self.result, self.prepare, self.pilot, self.upload, self.connection, self.select, self.year, self.new)
        for control in controls:
            control.disabled = True
        self.activity.value = '<p><b>Working…</b> Please wait; one click is enough.</p>'
        try:
            self.add(action())
        except (ValueError, KeyError) as exc:
            self.add({'type': 'error', 'message': str(exc)})
        except Exception as exc:
            self.add({'type': 'error', 'message': 'This step could not finish. If you were connecting Google, check project access with the owner. Otherwise check your current work before retrying.',
                      'error_type': type(exc).__name__})
        finally:
            for control in controls:
                control.disabled = False
            self.activity.value = ''
            self.sync()

    def _send(self, _):
        text = self.message.value.strip()
        if not text:
            return
        self.message.value = ''
        self.add({'message': text}, user=True)
        self._action(lambda: self.assistant.say(text))

    def _confirm(self, _):
        identifier = self._draft_id
        self._action(lambda: self.assistant.confirm(identifier))

    def _discard(self, _):
        mapping_draft = (self.assistant.pending and self.assistant.store.get(self.assistant.pending)['inputs']['action'] == 'mapping')
        self.assistant.discard()
        if mapping_draft and not any(j['state'] in {'queued', 'running'} for j in self.assistant.jobs()):
            self.assistant.selected = None
        self.add({'message': 'Choices cleared. You can choose a year again. Existing work has not been cancelled.'})
        self.sync()

    def _change_year(self, change):
        self.assistant.discard()
        self.sync()

    def _new(self, _):
        self.assistant.discard()
        self.assistant.selected = None
        self.sync()

    def _selection(self, change):
        if change['new']:
            self.assistant.discard()
            self._action(lambda: self.assistant.describe(change['new']))

    def _save(self, backup):
        output = self.assistant.store.root / ('landcover-saved-work.zip' if backup else 'landcover-details.json')
        path = self.assistant.save_backup(output) if backup else self.assistant.save_report(output)
        if self.download:
            self.download(str(path))
        return {'message': 'Saved. Next time, open this same notebook and choose Continue saved work.' if backup else 'Details saved. You can share this file with the project owner for support.'}

    def close(self):
        self._closed = True
        self.widget.close()


def display_chat(assistant, *, download=None, connect=None):
    from IPython.display import display
    ui = ChatUI(assistant, download=download, connect=connect)
    display(ui.widget)
    return ui
