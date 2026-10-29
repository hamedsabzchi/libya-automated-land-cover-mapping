"""One-time, in-place Colab display repair. Keeps the existing assistant and store."""
import importlib
import subprocess
import sys

SERVICE_COMMIT = "9e91a3c54adba54ba0808b4dd5b9cfa1b64364ef"


def repair_current_display(previous):
    if previous is None or not getattr(previous, 'map_data', None):
        raise RuntimeError('Run this cell in the same notebook session as the blank prepared map. Do not restart the runtime.')
    if previous._busy or previous._polling:
        raise RuntimeError('Wait for the current action to finish, then run this repair cell again.')
    print('Restoring the map interface. Your prepared map and downloads stay in this session…')
    log = previous.assistant.store.root / 'display-repair.log'
    with log.open('w') as stream:
        installed = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--no-deps',
            'libya-landcover-assistant @ git+https://github.com/hamedsabzchi/libya-automated-land-cover-mapping.git@'+SERVICE_COMMIT],
            stdout=stream, stderr=stream)
    if installed.returncode:
        raise RuntimeError('The display update could not install. Your old interface is still open; keep this runtime.')
    # Replace display classes only. Keep the engine, assistant object, credentials,
    # local chat model, selected tile, pending review and job ledger in memory.
    importlib.invalidate_caches()
    import libya_landcover.notebook_map as notebook_map
    import libya_landcover.map_ui as map_ui
    importlib.reload(notebook_map)
    importlib.reload(map_ui)
    if not hasattr(map_ui, 'restore_live_workspace'):
        raise RuntimeError('The expected display update was not loaded. Your work is still saved in this runtime.')
    restored = map_ui.restore_live_workspace(previous)
    print('Display restored below. No mapping or export was started. Check whether the boundary and colours are visible.')
    return restored


if __name__ == '__main__':
    ui = repair_current_display(globals().get('ui'))
