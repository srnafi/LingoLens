import sys
import os
import json
import subprocess
import ctypes
import ctypes.wintypes
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui

SETTINGS_FILE = Path(__file__).parent / "settings.json"

# Modern Dark Theme Stylesheet (Catppuccin Mocha aesthetic)
DARK_STYLESHEET = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10pt;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 8px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:checked {
    background-color: #89b4fa;
    color: #11111b;
    font-weight: bold;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 15px;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QSlider::groove:horizontal {
    border: 1px solid #45475a;
    height: 6px;
    background: #313244;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    border: none;
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #b4befe;
}
QScrollArea {
    border: none;
    background: transparent;
}
"""

class LingoLensControlCenter(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LingoLens - Next-Gen AI Translation & OCR")
        self.resize(800, 600)
        self.setMinimumSize(700, 500)
        self.setStyleSheet(DARK_STYLESHEET)

        # State variables & advanced customization defaults
        self.source_lang_option = 1  
        self.dest_lang = "en"
        self.fill_color = "#ff0000"
        self.text_color = "#000000"
        self.opacity = 0.3
        self.line_width = 3
        self.alpha = 0.7
        self.font_size = 12

        self.flask_process = None
        self.snip_process = None
        self.nativeEventFilter = None

        self.init_ui()
        self.load_settings()
        self.start_flask_server()
        self.init_global_hotkey()

    def save_settings(self):
        """Persist user preferences to disk."""
        settings = {
            "source_lang_option": self.source_lang_option,
            "dest_lang": self.dest_lang,
            "fill_color": self.fill_color,
            "text_color": self.text_color,
            "opacity": self.opacity,
            "line_width": self.line_width,
            "alpha": self.alpha,
            "font_size": self.font_size,
        }
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def load_settings(self):
        """Load user preferences from disk if available."""
        if not SETTINGS_FILE.exists():
            return
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            self.source_lang_option = settings.get("source_lang_option", 1)
            self.dest_lang = settings.get("dest_lang", "en")
            self.fill_color = settings.get("fill_color", "#ff0000")
            self.text_color = settings.get("text_color", "#000000")
            self.opacity = settings.get("opacity", 0.3)
            self.line_width = settings.get("line_width", 3)
            self.alpha = settings.get("alpha", 0.7)
            self.font_size = settings.get("font_size", 12)
            # Update UI sliders to reflect loaded values
            self.opacity_slider.setValue(int(self.opacity * 100))
            self.linewidth_slider.setValue(self.line_width)
            self.alpha_slider.setValue(int(self.alpha * 100))
            self.fontsize_slider.setValue(self.font_size)
            self.color_btn.setText(f"Pick Color ({self.fill_color})")
            self.text_color_btn.setText(f"Pick Text Color ({self.text_color})")
            print(f"Settings loaded from {SETTINGS_FILE}")
        except Exception as e:
            print(f"Failed to load settings: {e}")

    def reset_defaults(self):
        """Reset all settings to factory defaults."""
        self.source_lang_option = 1
        self.dest_lang = "en"
        self.fill_color = "#ff0000"
        self.text_color = "#000000"
        self.opacity = 0.3
        self.line_width = 3
        self.alpha = 0.7
        self.font_size = 12
        # Update UI
        self.opacity_slider.setValue(30)
        self.linewidth_slider.setValue(3)
        self.alpha_slider.setValue(70)
        self.fontsize_slider.setValue(12)
        self.color_btn.setText("Pick Color (#ff0000)")
        self.text_color_btn.setText("Pick Text Color (#000000)")
        self.save_settings()
        self.restart_flask_server()
        print("Settings reset to defaults")

    def init_ui(self):
        # Sidebar Navigation Panel
        sidebar = QtWidgets.QVBoxLayout()
        sidebar.setContentsMargins(0, 0, 0, 0)
        sidebar.setSpacing(10)

        title_label = QtWidgets.QLabel("LingoLens")
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #89b4fa; margin-bottom: 10px;")
        sidebar.addWidget(title_label)
        
        btn_ocr = QtWidgets.QPushButton("🌐 Languages & OCR")
        btn_capture = QtWidgets.QPushButton("🎨 Overlay & Capture")
        btn_overlay = QtWidgets.QPushButton("⚙️ Font & Alpha")
        
        btn_snip_now = QtWidgets.QPushButton("⚡ Snip & Translate Now")
        btn_snip_now.setStyleSheet("""
            background-color: #a6e3a1; 
            color: #11111b; 
            font-weight: bold; 
            font-size: 11pt;
            padding: 12px;
            border-radius: 8px;
        """)
        btn_snip_now.clicked.connect(self.trigger_snip)

        btn_reset = QtWidgets.QPushButton("↺ Reset Defaults")
        btn_reset.setStyleSheet("color: #f38ba8; font-size: 9pt;")
        btn_reset.clicked.connect(self.reset_defaults)

        for btn in (btn_ocr, btn_capture, btn_overlay):
            btn.setStyleSheet("text-align: left; padding: 10px; border-radius: 6px;")

        sidebar.addWidget(btn_ocr)
        sidebar.addWidget(btn_capture)
        sidebar.addWidget(btn_overlay)
        sidebar.addStretch()
        sidebar.addWidget(btn_reset)
        sidebar.addWidget(btn_snip_now)

        sidebar_widget = QtWidgets.QWidget()
        sidebar_widget.setLayout(sidebar)
        sidebar_widget.setFixedWidth(200)

        # Stacked Pages
        self.stack = QtWidgets.QStackedWidget()

        # Page 1: Languages Selection
        page1 = QtWidgets.QWidget()
        p1_layout = QtWidgets.QHBoxLayout(page1)
        p1_layout.setContentsMargins(0, 0, 0, 0)

        # Source Languages
        src_group = QtWidgets.QGroupBox("Source Language (OCR)")
        src_layout = QtWidgets.QVBoxLayout()
        src_scroll = QtWidgets.QScrollArea()
        src_scroll.setWidgetResizable(True)
        src_content = QtWidgets.QWidget()
        src_content_layout = QtWidgets.QVBoxLayout(src_content)

        self.src_buttons = {}
        sources = [
            ("English / Multilingual", 1),
            ("Spanish", 1),
            ("French", 1),
            ("Italian", 1),
            ("Portuguese", 1),
            ("Vietnamese", 1),
            ("German", 1),
            ("Chinese", 2),
            ("Japanese", 3),
            ("Russian", 4),
            ("Bengali", 5),
            ("Korean", 6)
        ]
        for name, val in sources:
            btn = QtWidgets.QPushButton(name)
            btn.setCheckable(True)
            if val == 1 and name.startswith("English"):
                btn.setChecked(True)
                self.current_src_btn = btn
            btn.clicked.connect(lambda checked, v=val, b=btn: self.set_source_language(v, b))
            src_content_layout.addWidget(btn)
            self.src_buttons[name] = btn
        src_content_layout.addStretch()
        src_scroll.setWidget(src_content)
        src_layout.addWidget(src_scroll)
        src_group.setLayout(src_layout)

        # Destination Languages
        dest_group = QtWidgets.QGroupBox("Destination Language (Translation)")
        dest_layout = QtWidgets.QVBoxLayout()
        dest_scroll = QtWidgets.QScrollArea()
        dest_scroll.setWidgetResizable(True)
        dest_content = QtWidgets.QWidget()
        dest_content_layout = QtWidgets.QVBoxLayout(dest_content)

        self.dest_buttons = {}
        destinations = [
            ("English", "en"), ("Spanish", "es"), ("French", "fr"), ("German", "de"),
            ("Italian", "it"), ("Portuguese", "pt"), ("Russian", "ru"), ("Vietnamese", "vi"),
            ("Bengali", "bn"), ("Hindi", "hi"), ("Chinese (Simplified)", "zh-CN"),
            ("Japanese", "ja"), ("Korean", "ko"), ("Arabic", "ar"), ("Urdu", "ur"),
            ("Dutch", "nl"), ("Turkish", "tr"), ("Polish", "pl"), ("Indonesian", "id"), ("Thai", "th")
        ]
        for name, d in destinations:
            btn = QtWidgets.QPushButton(name)
            btn.setCheckable(True)
            if d == "en":
                btn.setChecked(True)
                self.current_dest_btn = btn
            btn.clicked.connect(lambda checked, lang=d, b=btn: self.set_dest_language(lang, b))
            dest_content_layout.addWidget(btn)
            self.dest_buttons[d] = btn
        dest_content_layout.addStretch()
        dest_scroll.setWidget(dest_content)
        dest_layout.addWidget(dest_scroll)
        dest_group.setLayout(dest_layout)

        p1_layout.addWidget(src_group)
        p1_layout.addWidget(dest_group)
        self.stack.addWidget(page1)

        # Page 2: Capture Window & Customization Settings
        page2 = QtWidgets.QWidget()
        p2_layout = QtWidgets.QVBoxLayout(page2)
        
        custom_group = QtWidgets.QGroupBox("Capture & Overlay Customization")
        custom_layout = QtWidgets.QVBoxLayout()

        color_layout = QtWidgets.QHBoxLayout()
        color_layout.addWidget(QtWidgets.QLabel("Selection Box Fill Color:"))
        self.color_btn = QtWidgets.QPushButton("Pick Color (#ff0000)")
        self.color_btn.clicked.connect(self.pick_color)
        color_layout.addWidget(self.color_btn)
        custom_layout.addLayout(color_layout)

        text_color_layout = QtWidgets.QHBoxLayout()
        text_color_layout.addWidget(QtWidgets.QLabel("Translated Text Color:"))
        self.text_color_btn = QtWidgets.QPushButton("Pick Text Color (#000000)")
        self.text_color_btn.clicked.connect(self.pick_text_color)
        text_color_layout.addWidget(self.text_color_btn)
        custom_layout.addLayout(text_color_layout)

        custom_layout.addWidget(QtWidgets.QLabel("Selection Box Opacity (0.0 - 1.0):"))
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(30)
        self.opacity_slider.setToolTip("Controls how visible the selection box is while drawing")
        self.opacity_slider.valueChanged.connect(self.update_opacity)
        custom_layout.addWidget(self.opacity_slider)

        custom_layout.addWidget(QtWidgets.QLabel("Selection Border Line Width (1 - 10):"))
        self.linewidth_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.linewidth_slider.setRange(1, 10)
        self.linewidth_slider.setValue(3)
        self.linewidth_slider.setToolTip("Thickness of the selection box border")
        self.linewidth_slider.valueChanged.connect(self.update_linewidth)
        custom_layout.addWidget(self.linewidth_slider)
        
        custom_group.setLayout(custom_layout)
        p2_layout.addWidget(custom_group)
        p2_layout.addStretch()
        self.stack.addWidget(page2)

        # Page 3: Font & Alpha Settings
        page3 = QtWidgets.QWidget()
        p3_layout = QtWidgets.QVBoxLayout(page3)

        font_group = QtWidgets.QGroupBox("Overlay Window Appearance")
        font_layout = QtWidgets.QVBoxLayout()

        font_layout.addWidget(QtWidgets.QLabel("Overlay Background Alpha / Transparency (0.0 - 1.0):"))
        self.alpha_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(70)
        self.alpha_slider.setToolTip("Transparency of the translated text overlay windows")
        self.alpha_slider.valueChanged.connect(self.update_alpha)
        font_layout.addWidget(self.alpha_slider)

        font_layout.addWidget(QtWidgets.QLabel("Translated Text Font Size (5 - 25):"))
        self.fontsize_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.fontsize_slider.setRange(5, 25)
        self.fontsize_slider.setValue(12)
        self.fontsize_slider.setToolTip("Size of the translated text displayed on screen")
        self.fontsize_slider.valueChanged.connect(self.update_fontsize)
        font_layout.addWidget(self.fontsize_slider)

        font_group.setLayout(font_layout)
        p3_layout.addWidget(font_group)
        p3_layout.addStretch()
        self.stack.addWidget(page3)

        # Status bar at bottom
        status_widget = QtWidgets.QWidget()
        status_layout = QtWidgets.QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 5, 0, 0)
        self.status_label = QtWidgets.QLabel("🔴 Flask OCR: starting...")
        self.status_label.setStyleSheet("color: #f38ba8; font-size: 9pt;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        self.hotkey_label = QtWidgets.QLabel("Hotkey: Alt+Shift+M")
        self.hotkey_label.setStyleSheet("color: #6c7086; font-size: 9pt;")
        status_layout.addWidget(self.hotkey_label)

        outer_layout = QtWidgets.QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QHBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 15, 15, 0)
        content_layout.setSpacing(15)
        content_layout.addWidget(sidebar_widget)
        content_layout.addWidget(self.stack)
        outer_layout.addWidget(content_widget)
        outer_layout.addWidget(status_widget)
        self.setLayout(outer_layout)

        # Remove the old direct layout additions
        # Connect sidebar navigation
        btn_ocr.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        btn_capture.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        btn_overlay.clicked.connect(lambda: self.stack.setCurrentIndex(2))

    def set_source_language(self, val, btn):
        if hasattr(self, 'current_src_btn'):
            self.current_src_btn.setChecked(False)
        self.current_src_btn = btn
        btn.setChecked(True)
        self.source_lang_option = val
        print(f"Source language option updated: {val}")
        self.save_settings()
        self.restart_flask_server()

    def set_dest_language(self, lang, btn):
        if hasattr(self, 'current_dest_btn'):
            self.current_dest_btn.setChecked(False)
        self.current_dest_btn = btn
        btn.setChecked(True)
        self.dest_lang = lang
        print(f"Destination language updated: {lang}")
        self.save_settings()

    def pick_color(self):
        col = QtWidgets.QColorDialog.getColor()
        if col.isValid():
            self.fill_color = col.name()
            self.color_btn.setText(f"Pick Color ({self.fill_color})")
            self.save_settings()

    def pick_text_color(self):
        col = QtWidgets.QColorDialog.getColor()
        if col.isValid():
            self.text_color = col.name()
            self.text_color_btn.setText(f"Pick Text Color ({self.text_color})")
            self.save_settings()

    def update_opacity(self, val):
        self.opacity = val / 100.0
        self.save_settings()

    def update_linewidth(self, val):
        self.line_width = val
        self.save_settings()

    def update_alpha(self, val):
        self.alpha = val / 100.0
        self.save_settings()

    def update_fontsize(self, val):
        self.font_size = val
        self.save_settings()

    def start_flask_server(self):
        python_executable = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
        if not python_executable.exists():
            python_executable = sys.executable
        server_script = Path(__file__).parent / "python" / "ocr_server.py"
        
        cmd = [str(python_executable), str(server_script), str(self.source_lang_option)]
        print(f"Starting Flask server: {' '.join(cmd)}")
        try:
            self.flask_process = subprocess.Popen(cmd)
            self._poll_flask_health()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to start Flask OCR server: {e}")

    def _poll_flask_health(self):
        """Poll Flask /health endpoint and update status label."""
        import requests as _requests
        def check():
            try:
                resp = _requests.get("http://localhost:5000/health", timeout=2)
                if resp.status_code == 200:
                    self.status_label.setText("🟢 Flask OCR: ready")
                    self.status_label.setStyleSheet("color: #a6e3a1; font-size: 9pt;")
                else:
                    self.status_label.setText("🟡 Flask OCR: initializing...")
                    self.status_label.setStyleSheet("color: #f9e2af; font-size: 9pt;")
                    QtCore.QTimer.singleShot(2000, check)
            except Exception:
                self.status_label.setText("🔴 Flask OCR: not running")
                self.status_label.setStyleSheet("color: #f38ba8; font-size: 9pt;")
                QtCore.QTimer.singleShot(3000, check)
        QtCore.QTimer.singleShot(2000, check)

    def restart_flask_server(self):
        if self.flask_process:
            print("Terminating old Flask server...")
            self.flask_process.terminate()
            try:
                self.flask_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.flask_process.kill()
        self.start_flask_server()

    def trigger_snip(self):
        python_executable = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
        if not python_executable.exists():
            python_executable = sys.executable
        snip_script = Path(__file__).parent / "python" / "capture.py"

        cmd = [
            str(python_executable),
            str(snip_script),
            str(self.dest_lang),
            str(self.fill_color),
            str(self.opacity),
            str(self.line_width),
            str(self.alpha),
            str(self.font_size),
            str(self.text_color),
        ]
        print(f"Launching screen snipper script: {' '.join(cmd)}")
        try:
            self.snip_process = subprocess.Popen(cmd, cwd=str(snip_script.parent))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Warning", f"Failed to launch screen snipper script: {e}")

    def init_global_hotkey(self):
        if sys.platform == 'win32':
            try:
                ctypes.windll.user32.RegisterHotKey(None, 1, 0x0001 | 0x0004, 0x4D)
                self.nativeEventFilter = HotkeyFilter(self.trigger_snip)
                app_instance = QtWidgets.QApplication.instance()
                if app_instance:
                    app_instance.installNativeEventFilter(self.nativeEventFilter)
                print("Global hotkey Alt+Shift+M registered successfully.")
            except Exception as e:
                print(f"Failed to register global hotkey: {e}")

    def closeEvent(self, a0: QtGui.QCloseEvent):
        if self.flask_process:
            self.flask_process.terminate()
        if sys.platform == 'win32':
            try:
                ctypes.windll.user32.UnregisterHotKey(None, 1)
            except:
                pass
        a0.accept()

if sys.platform == 'win32':
    class HotkeyFilter(QtCore.QAbstractNativeEventFilter):
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

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = LingoLensControlCenter()
    window.show()
    sys.exit(app.exec_())
