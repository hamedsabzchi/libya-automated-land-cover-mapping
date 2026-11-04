"""Regression for VBox text fallback, using real widgets and IPython publication."""
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from ipywidgets import VBox, Button
from libya_landcover.widget_display import display_widget, WIDGET_MIME


class WidgetDisplayTests(unittest.TestCase):
    def test_raw_widget_view_survives_a_text_only_ipython_formatter(self):
        source = r'''
import sys, types
from unittest.mock import Mock, patch
from IPython.core.interactiveshell import InteractiveShell
from IPython.display import display
from IPython.utils.capture import capture_output
from ipywidgets import VBox, Button
from libya_landcover.widget_display import display_widget, WIDGET_MIME
shell = InteractiveShell.instance()
widget = VBox([Button(description='Create map')])
colab = types.ModuleType('google.colab'); colab.output = Mock()
with patch.dict(sys.modules, {'google.colab': colab}), \
     patch.object(shell.display_formatter, 'format', return_value=({'text/plain': repr(widget)}, {})):
    with capture_output() as before:
        display(widget)
    assert 'VBox(' in before.outputs[0].data['text/plain']
    assert WIDGET_MIME not in before.outputs[0].data
    with capture_output() as after:
        display_widget(widget)
    assert len(after.outputs) == 1
    data = after.outputs[0].data
    assert data[WIDGET_MIME] == widget.get_view_spec()
    assert 'VBox(' not in data['text/plain']
    colab.output.enable_custom_widget_manager.assert_called_once()
widget.close()
'''
        result = subprocess.run([sys.executable, '-c', source],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_redisplay_preserves_controls_callbacks_and_widget_identity(self):
        button = Button(description='Create tile download')
        callback = Mock(); button.on_click(callback)
        widget = VBox([button]); self.addCleanup(widget.close); self.addCleanup(button.close)
        identity = (widget.model_id, widget.comm, widget.children, button.model_id)
        with patch('IPython.display.display') as publish, \
             patch('ipywidgets.register_comm_target') as register, \
             patch.object(button, 'send_state') as state:
            display_widget(widget)
            register.assert_called_once(); state.assert_called_once()
            args, kwargs = publish.call_args
            self.assertTrue(kwargs['raw'])
            self.assertEqual(args[0][WIDGET_MIME]['model_id'], widget.model_id)
        self.assertEqual(identity, (widget.model_id, widget.comm, widget.children, button.model_id))
        callback.assert_not_called()
        button.click(); callback.assert_called_once()

    def test_closed_view_is_not_published_or_silently_recreated(self):
        widget = VBox(); widget.close()
        with patch('IPython.display.display') as publish:
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                display_widget(widget)
            publish.assert_not_called()


if __name__ == '__main__': unittest.main()
