"""Pytest configuration: headless Qt + stub googletrans/translator for offline tests.

Sets QT_QPA_PLATFORM=offscreen so no display is needed. Stubs googletrans (not
installed and not needed for tests that mock translation) so importing overlay.py
(which imports translator.py) never raises ImportError.
"""
import os
import sys
import types

# Headless Qt: must be set before QApplication is created anywhere.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure python/ is on sys.path so `import overlay` etc. work from tests/.
_python_dir = os.path.join(os.path.dirname(__file__), "..")
_python_dir = os.path.abspath(_python_dir)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

# ---------------------------------------------------------------------------
# Stub googletrans so translator.py's top-level import succeeds in tests.
# translator.py does: from googletrans import Translator
# We provide a dummy module; real translation is stubbed at the test level.
# ---------------------------------------------------------------------------
if "googletrans" not in sys.modules:
    _stub = types.ModuleType("googletrans")
    class _FakeTranslator:
        def translate(self, text, dest=None, src=None):
            raise RuntimeError("googletrans stub: not available in tests")
    _stub.Translator = _FakeTranslator
    sys.modules["googletrans"] = _stub

# Also stub translator itself for tests that don't want network.
# Tests that need real translator behavior should import it directly.
