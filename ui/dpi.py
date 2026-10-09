"""Windows DPI bootstrap — stdlib only, no Qt at module top.

:func:`ensure_dpi_awareness` must run BEFORE any PyQt5 import, or Windows
bitmap-scales the whole window on scaled displays and all text renders
blurry (mirrors ``python/capture.py``). This module deliberately imports
no Qt at the top so importing it can never trigger the Qt import early;
Qt is imported lazily inside :func:`enable_high_dpi_scaling`.
"""
import ctypes


def ensure_dpi_awareness():
    """Per-monitor DPI awareness, with system-aware fallback."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def enable_high_dpi_scaling():
    """Qt-side crisp-text flags. Call before constructing QApplication."""
    from PyQt5 import QtCore, QtWidgets
    QtWidgets.QApplication.setAttribute(
        QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(
        QtCore.Qt.AA_UseHighDpiPixmaps, True)
