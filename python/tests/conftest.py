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
# translator.py no longer imports googletrans (defect 9 fixed), so no stub
# is needed.  Tests that need network translation stub translate_text
# at the test level.
# ---------------------------------------------------------------------------
