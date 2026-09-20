"""Conftest for python/ level tests.

Sets QT_QPA_PLATFORM=offscreen and stubs googletrans so that importing
overlay.py (which imports translator.py which imports googletrans) does
not crash with ImportError when googletrans is not installed.
"""
import os
import sys
import types

os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Stub googletrans so translator.py's top-level import succeeds in tests.
# The real translation is mocked/stubbed where needed.
if "googletrans" not in sys.modules:
    _stub = types.ModuleType("googletrans")
    class _FakeTranslator:
        def translate(self, text, dest=None, src=None):
            raise RuntimeError("googletrans stub: not available in tests")
    _stub.Translator = _FakeTranslator
    sys.modules["googletrans"] = _stub
