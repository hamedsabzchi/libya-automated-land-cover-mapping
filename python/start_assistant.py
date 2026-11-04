import sys, subprocess, traceback, importlib, sqlite3, logging
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError
from IPython.display import display, HTML, clear_output

# The complete notebook embeds this starter and supplies its immutable release pin.
# The compatibility updater supplies the same pin when opening a fresh workspace.
if not isinstance(globals().get("SERVICE_COMMIT"), str) or not __import__("re").fullmatch(r"[0-9a-f]{40}", SERVICE_COMMIT):
    raise ValueError("The assistant release pin is missing or invalid.")
EXPECTED_VERSION = "0.12.1"

def repair_closed_console_logs():
    # Older startup redirected stderr into a short-lived file. Libraries retained
    # that stream in their handlers. Repair console handlers without touching files.
    loggers = [logging.getLogger()] + [item for item in logging.Logger.manager.loggerDict.values()
                                       if isinstance(item, logging.Logger)]
    repaired = 0
    seen = set()
    for logger in loggers:
        for handler in logger.handlers:
            if id(handler) in seen:
                continue
            seen.add(id(handler))
            if (isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
                    and getattr(getattr(handler, "stream", None), "closed", False)):
                handler.acquire()
                try:
                    # setStream flushes the old stream, which is already closed.
                    handler.stream = sys.stderr
                    repaired += 1
                finally:
                    handler.release()
    return repaired


def mapping_is_active():
    database = Path("/content/assistant-store/jobs.sqlite3")
    if not database.exists():
        return False
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        return db.execute("SELECT 1 FROM records WHERE kind='mapping' AND state IN ('queued','running') LIMIT 1").fetchone() is not None


def retire_previous_interface():
    previous = globals().get("assistant")
    if previous is not None:
        previous.discard()
        def retired():
            raise ValueError("This interface has been replaced. Use the newly opened assistant below.")
        previous.before_live = retired
    previous_ui = globals().get("ui")
    if previous_ui is not None:
        if callable(getattr(previous_ui, "close", None)):
            previous_ui.close()
        elif hasattr(previous_ui, "widget"):
            previous_ui.widget.close()
        # Older versions only closed the parent box, leaving the map comm open.
        previous_map = getattr(previous_ui, "map", None)
        if previous_map is not None:
            previous_map.close()
        # Older updates could leave more than one detached workspace map alive.
        # Only retire maps bearing BOTH workspace-owned overlay names.
        from ipywidgets.widgets import widget as widget_module
        from ipyleaflet import Map
        for candidate in list(getattr(widget_module, "_instances", {}).values()):
            if isinstance(candidate, Map) and candidate.comm is not None:
                names = {getattr(layer, "name", "") for layer in candidate.layers}
                if {"Download grid", "Selected download tile"} <= names:
                    candidate.close()


def start_assistant():
    global assistant, ui, local_parser
    repair_closed_console_logs()
    previous_ui = globals().get("ui")
    reuse_workspace = previous_ui is not None and hasattr(previous_ui, "map_data") and not getattr(previous_ui, "_closed", True)
    loaded = sys.modules.get("libya_landcover")
    upgrade = loaded is not None and getattr(loaded, "__version__", None) != EXPECTED_VERSION
    if upgrade:
        try:
            active = mapping_is_active()
        except Exception:
            display(HTML("<p>I could not check your saved work safely. No update was started. "
                "Keep this session open and contact the project owner.</p>"))
            return
        if active:
            display(HTML("<p>A map is still marked as running in this session. The update is paused to protect it. "
                "Use the previous assistant's Check progress / Refresh status button. After it finishes, click Start assistant again.</p>"))
            return
    clear_output(wait=True)
    progress = display(HTML("<h3>Opening your assistant…</h3><p>1 of 2 · Preparing the app. You do not need to do anything yet.</p>"), display_id=True)
    log_path = Path("/content/landcover-startup.log")
    try:
        if loaded is None or upgrade:
            with log_path.open("w") as log:
                try:
                    torch_version = tuple(int(n) for n in version("torch").split("+")[0].split(".")[:2])
                except PackageNotFoundError:
                    torch_version = (0, 0)
                if torch_version < (2, 6):
                    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "torch>=2.6,<3",
                        "--index-url", "https://download.pytorch.org/whl/cpu"], stdout=log, stderr=log, check=True)
                subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                    "libya-landcover-assistant[map-chat] @ git+https://github.com/hamedsabzchi/libya-automated-land-cover-mapping.git@" + SERVICE_COMMIT],
                    stdout=log, stderr=log, check=True)
        if upgrade:
            if version("libya-landcover-assistant") != EXPECTED_VERSION:
                raise RuntimeError("The installed update has an unexpected version")
            # Retire old controls only after installation succeeds. Preserve all work files.
            if not reuse_workspace:
                retire_previous_interface()
            # Input validation also lives outside the UI package. Refresh it
            # before importing new methods, including in a reused runtime.
            for name in ('contracts.models', 'contracts', 'python.landcover_engine', 'python.assistant_adapter'):
                if name in sys.modules:
                    importlib.reload(sys.modules[name])
            for name in list(sys.modules):
                if name == "libya_landcover" or name.startswith("libya_landcover."):
                    del sys.modules[name]
            importlib.invalidate_caches()
        elif "ui" in globals() and not reuse_workspace:
            retire_previous_interface()
        import libya_landcover
        if libya_landcover.__version__ != EXPECTED_VERSION:
            raise RuntimeError("Unexpected assistant version")
        from google.colab import files, output
        from libya_landcover.assistant import TRIPOLI
        from libya_landcover.map_assistant import MapAssistant as Assistant
        from libya_landcover.job_store import JobStore
        from libya_landcover.local_language import LocalParser
        from libya_landcover.chat_language import GuidedParser
        from libya_landcover.map_ui import display_map_assistant as display_chat
        output.enable_custom_widget_manager()
        if reuse_workspace:
            clear_output(wait=True)
            if upgrade:
                from libya_landcover.accuracy_chat import upgrade_accuracy_chat
                ui = upgrade_accuracy_chat(previous_ui)
            else:
                ui = previous_ui
            # Redisplay the same map, tile selection, downloads and unfinished chat.
            # Replace the browser callback once; never rebuild or submit work here.
            from libya_landcover.colab_updates import attach_colab_updates, detach_colab_updates
            detach_colab_updates(ui)
            from libya_landcover.widget_display import display_widget
            display_widget(ui.widget)
            attach_colab_updates(ui)
            assistant = ui.assistant
            assistant.engine_commit = SERVICE_COMMIT  # New requests record the installed source.
            return
        progress.update(HTML("<h3>Opening your assistant…</h3><p>2 of 2 · Loading English chat. "
            "The first download can take several minutes. Please wait here.</p>"))
        try:
            cached = globals().get("local_parser")
            if (upgrade and getattr(cached, "model_id", None) == "Qwen/Qwen2.5-1.5B-Instruct"
                    and callable(getattr(cached, "_generate", None))):
                # Reuse already-loaded weights while replacing the parser's Python class.
                local_parser = LocalParser(cached._generate, device=cached.device, model_id=cached.model_id)
            if "local_parser" not in globals() or not isinstance(local_parser, LocalParser):
                # Keep library loggers attached to the live notebook console.
                local_parser = LocalParser.load(cache_dir="/content/landcover-chat-model")
            repair_closed_console_logs()
            parser = local_parser
        except Exception:
            with log_path.open("a") as log:
                traceback.print_exc(file=log)
            parser = GuidedParser()
        store = JobStore(Path("/content/assistant-store"))
        assistant = Assistant(store, engine_commit=SERVICE_COMMIT, profile=dict(TRIPOLI), parser=parser)

        def connect_google():
            import ee
            ee.Authenticate()
            ee.Initialize(project=assistant.profile["project"])
            try:
                ee.data.getAsset(assistant.profile["aoi_asset"])
                ee.data.getAsset(assistant.profile["training_asset"])
            except Exception:
                raise ValueError("Google signed in, but the configured study data could not be opened. "
                    "Ask the project owner to check your access to the Tripoli boundary and training data, then reconnect.") from None

        clear_output(wait=True)
        ui = display_chat(assistant, download=files.download, connect=connect_google)
    except Exception as exc:
        with log_path.open("a") as log:
            traceback.print_exc(file=log)
        progress.update(HTML("<h3>The assistant could not open</h3><p>Click Start assistant once more. "
            "If the problem continues, send the project owner this error name: <b>" + type(exc).__name__ + "</b>.</p>"))

start_assistant()
