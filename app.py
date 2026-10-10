"""LingoLens Control Center — thin DPI-first launcher.

DPI awareness runs BEFORE any Qt import (or Windows bitmap-scales the
whole window and all text renders blurry). Everything else lives in
the ui/ package: LingoLensControlCenter in ui.main_window is the real
window (custom-painted Prism glass + theme morph, no global QSS),
backed by SettingsStore (prefs) and Backend (Flask :5000 + snip +
hotkey). Backend contracts unchanged: Flask ocr_server.py
<source_lang_option> on :5000, capture.py argv order, Alt+Shift+M.
"""
from ui.dpi import enable_high_dpi_scaling, ensure_dpi_awareness

ensure_dpi_awareness()

from pathlib import Path  # noqa: E402

from PyQt5 import QtGui, QtWidgets  # noqa: E402

from ui.main_window import LingoLensControlCenter  # noqa: E402

if __name__ == "__main__":
    # Crisp text on scaled displays (pairs with the per-monitor DPI
    # awareness set above, before the Qt import).
    enable_high_dpi_scaling()
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")  # consistent base style on every OS
    _logo_path = Path(__file__).parent / "logo.png"
    if _logo_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(_logo_path)))
    window = LingoLensControlCenter()
    window.show()
    app.exec_()
