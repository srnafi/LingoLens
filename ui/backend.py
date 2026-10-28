"""Backend process management — Flask OCR server + snip subprocess + hotkey.

Thin layer over subprocess: the ONLY place child-process argv is built.
Contracts (must not drift):
  - Flask: ``python/ocr_server.py <source_lang_option>``, :5000, /health.
  - Snip: ``python/capture.py dest fill opacity width alpha fontsize color``.
  - Global hotkey: Alt+Shift+M (win32 only).
"""
import os
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
                    ocr_engine="easyocr", source_option=1, provider="auto"):
        """Launch the freeze-frame screen snipper (positional argv).

        argv carries only the capture-box values. ``capture.py`` still accepts
        the retired overlay-text arguments (alpha / font size / text colour)
        at their old positions, so it falls back to its own defaults and the
        overlay keeps deriving colour and size from the source pixels.

        The OCR backend, the source-language bundle and the translation
        provider travel in the child environment (``LINGOLENS_OCR_ENGINE`` /
        ``LINGOLENS_SOURCE_OPTION`` / ``LINGOLENS_TRANSLATE_PROVIDER``), so the
        positional argv contract stays exactly as it was.
        """
        snip_script = self.root / "python" / "capture.py"
        cmd = [
            venv_python(self.root),
            str(snip_script),
            str(dest_lang),
            str(fill_color),
            str(opacity),
            str(line_width),
        ]
        env = os.environ.copy()
        env["LINGOLENS_OCR_ENGINE"] = str(ocr_engine)
        env["LINGOLENS_SOURCE_OPTION"] = str(source_option)
        env["LINGOLENS_TRANSLATE_PROVIDER"] = str(provider or "auto")
        print(f"Launching screen snipper script: {' '.join(cmd)} "
              f"(engine={ocr_engine}, source_option={source_option}, "
              f"provider={provider})")
        try:
            self.snip_process = subprocess.Popen(
                cmd, cwd=str(snip_script.parent), env=env)
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


# RegisterHotKey modifier flags (winuser.h).
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000

# Named keys -> virtual-key codes. Letters and digits are handled by ord().
_NAMED_KEYS = {
    "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "RETURN": 0x0D, "ESC": 0x1B,
    "ESCAPE": 0x1B, "BACKSPACE": 0x08, "DELETE": 0x2E, "INSERT": 0x2D,
    "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "PRINTSCREEN": 0x2C, "PAUSE": 0x13, "CAPSLOCK": 0x14,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}

# Virtual keys Windows will accept for a global hotkey; anything else is either
# modifier-only or reserved.
_RESERVED_VK = {0x5B, 0x5C, 0x5D, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
                0x10, 0x11, 0x12, 0x14, 0x5F, 0x6F, 0x90, 0x91, 0xFF}


def parse_hotkey(sequence):
    """Return ``(modifier_flags, virtual_key)`` for "Ctrl+Alt+T", or None.

    Also returns None for shortcuts Windows cannot register (no modifier, or a
    modifier as the main key), so the UI can refuse a bad choice instead of
    silently installing a hotkey that never fires.
    """
    if not sequence or not isinstance(sequence, str):
        return None
    mods = 0
    key = None
    for part in sequence.replace(" ", "").split("+"):
        low = part.lower()
        if low in ("ctrl", "control"):
            mods |= _MOD_CONTROL
        elif low == "alt":
            mods |= _MOD_ALT
        elif low == "shift":
            mods |= _MOD_SHIFT
        elif low in ("win", "meta", "super"):
            mods |= _MOD_WIN
        elif part:
            if key is not None:  # two non-modifier keys: not a hotkey
                return None
            key = part
    if not mods or not key:
        return None
    up = key.upper()
    if len(up) == 1 and ("A" <= up <= "Z" or "0" <= up <= "9"):
        vk = ord(up)
    elif up.startswith("F") and up[1:].isdigit() and 1 <= int(up[1:]) <= 24:
        vk = 0x6F + int(up[1:])  # F1 = 0x70
    else:
        vk = _NAMED_KEYS.get(up)
    if not vk or vk in _RESERVED_VK:
        return None
    return mods, vk


def hotkey_supported(sequence):
    """True when ``sequence`` can be registered as a Windows global hotkey."""
    return parse_hotkey(sequence) is not None


def register_hotkey(callback, sequence="Alt+Shift+M"):
    """Register a global hotkey; returns the filter (keep alive!) or None.

    Any previously registered hotkey is released first, so this can be called
    again when the user picks a new shortcut.
    """
    if sys.platform != "win32":
        return None
    parsed = parse_hotkey(sequence)
    if parsed is None:
        print(f"Invalid hotkey sequence: {sequence!r}")
        return None
    mods, vk = parsed
    try:
        unregister_hotkey()
        ok = ctypes.windll.user32.RegisterHotKey(
            None, 1, mods | _MOD_NOREPEAT, vk)
        if not ok:
            err = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else ""
            print(f"Failed to register global hotkey {sequence} "
                  f"(code {ctypes.windll.kernel32.GetLastError()}) {err}")
            return None
        from PyQt5 import QtWidgets
        filt = HotkeyFilter(callback)
        app_instance = QtWidgets.QApplication.instance()
        if app_instance:
            app_instance.installNativeEventFilter(filt)
        print(f"Global hotkey {sequence} registered successfully.")
        return filt
    except Exception as e:
        print(f"Failed to register global hotkey: {e}")
        return None


# ---- start with Windows -----------------------------------------------------
# HKCU\...\Run is per-user and needs no elevation, so no new dependency and no
# admin prompt. The value points at the console-less interpreter when present.
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "LingoLens"


def _autostart_command(root):
    """Command line stored in the Run key: pythonw app.py, quoted."""
    exe = Path(root) / ".venv" / "Scripts" / "pythonw.exe"
    if not exe.exists():
        exe = Path(venv_python(root))
    return f'"{exe}" "{Path(root) / "app.py"}"'


def is_autostart_enabled():
    """True when the Run entry exists (the real registry state)."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_VALUE)
        return True
    except OSError:
        return False


def set_autostart(root, enabled):
    """Create or remove the Run entry. Returns True on success."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ,
                                  _autostart_command(root))
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError as e:
        print(f"Failed to update autostart entry: {e}")
        return False


def unregister_hotkey():
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.UnregisterHotKey(None, 1)
        except Exception:
            pass
