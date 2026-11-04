"""Add saved-accuracy chat to the open workspace, retaining its map and downloads."""
import asyncio
import importlib
import subprocess
import sys

SERVICE_COMMIT = "b33e1abebc7f3e65727bd2590b8be320eb954bf6"


async def update_accuracy(previous):
    if previous is None or getattr(previous, '_closed', True):
        raise RuntimeError('Run this update in the same notebook as your open map workspace.')
    while previous._busy or previous._polling:
        await asyncio.sleep(.25)
    previous._busy = True  # Existing timers skip the update; no new timers/tasks.
    old_ui_class, old_assistant_class = previous.__class__, previous.assistant.__class__
    old_parser, old_chat = previous.assistant.parser, previous.chat
    old_children = previous.widget.children
    old_choices = previous.choices.children
    old_fallback = getattr(previous, 'fallback_year', None)
    try:
        from libya_landcover.workspace import save_workspace
        backup = save_workspace(previous.assistant, previous.assistant.store.root / 'landcover-before-accuracy.zip',
                                history=previous.history)
        print('Your saved work is backed up. Restoring target and fallback year controls…')
        if previous.download:
            previous.download(str(backup))
        log = previous.assistant.store.root / 'accuracy-update.log'
        with log.open('w') as stream:
            installed = await asyncio.to_thread(subprocess.run,
                [sys.executable, '-m', 'pip', 'install', '--quiet', '--no-deps',
                 'libya-landcover-assistant @ git+https://github.com/hamedsabzchi/libya-automated-land-cover-mapping.git@' + SERVICE_COMMIT],
                stdout=stream, stderr=stream)
        if installed.returncode:
            raise RuntimeError('The update could not install. Your current workspace and backup are retained.')
        importlib.invalidate_caches()
        # Retain map, export, engine, credentials, model weights and polling modules.
        for name in ('year_controls', 'accuracy_explanation', 'chat_language', 'local_language', 'accuracy', 'assistant', 'map_assistant',
                     'chat_ui', 'accuracy_chat', 'map_ui'):
            importlib.reload(importlib.import_module('libya_landcover.' + name))
        from libya_landcover.accuracy_chat import upgrade_accuracy_chat
        upgrade_accuracy_chat(previous)
        import libya_landcover
        libya_landcover.__version__ = '0.11.0'
        from IPython.display import display
        # Show the year controls here too; the existing map stays mounted.
        display(previous.choices)
        print('Ready. Choose Target year and Fallback year, then click Create map when you want a new run. Your existing work is retained.')
        return previous
    except Exception:
        previous.__class__, previous.assistant.__class__ = old_ui_class, old_assistant_class
        previous.assistant.parser, previous.chat = old_parser, old_chat
        previous.widget.children = old_children
        previous.choices.children = old_choices
        if old_fallback is None and hasattr(previous, 'fallback_year'):
            previous.fallback_year.close()
            del previous.fallback_year
        raise
    finally:
        previous._busy = False


if __name__ == '__main__':
    accuracy_update_task = asyncio.get_running_loop().create_task(update_accuracy(globals().get('ui')))
