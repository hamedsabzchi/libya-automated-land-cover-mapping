"""Apply the unified UI in the current Colab session, without restarting work."""
import asyncio
import importlib
import subprocess
import sys

SERVICE_COMMIT = "3aa8fb73f983fea933572c61aee863619f6c2ad1"


async def update_current_workspace(previous):
    if previous is None or not getattr(previous,'assistant',None):
        raise RuntimeError('Use this cell in the same notebook as your existing assistant.')
    print('Updating this workspace. Keep this notebook open; no mapping or export will be started.')
    # Let an in-flight read finish. Never cancel a thread while it is writing its observation.
    while previous._busy or previous._polling:
        await asyncio.sleep(.25)
    old_task=getattr(previous,'_poll_task',None)
    had_poll=old_task is not None and not old_task.done()
    if old_task:
        old_task.cancel()
        try:await old_task
        except asyncio.CancelledError:pass
    previous._busy=True
    old_assistant_class=previous.assistant.__class__
    old_display=previous.widget.layout.display
    previous.widget.layout.display='none'
    previous.activity.value='<p><b>Updating the interface and saving your work…</b></p>'
    try:
        log=previous.assistant.store.root/'workspace-update.log'
        with log.open('w') as stream:
            installed=await asyncio.to_thread(subprocess.run,[sys.executable,'-m','pip','install','--quiet','--no-deps',
                'libya-landcover-assistant @ git+https://github.com/hamedsabzchi/libya-automated-land-cover-mapping.git@'+SERVICE_COMMIT],
                stdout=stream,stderr=stream)
        if installed.returncode:raise RuntimeError('Update installation failed. Your current work is retained.')
        importlib.invalidate_caches()
        # No engine, adapter, classifier or authentication modules are reloaded.
        for name in ('downloads','exports','workspace','chat_ui','notebook_map','map_ui'):
            module=importlib.import_module('libya_landcover.'+name);importlib.reload(module)
        from libya_landcover.workspace import save_workspace
        backup=save_workspace(previous.assistant,previous.assistant.store.root/'landcover-before-update.zip',history=previous.history)
        print('All existing work was saved to landcover-before-update.zip.')
        if previous.download:
            try:previous.download(str(backup))
            except Exception:print('The backup is also retained in this session; Save work for later downloads it.')
        if old_assistant_class.__module__=='libya_landcover.map_assistant' and old_assistant_class.__name__=='MapAssistant':
            assistant_module=importlib.import_module('libya_landcover.assistant');importlib.reload(assistant_module)
            map_module=importlib.import_module('libya_landcover.map_assistant');importlib.reload(map_module)
            # Pure-Python classes with the same instance fields. Keep the exact
            # assistant object, ledger, pending review, parser and selection.
            previous.assistant.__class__=map_module.MapAssistant
        from libya_landcover.map_ui import restore_live_workspace
        previous._busy=False
        updated=restore_live_workspace(previous)
        import libya_landcover
        libya_landcover.__version__='0.9.0'
        print('Ready. Select a blue square and click Create tile download once. Follow Downloads above; no refresh clicks are needed.')
        return updated
    except Exception:
        previous.assistant.__class__=old_assistant_class
        previous.widget.layout.display=old_display
        previous._busy=False;previous.activity.value=''
        if not previous._closed and had_poll:
            previous._poll_task=asyncio.create_task(previous._poll_loop())
        raise
