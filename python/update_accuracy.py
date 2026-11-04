"""Compatibility entry: update an open workspace or open the complete assistant."""
import asyncio
import importlib
import subprocess
import sys

SERVICE_COMMIT = "3eb4f3d77b4fc3c5d00dfb5ed678e26190f5bb5a"


def open_complete_assistant():
    """Use the same pinned startup as the complete Colab, without a prior UI."""
    from urllib.request import urlopen
    url = ('https://raw.githubusercontent.com/hamedsabzchi/'
           'libya-automated-land-cover-mapping/' + SERVICE_COMMIT + '/python/start_assistant.py')
    with urlopen(url, timeout=60) as response:
        source = response.read().decode('utf-8')
    exec(compile(source, 'start_assistant.py', 'exec'), globals())
    return globals().get('ui')


async def update_accuracy(previous):
    if previous is None or getattr(previous, '_closed', True):
        return open_complete_assistant()
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
        for name in ('contracts.models', 'contracts', 'python.landcover_engine', 'python.assistant_adapter'):
            if name in sys.modules:
                importlib.reload(sys.modules[name])
        # Retain map, export, engine, credentials, model weights and polling modules.
        for name in ('jobs', 'year_controls', 'accuracy_explanation', 'chat_language', 'local_language', 'accuracy', 'assistant', 'map_assistant',
                     'chat_ui', 'accuracy_chat', 'map_ui'):
            importlib.reload(importlib.import_module('libya_landcover.' + name))
        from libya_landcover.accuracy_chat import upgrade_accuracy_chat
        upgrade_accuracy_chat(previous)
        previous.assistant.engine_commit = SERVICE_COMMIT
        import libya_landcover
        libya_landcover.__version__ = '0.12.0'
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


def show_update_error(exc):
    """Report a failed update in the cell; never leave an unobserved asyncio error."""
    from html import escape
    from IPython.display import HTML, display
    display(HTML('<p>The assistant update could not finish. Existing work has been retained.</p>'
                 '<details><summary>Error details</summary><pre>' +
                 escape(type(exc).__name__ + ': ' + str(exc)) + '</pre></details>'))


def update_finished(task):
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        show_update_error(exc)


def open_or_update():
    previous = globals().get('ui')
    if previous is None or getattr(previous, '_closed', True):
        # A fresh notebook must open in the cell's display context, not in an
        # orphaned background task which assumes a map is already mounted.
        try:
            return open_complete_assistant()
        except Exception as exc:
            show_update_error(exc)
            return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(update_accuracy(previous))
        except Exception as exc:
            show_update_error(exc)
            return None
    task = loop.create_task(update_accuracy(previous))
    task.add_done_callback(update_finished)
    return task


if __name__ == '__main__':
    accuracy_update_task = open_or_update()
