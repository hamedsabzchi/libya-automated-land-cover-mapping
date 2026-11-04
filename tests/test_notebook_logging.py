"""Exercise the actual notebook repair with real logging handlers; no model download."""
import ast
from contextlib import redirect_stderr
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

NOTEBOOK = Path(__file__).resolve().parents[1]/'python/07_wp07_free_english_assistant.ipynb'


def source():
    return ''.join(next(c for c in json.loads(NOTEBOOK.read_text())['cells'] if c['cell_type']=='code')['source'])


def repair():
    node = next(n for n in ast.parse(source()).body if isinstance(n,ast.FunctionDef) and n.name=='repair_closed_console_logs')
    scope = {'logging':logging,'sys':sys}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(NOTEBOOK),'exec'),scope)
    return scope['repair_closed_console_logs']()


class NotebookLoggingTests(unittest.TestCase):
    def setUp(self):
        self.logger=logging.getLogger('startup-regression.'+str(uuid4()))
        self.logger.setLevel(logging.WARNING); self.logger.propagate=False
        self.addCleanup(self.clean)
    def clean(self):
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler);handler.close()
    def test_old_closed_stream_is_repaired_before_later_generation_warning(self):
        old=io.StringIO()
        with redirect_stderr(old): handler=logging.StreamHandler()
        self.logger.addHandler(handler);old.close()
        live=io.StringIO()
        with redirect_stderr(live):
            self.assertGreaterEqual(repair(),1)
            self.logger.warning('Generation warning after model loading')
        self.assertEqual(live.getvalue(),'Generation warning after model loading\n')
        self.assertIs(handler.stream,live)
    def test_live_console_and_file_handlers_are_not_retargeted(self):
        live=io.StringIO();console=logging.StreamHandler(live);self.logger.addHandler(console)
        with tempfile.TemporaryDirectory() as root:
            file=logging.FileHandler(Path(root)/'private.log');self.logger.addHandler(file)
            file.close()
            with redirect_stderr(io.StringIO()): repair()
            self.assertIs(console.stream,live)
            self.assertIsNone(file.stream)
    def test_model_loading_no_longer_redirects_console_to_temporary_file(self):
        code=source()
        self.assertNotIn('redirect_stderr',code)
        self.assertNotIn('redirect_stdout',code)
        start=next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='start_assistant')
        self.assertIsInstance(start.body[1],ast.Expr)
        self.assertEqual(start.body[1].value.func.id,'repair_closed_console_logs')
