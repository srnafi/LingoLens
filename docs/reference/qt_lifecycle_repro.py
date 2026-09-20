"""
Reproduces WHY the LingoLens overlay never appears (verified with PyQt5 5.15.14, offscreen).

Run:   python docs/reference/qt_lifecycle_repro.py A     # current code pattern  -> process exits at ~0.6 s, overlay destroyed
       python docs/reference/qt_lifecycle_repro.py B     # strong reference kept -> overlay survives
       python docs/reference/qt_lifecycle_repro.py C     # B + setQuitOnLastWindowClosed(False) -> overlay survives (recommended)

(If your Qt build lacks the offscreen platform plugin, set QT_QPA_PLATFORM to the native one, e.g. windows.)

It mimics capture.py -> detector.main() -> overlay.show_translations():
  1. the selection widget is closed inside a (mouse-release-like) handler,
  2. slow work runs synchronously in that same handler (OCR + translation),
  3. show_translations() creates the overlay in a LOCAL variable, calls show(), and returns.

In variant A the parentless overlay has no owner once show_translations() returns, so Python
garbage-collects it (the C++ window is destroyed). No visible top-level window is left, Qt
quits the event loop, app.exec_() returns, and the process exits. The user sees nothing.

Use this file as the template for an automated regression test against the REAL overlay code:
call the real show_translations() (with OCR/translation stubbed), spin the event loop for
~1 s, assert the overlay is still visible and still registered, then close it and assert
the loop ends.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QWidget

variant = (sys.argv[1] if len(sys.argv) > 1 else "A").upper()
app = QApplication(sys.argv)
if variant == "C":
    app.setQuitOnLastWindowClosed(False)   # in the real fix: quit explicitly when the LAST overlay closes

state = {"overlay_destroyed": False}
_registry = []                             # the real fix: module-level strong references (removed on close)


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(200, 100)
        self.destroyed.connect(lambda *_: state.__setitem__("overlay_destroyed", True))


def show_translations():                   # stands in for overlay.show_translations()
    time.sleep(0.4)                        # OCR + translation latency
    ov = Overlay()                         # <-- local variable, exactly like the current code
    ov.show()
    if variant in ("B", "C"):
        _registry.append(ov)
    # returning here drops the last Python reference in variant A


capture = QWidget()
capture.resize(300, 300)
capture.show()


def mouse_release_like():
    capture.close()                        # capture.py: self.close()
    show_translations()                    # capture.py: detector.main(...) -> overlay.show_translations()


QTimer.singleShot(200, mouse_release_like)
QTimer.singleShot(1500, lambda: print(
    f"[{variant}] t=1.5s overlay_destroyed={state['overlay_destroyed']} "
    f"visible_overlays={sum(1 for w in QApplication.topLevelWidgets() if isinstance(w, Overlay) and w.isVisible())}", flush=True))
QTimer.singleShot(3000, app.quit)          # watchdog so the script always terminates

t0 = time.time()
app.exec_()
dt = time.time() - t0
verdict = "EXITED EARLY -> bug reproduced (overlay gone)" if dt < 2.5 else "stayed alive until the watchdog -> OK"
print(f"[{variant}] exec_() returned after {dt:.2f}s (watchdog 3.00s), overlay_destroyed={state['overlay_destroyed']} -> {verdict}")
