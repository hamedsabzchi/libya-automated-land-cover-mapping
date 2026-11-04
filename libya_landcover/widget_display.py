"""Publish the live widget protocol explicitly, bypassing text-only formatters."""

WIDGET_MIME = 'application/vnd.jupyter.widget-view+json'


def display_widget(widget):
    """Mount the existing widget; do not rebuild it or start application work.

    Colab attaches its custom-manager metadata to this MIME type at publication.
    Raw display avoids a stale/disabled IPython formatter choosing VBox's repr.
    The browser still needs access to Colab's widget manager and widget assets.
    """
    if getattr(widget, 'comm', None) is None:
        raise RuntimeError('This interface is closed; its saved work is still retained.')
    from ipywidgets import register_comm_target
    from IPython.display import display
    from .colab_updates import send_widget_tree
    register_comm_target()
    try:
        from google.colab import output
    except ImportError:
        pass  # Ordinary Jupyter uses its own widget manager.
    else:
        output.enable_custom_widget_manager()
    spec = widget.get_view_spec()
    if not spec.get('model_id'):
        raise RuntimeError('The assistant widget connection has no model identifier.')
    # Re-send this view's existing dependencies after a cell output was cleared.
    send_widget_tree(widget)
    display({
        WIDGET_MIME: spec,
        'text/plain': ('The interactive assistant has not rendered in this viewer. '
                       'Its controls require the live Google Colab widget renderer. '
                       'Existing saved work has not been deleted.'),
    }, raw=True)
