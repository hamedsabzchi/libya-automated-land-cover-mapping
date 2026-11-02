"""Mount only the chat panel; live map widgets and download controls are retained."""


def install_accuracy_chat(ui):
    import ipywidgets as w
    old_chat = getattr(ui, 'chat', None)
    button = w.Button(description='Model accuracy', icon='table', layout=w.Layout(width='170px'))
    button.on_click(lambda _: ui._action(ui.assistant.accuracy))
    ui.accuracy_button = button
    explain = w.Button(description='Explain accuracy', icon='comment', layout=w.Layout(width='170px'))
    explain.on_click(lambda _: ui._action(lambda: ui.assistant.accuracy(question='Interpret accuracy')))
    ui.explain_accuracy_button = explain
    ui.chat = w.VBox([
        w.HTML('<h3>Ask the assistant</h3><p><b>Model accuracy</b> shows the saved tables. '
               '<b>Explain accuracy</b> gives a short explanation. You can ask '
               '<i>Explain the accuracy of cultivated irrigated land</i>, '
               '<i>Which classes are most often confused?</i> or '
               '<i>What does producer accuracy mean?</i> '
               'These answers use saved validation results and need no new Earth Engine calculation. '
               'You can still ask about colours, progress or another year.</p>'),
        ui.chat_mode, w.HBox([button, explain, *ui.help_buttons], layout=w.Layout(flex_flow='row wrap')),
        ui.transcript, ui.message, ui.send])
    if old_chat is not None and hasattr(ui, 'widget'):
        ui.widget.children = tuple(ui.chat if child is old_chat else child for child in ui.widget.children)
    return ui.chat


def upgrade_accuracy_chat(ui):
    """Upgrade Python methods in place without rebuilding a map or checking an export."""
    from .map_ui import MapUI
    from .map_assistant import MapAssistant
    from .local_language import LocalParser
    from .chat_language import GuidedParser
    if (ui.__class__.__module__, ui.__class__.__name__) != ('libya_landcover.map_ui', 'MapUI'):
        raise ValueError('Open the map workspace before updating its assistant.')
    assistant = ui.assistant
    if (assistant.__class__.__module__, assistant.__class__.__name__) != ('libya_landcover.map_assistant', 'MapAssistant'):
        raise ValueError('This update requires the existing map assistant.')
    parser = assistant.parser
    if parser.__class__.__name__ == 'LocalParser':
        assistant.parser = LocalParser(parser._generate, device=parser.device, model_id=parser.model_id)
    elif parser.__class__.__name__ == 'GuidedParser':
        assistant.parser = GuidedParser()
    assistant.__class__ = MapAssistant
    ui.__class__ = MapUI
    from .year_controls import install_year_controls
    install_year_controls(ui)
    install_accuracy_chat(ui)
    return ui
