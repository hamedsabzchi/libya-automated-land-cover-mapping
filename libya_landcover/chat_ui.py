"""Small private Colab/Jupyter chat UI; optional ipywidgets dependency."""

from html import escape
import json
from pathlib import Path
from urllib.parse import urlparse

from .chat_language import HELP


def render_reply(reply):
    """All user/model/server text is escaped; only actual Drive links are clickable."""
    message = escape(str(reply.get("message", "")))
    details = {k: v for k, v in reply.items() if k != "message"}
    links = []
    for uri in reply.get("destination_uris", []):
        if isinstance(uri, str):
            parsed = urlparse(uri)
            if parsed.scheme == "https" and parsed.netloc == "drive.google.com":
                links.append('<a target="_blank" rel="noopener noreferrer" href="' + escape(uri, quote=True) + '">Open Drive output</a>')
    summary = []
    labels = {"state": "وضعیت", "source": "منبع وضعیت", "observed_at": "زمان ثبت",
              "coverage": "محدودهٔ خروجی", "drive_folder": "پوشهٔ Drive"}
    for key, label in labels.items():
        if reply.get(key) is not None:
            summary.append('<div dir="auto"><b>' + label + ':</b> ' + escape(str(reply[key])) + '</div>')
    if reply.get("type") == "mapping" and reply.get("outputs"):
        summary.append('<div dir="auto">تعداد نقشه‌های ذخیره‌شده به صورت گراف: ' + str(len(reply["outputs"])) + '</div>')
    # Proposals remain fully visible; technical result metadata can be expanded.
    metadata = '<pre style="white-space:pre-wrap;overflow-wrap:anywhere" dir="ltr">' + escape(
        json.dumps(details, indent=2, ensure_ascii=False)) + '</pre>' if details else ''
    if reply.get("type") not in {"preview", "jobs"} and metadata:
        metadata = '<details><summary>جزئیات / Details</summary>' + metadata + '</details>'
    return '<div dir="auto" style="white-space:pre-wrap">' + message + '</div>' + ''.join(summary) + '<br>'.join(links) + metadata


class ChatUI:
    def __init__(self, assistant, *, download=None):
        import ipywidgets as w
        self.assistant, self.download = assistant, download
        assistant.discard()
        self._draft_id = None
        self.history = []
        self.transcript = w.HTML()
        self.message = w.Textarea(placeholder="map 2024 | وضعیت | نتیجه", layout=w.Layout(width="100%", height="75px"))
        self.send = w.Button(description="ارسال / Send", button_style="primary")
        self.confirm = w.Button(description="تأیید و اجرا / Run", button_style="warning", disabled=True,
                                layout=w.Layout(width="200px"))
        self.discard = w.Button(description="لغو پیش‌نویس")
        self.refresh = w.Button(description="Refresh status")
        self.select = w.Dropdown(description="Job", options=[("Choose a job", "")], layout=w.Layout(width="100%"))
        self.report = w.Button(description="Download report")
        self.backup = w.Button(description="Download backup")
        self.send.on_click(self._send)
        self.confirm.on_click(self._confirm)
        self.discard.on_click(self._discard)
        self.refresh.on_click(lambda _: self._action(assistant.refresh))
        self.report.on_click(lambda _: self._action(lambda: self._save(False)))
        self.backup.on_click(lambda _: self._action(lambda: self._save(True)))
        self.select.observe(self._selection, names="value")
        mode = w.HTML('<b>' + escape(assistant.parser.label) + '</b><br><span dir="auto">' +
            'وضعیت‌ها با Refresh به‌روز می‌شوند. تهیهٔ درخواست جدید، تأیید قبلی را باطل می‌کند.</span>')
        self.widget = w.VBox([mode, self.select, self.transcript, self.message,
            w.HBox([self.send, self.confirm, self.discard]), w.HBox([self.refresh, self.report, self.backup])])
        self.add({"message": HELP})
        if assistant.selected:
            self.add(assistant.describe())
        self.sync()

    def add(self, reply, *, user=False):
        self.history.append('<div style="border-bottom:1px solid #ddd;padding:12px">' +
            ('<b>You</b>' if user else '<b>Assistant</b>') + render_reply(reply) + '</div>')
        self.history = self.history[-30:]
        self.transcript.value = ''.join(self.history)

    def sync(self):
        self._draft_id = self.assistant.pending
        self.confirm.disabled = self._draft_id is None
        options = [(j["kind"] + ' · ' + j["state"] + ' · ' + j["job_id"], j["job_id"])
                   for j in self.assistant.jobs()]
        self.select.unobserve(self._selection, names="value")
        try:
            self.select.options = [("Choose a job", ""), *options]
            self.select.value = self.assistant.selected or ""
        finally:
            self.select.observe(self._selection, names="value")

    def _action(self, action):
        buttons = (self.send, self.confirm, self.refresh, self.report, self.backup, self.discard)
        for button in buttons:
            button.disabled = True
        try:
            self.add(action())
        except (ValueError, KeyError) as exc:
            self.add({"type": "error", "message": str(exc)})
        except Exception as exc:
            # Never render raw authentication/network exceptions or request headers.
            self.add({"type": "error", "message": "عملیات کامل نشد؛ اتصال، ورود GEE و وضعیت کار را بررسی کن.",
                      "error_type": type(exc).__name__})
        finally:
            for button in buttons:
                button.disabled = False
            self.sync()

    def _send(self, _):
        text = self.message.value
        self.message.value = ""
        self.add({"message": text}, user=True)
        self._action(lambda: self.assistant.say(text))

    def _confirm(self, _):
        identifier = self._draft_id
        self._action(lambda: self.assistant.confirm(identifier))

    def _discard(self, _):
        self.assistant.discard()
        self.add({"message": "پیش‌نویس لغو شد. کارهای اجراشده متوقف نمی‌شوند."})
        self.sync()

    def _selection(self, change):
        if change["new"]:
            self.assistant.discard()
            self._action(lambda: self.assistant.describe(change["new"]))

    def _save(self, backup):
        output = self.assistant.store.root / ("assistant-result.zip" if backup else "assistant-report.json")
        path = self.assistant.save_backup(output) if backup else self.assistant.save_report(output)
        if self.download:
            self.download(str(path))
        return {"message": "فایل آماده است. Backup شامل گراف‌ها و اطلاعات کار است؛ TIFF را از Drive بگیر.", "file": str(Path(path))}


def display_chat(assistant, *, download=None):
    from IPython.display import display
    ui = ChatUI(assistant, download=download)
    display(ui.widget)
    return ui
