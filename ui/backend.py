"""Backend process management — Flask OCR server + snip subprocess + hotkey.

Thin layer over subprocess: the ONLY place child-process argv is built.
Contracts (must not drift):
  - Flask: ``python/ocr_server.py <source_lang_option>``, :5000, /health.
  - Snip: ``python/capture.py dest fill opacity width alpha fontsize color``.
  - Global hotkey: Alt+Shift+M (win32 only).
"""
import subprocess
import sys
import ctypes
import ctypes.wintypes
from pathlib import Path

from PyQt5 import QtCore


def venv_python(root):
    """Project venv interpreter, falling back to the running one."""
    exe = root / ".venv" / "Scripts" / "python.exe"
    return str(exe) if exe.exists() else sys.executable


class Backend:
    """Owns the Flask OCR server and snip subprocess lifetimes."""

    def __init__(self, root, on_health=None):
        self.root = root
        self.flask_process = None
        self.snip_process = None
        self._on_health = on_health  # callback: fn("ready"|"starting"|"offline")

    # ---- Flask OCR server ----
    def start_flask_server(self, source_lang_option):
        """Boot the EasyOCR server for the given source-language option."""
        cmd = [venv_python(self.root), str(self.root / "python" / "ocr_server.py"),
               str(source_lang_option)]
        print(f"Starting Flask server: {' '.join(cmd)}")
        try:
            self.flask_process = subprocess.Popen(cmd)
            self._poll_health()
        except Exception as e:
            print(f"Failed to start Flask OCR server: {e}")
            self._report("offline")
            return e
        return None

    def restart_flask_server(self, source_lang_option):
        """Kill the current server (if any) and boot a fresh one."""
        if self.flask_process:
            print("Terminating old Flask server...")
            self.flask_process.terminate()
            try:
                self.flask_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.flask_process.kill()
        self._report("starting")
        return self.start_flask_server(source_lang_option)

    def stop(self):
        if self.flask_process:
            self.flask_process.terminate()
            self.flask_process = None

    def _report(self, state):
        if self._on_health:
            self._on_health(state)

    def _poll_health(self):
        """Poll Flask /health; reflect it through the on_health callback."""
        import requests as _requests

        def check():
            try:
                resp = _requests.get("http://localhost:5000/health", timeout=2)
                if resp.status_code == 200:
                    self._report("ready")
                else:
                    self._report("starting")
                    QtCore.QTimer.singleShot(2000, check)
            except Exception:
                self._report("offline")
                QtCore.QTimer.singleShot(3000, check)
        QtCore.QTimer.singleShot(2000, check)

    def recheck_health(self):
        """Manual re-check; restart the server if it is down."""
        import requests as _requests
        try:
            resp = _requests.get("http://localhost:5000/health", timeout=2)
            if resp.status_code == 200:
                self._report("ready")
                return
            self._report("starting")
        except Exception:
            self._report("offline")
            print("Status check failed — restarting Flask server...")
            return "restart"

    # ---- snip subprocess ----
    def launch_snip(self, dest_lang, fill_color, opacity, line_width,
                    alpha, font_size, text_color):
        """Launch the freeze-frame screen snipper (positional argv)."""
        snip_script = self.root / "python" / "capture.py"
        cmd = [
            venv_python(self.root),
            str(snip_script),
            str(dest_lang),
            str(fill_color),
            str(opacity),
            str(line_width),
            str(alpha),
            str(font_size),
            str(text_color),
        ]
        print(f"Launching screen snipper script: {' '.join(cmd)}")
        try:
            self.snip_process = subprocess.Popen(
                cmd, cwd=str(snip_script.parent))
        except Exception as e:
            print(f"Failed to launch screen snipper script: {e}")
            return e
        return None


if sys.platform == "win32":
    class HotkeyFilter(QtCore.QAbstractNativeEventFilter):
        """Alt+Shift+M global hotkey filter (win32 only)."""

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        def nativeEventFilter(self, eventType, message):
            if eventType == b"windows_generic_MSG" or eventType == "windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:  # WM_HOTKEY
                    if msg.wParam == 1:
                        self.callback()
                        return True, 0
            return False, 0


def register_hotkey(callback):
    """Register Alt+Shift+M; returns the filter (keep alive!) or None."""
    if sys.platform != "win32":
        return None
    try:
        ctypes.windll.user32.RegisterHotKey(None, 1, 0x0001 | 0x0004, 0x4D)
        from PyQt5 import QtWidgets
        filt = HotkeyFilter(callback)
        app_instance = QtWidgets.QApplication.instance()
        if app_instance:
            app_instance.installNativeEventFilter(filt)
        print("Global hotkey Alt+Shift+M registered successfully.")
        return filt
    except Exception as e:
        print(f"Failed to register global hotkey: {e}")
        return None


def unregister_hotkey():
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.UnregisterHotKey(None, 1)
        except Exception:
            pass
