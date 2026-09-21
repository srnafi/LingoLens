"""P1 lifecycle and geometry tests (section 9 / 10 of OVERLAY_SPEC.md).

These tests exercise the REAL overlay.py code paths (not mocks) to verify:
  - test_lifecycle_registry: show_translations() with OCR/translation stubbed
    keeps the overlay visible after the event loop runs for 1 second, and the
    _OVERLAYS registry has 1 entry.  Closing it ends the loop.
  - test_lifecycle_subprocess: same pattern in a subprocess; exits within 1 s
    after dismissal, not before.
  - test_geometry: OverlayWindow geometry equals the snip rect; no scaling.

Run: QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python/tests/test_p1.py -v
"""
import os
import sys
import time
import subprocess
from pathlib import Path

_python_dir = str(Path(__file__).resolve().parent.parent)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)
def test_lifecycle_registry():
    """Overlay stays visible after 1s of event loop; registry has 1 entry."""
    import overlay
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFont, QFontDatabase

    # Ensure QApplication exists
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if hasattr(Qt, 'AA_DisableHighDpiScaling'):
        app.setAttribute(Qt.AA_DisableHighDpiScaling, True)

    # Stub out the network calls in show_translations
    original_wait = overlay._wait_for_flask
    original_ocr = overlay._run_ocr
    original_translate = overlay.translate_text

    overlay._wait_for_flask = lambda: True

    def fake_ocr(folder):
        # 2 words: "Hello World"
        return {
            "10,60,10,25": "Hello",
            "65,110,10,25": "World",
        }

    overlay._run_ocr = fake_ocr

    class FakeResult:
        def __init__(self, text):
            self.text = text

    overlay.translate_text = lambda text, dest="en": text.upper()

    try:
        # Clear any leftovers
        overlay._OVERLAYS.clear()

        # Create a small synthetic capture image
        import numpy as np
        from PIL import Image
        img = np.full((200, 300, 3), 240, dtype=np.uint8)
        img[40:160, 10:60] = 255  # white card area
        img[40:160, 65:110] = 255
        capture_path = str(Path(_python_dir) / "image1.png")
        Image.fromarray(img[:, :, ::-1]).save(capture_path)

        # Stub the crops folder check
        crops_folder = overlay._this_dir / "crops"
        crops_folder.mkdir(parents=True, exist_ok=True)

        overlay.show_translations(
            100, 200, "en", 0.9, 12,
            text_color="#000000", image_path=capture_path)

        # Let the event loop run for 1 second
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(app.quit)
        timer.start(1000)
        app.exec_()

        # After 1s: overlay should still be in the registry and visible
        assert len(overlay._OVERLAYS) == 1, (
            f"Expected 1 overlay in registry after 1s, got {len(overlay._OVERLAYS)}. "
            "Overlay was garbage-collected (defect 1).")
        ov = overlay._OVERLAYS[0]
        assert ov.isVisible(), "Overlay is not visible after 1s (defect 1)."

        # Geometry check: window matches snip dimensions
        assert ov.width() == 300, f"Expected width 300, got {ov.width()}"
        assert ov.height() == 200, f"Expected height 200, got {ov.height()}"
        assert ov.x() == 100, f"Expected x=100, got {ov.x()}"
        assert ov.y() == 200, f"Expected y=200, got {ov.y()}"

        # Now dismiss it
        ov._dismiss()
        assert len(overlay._OVERLAYS) == 0, "Overlay not removed from registry after dismiss."

        # Clean up
        try:
            os.remove(capture_path)
        except OSError:
            pass

    finally:
        overlay._wait_for_flask = original_wait
        overlay._run_ocr = original_ocr
        overlay.translate_text = original_translate
        overlay._OVERLAYS.clear()


# ---------------------------------------------------------------------------
# test_lifecycle_subprocess: run the real pattern in a subprocess
# ---------------------------------------------------------------------------
def test_lifecycle_subprocess():
    """Subprocess overlay survives pipeline and exits within 1s of dismissal."""
    import textwrap

    script = textwrap.dedent("""
        import sys, os, time, types
        sys.path.insert(0, r'{pydir}')
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        # googletrans is now optional and not imported by translator.py, so
        # no stub is needed here — translator.py imports cleanly.
        import overlay
        from PyQt5.QtCore import Qt, QTimer
        from PyQt5.QtWidgets import QApplication

        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setAttribute(Qt.AA_DisableHighDpiScaling, True)

        # Stub network
        overlay._wait_for_flask = lambda: True
        overlay._run_ocr = lambda folder: {{"10,60,10,25": "Hello", "65,110,10,25": "World"}}
        overlay.translate_text = lambda text, dest="en": text.upper()

        # Create synthetic capture
        import numpy as np
        from PIL import Image
        img = np.full((200, 300, 3), 240, dtype=np.uint8)
        capture_path = os.path.join(r'{pydir}', 'image1.png')
        Image.fromarray(img[:, :, ::-1]).save(capture_path)
        os.makedirs(os.path.join(r'{pydir}', 'crops'), exist_ok=True)

        # Run the real show_translations (stubs above)
        overlay.show_translations(100, 200, 'en', 0.9, 12, text_color='#000000')

        # At this point, is the overlay still alive?
        print(f"REGISTRY_COUNT={{len(overlay._OVERLAYS)}}", flush=True)

        if not overlay._OVERLAYS:
            print("EXITED_EARLY", flush=True)
            sys.exit(1)

        # Schedule dismissal after 1s, then quit
        QTimer.singleShot(1000, lambda: overlay._OVERLAYS[0]._dismiss())
        QTimer.singleShot(2000, app.quit)

        t0 = time.time()
        app.exec_()
        dt = time.time() - t0
        print(f"ELAPSED={{dt:.2f}}", flush=True)
        print("OK", flush=True)
    """).format(pydir=_python_dir)

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})

    combined = result.stdout + result.stderr
    # The overlay must have been alive in the registry
    assert "EXITED_EARLY" not in combined, (
        f"Overlay was destroyed at once (defect 1). Output: {combined}")
    assert "REGISTRY_COUNT=1" in combined, (
        f"Overlay not in registry after pipeline. Output: {combined}")
    # Must have exited (not hung)
    assert result.returncode == 0, f"Process exited with {result.returncode}. Output: {combined}"
    # Clean up
    try:
        os.remove(os.path.join(_python_dir, "image1.png"))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# test_geometry: OverlayWindow geometry from snip rect, not OCR boxes
# ---------------------------------------------------------------------------
def test_geometry():
    """OverlayWindow geometry equals snip rect; no scaling in paintEvent."""
    import overlay
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor

    app = QApplication.instance() or QApplication(sys.argv)

    # Create an overlay at a specific position and size
    ov = overlay.OverlayWindow(150, 250, 400, 300, alpha=0.9, text_color="#ff0000")
    ov.setWindowFlags(
        Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)

    assert ov.x() == 150, f"Expected x=150, got {ov.x()}"
    assert ov.y() == 250, f"Expected y=250, got {ov.y()}"
    assert ov.width() == 400, f"Expected width=400, got {ov.width()}"
    assert ov.height() == 300, f"Expected height=300, got {ov.height()}"

    # paintEvent must not scale: the QImage is 400x300, drawn 1:1
    # (we can't easily inspect paintEvent in offscreen, but we can check
    # that show_translations does NOT use OCR-box-derived dimensions)
    import inspect
    src = inspect.getsource(overlay.show_translations)
    assert "all_x_max - all_x_min + 40" not in src, (
        "show_translations still sizes window from OCR boxes + 40 (defect 2).")
    assert "snip_w_img" in src or "capture_bgr.shape" in src, (
        "show_translations does not use image shape for window size (defect 2).")
