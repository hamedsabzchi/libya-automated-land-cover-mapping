"""Browser-requested widget delivery for Colab's idle output frames.

This is a status/display callback, not a work-submission endpoint. In Colab,
background widget sends can remain invisible after the originating cell ends.
"""
import json
from uuid import uuid4


def send_widget_tree(root):
    """Resend the existing view and its dependencies in the callback context."""
    from ipywidgets import Widget
    seen = set()

    def visit(value):
        if isinstance(value, Widget):
            if id(value) in seen or value.comm is None:
                return
            seen.add(id(value))
            for name in value.traits(sync=True):
                visit(getattr(value, name))
            value.send_state()
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)

    visit(root)


def refresh_script(name, interval_ms=5000):
    # Wait for each callback before scheduling another. Never accumulate requests
    # when Earth Engine is slow or a notebook reconnects.
    return """(() => {
      const name = NAME;
      const slot = '__libyaLandcoverRefresh';
      if (globalThis[slot]) globalThis[slot]();
      let stopped = false, timer = null, failures = 0;
      const stop = () => { stopped = true; clearTimeout(timer); };
      globalThis[slot] = stop;
      window.addEventListener('pagehide', stop, {once: true});
      async function tick() {
        if (stopped) return;
        try {
          const reply = await google.colab.kernel.invokeFunction(name, [], {});
          const state = reply && reply.data && reply.data['application/json'];
          if (state && state.closed) { stop(); return; }
          failures = 0;
        } catch (_) {
          if (++failures >= 3) { stop(); return; }
        }
        if (!stopped) timer = setTimeout(tick, INTERVAL);
      }
      timer = setTimeout(tick, 100);
    })();""".replace('NAME', json.dumps(name)).replace('INTERVAL', str(interval_ms))


def attach_colab_updates(ui):
    """Use Colab's documented callback bridge, or leave ordinary notebooks alone."""
    try:
        from google.colab import output
    except ImportError:
        return False
    from IPython.display import Javascript, JSON, display
    name = 'libya_landcover.refresh_' + uuid4().hex

    def refresh():
        return JSON(ui._browser_tick())

    output.register_callback(name, refresh)
    try:
        display(Javascript(refresh_script(name)))
    except Exception:
        output.unregister_callback(name)
        raise
    ui._browser_updates = True
    ui._browser_callback = (output, name)
    # Any pending map mount must happen inside a browser-requested callback,
    # so new map-widget comms also reach the displayed Colab frame.
    if ui._load_task and not ui._load_task.done():
        ui._load_task.cancel()
        if ui.map_data is None and not ui.last_error:
            ui._attempted = None
    return True


def detach_colab_updates(ui):
    registered = getattr(ui, '_browser_callback', None)
    if registered:
        output, name = registered
        try:
            output.unregister_callback(name)
        except ValueError:
            pass
        ui._browser_callback = None
    ui._browser_updates = False
