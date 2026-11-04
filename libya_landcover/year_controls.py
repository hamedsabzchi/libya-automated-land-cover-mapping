"""Expose existing request years without remounting maps or starting work."""
def install_year_controls(ui, *, initialize_year=False):
    import ipywidgets as w
    request = ui.assistant.request_defaults()
    ui.year.description = 'Target year'
    ui.year.style.description_width = 'initial'
    # Upgrading an open workspace must expand both existing widgets without
    # firing their edit callbacks or expiring the user's pending review.
    for widget in (ui.year, getattr(ui, 'fallback_year', None)):
        if widget is None:
            continue
        value = widget.value
        widget.unobserve(ui._change_year, names='value')
        try:
            widget.options = list(range(2025, 2016, -1))
            widget.value = value
        finally:
            widget.observe(ui._change_year, names='value')
    if initialize_year:
        ui.year.unobserve(ui._change_year, names='value')
        ui.year.value = request.get('target_year', ui.year.value)
        ui.year.observe(ui._change_year, names='value')
    if not hasattr(ui, 'fallback_year'):
        ui.fallback_year = w.Dropdown(description='Fallback year', options=list(range(2025, 2016, -1)),
            value=request.get('fallback_year', 2023), style={'description_width':'initial'})
        ui.fallback_year.observe(ui._change_year, names='value')
    ui.choices.children = (
        w.HTML('<h4>Map settings for your next run</h4><p>Choose the target year and fallback year. '
               'The fallback supplies missing target-year embedding data. Changing these choices does not run anything. '
               'Click <b>Create map</b> to apply them; your existing maps and downloads stay saved.</p>'),
        w.HBox([ui.region, ui.year, ui.fallback_year], layout=w.Layout(flex_flow='row wrap')), ui.prepare)
    ui._visible(ui.choices, ui.live_ready)


def set_year_choices(ui, request):
    """Show chat-proposed values without expiring their pending confirmation."""
    for field, widget in (('target_year', ui.year), ('fallback_year', ui.fallback_year)):
        widget.unobserve(ui._change_year, names='value')
        try:
            widget.value = request[field]
        finally:
            widget.observe(ui._change_year, names='value')
