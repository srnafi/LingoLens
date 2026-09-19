import sys
import os
import subprocess
import ctypes
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui

class LingoLensApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LingoLens - Python Control Center")
        self.resize(600, 500)

        # State variables matching Electron app defaults
        self.source_lang_option = 1  # 1: Default (en, es, fr, etc.), 2: Chinese, 3: Japanese, 4: Russian, 5: Bengali, 6: Korean
        self.dest_lang = "en"
        self.fill_color = "#ff0000"
        self.opacity = 0.3
        self.line_width = 3
        self.alpha = 0.5
        self.font_size = 10

        self.flask_process = None
        self.snip_process = None

        self.init_ui()
        self.start_flask_server()
        self.init_global_hotkey()

    def init_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)

        # Sidebar navigation
        sidebar = QtWidgets.QVBoxLayout()
        sidebar.setContentsMargins(0, 0, 0, 0)
        
        btn_ocr = QtWidgets.QPushButton("OCR / Languages")
        btn_capture = QtWidgets.QPushButton("Capture Settings")
        btn_overlay = QtWidgets.QPushButton("Overlay & Font")
        btn_snip_now = QtWidgets.QPushButton("Snip & Translate Now")
        btn_snip_now.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")

        sidebar.addWidget(btn_ocr)
        sidebar.addWidget(btn_capture)
        sidebar.addWidget(btn_overlay)
        sidebar.addStretch()
        sidebar.addWidget(btn_snip_now)

        sidebar_widget = QtWidgets.QWidget()
        sidebar_widget.setLayout(sidebar)
        sidebar_widget.setFixedWidth(160)
        sidebar_widget.setStyleSheet("background-color: #333333; color: white; padding: 10px;")

        # Stacked pages for settings sections
        self.stack = QtWidgets.QStackedWidget()

        # Page 1: Languages
        page1 = QtWidgets.QWidget()
        p1_layout = QtWidgets.QHBoxLayout(page1)
        
        # Source languages
        src_group = QtWidgets.QGroupBox("Source Language")
        src_layout = QtWidgets.QVBoxLayout()
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
            src_layout.addWidget(btn)
            self.src_buttons[name] = btn
        src_group.setLayout(src_layout)

        # Destination languages
        dest_group = QtWidgets.QGroupBox("Destination Language")
        dest_layout = QtWidgets.QVBoxLayout()
        self.dest_buttons = {}
        destinations = ["en", "es", "fr", "de", "it", "pt", "ru", "vi", "bn"]
        for d in destinations:
            btn = QtWidgets.QPushButton(d.upper())
            btn.setCheckable(True)
            if d == "en":
                btn.setChecked(True)
                self.current_dest_btn = btn
            btn.clicked.connect(lambda checked, lang=d, b=btn: self.set_dest_language(lang, b))
            dest_layout.addWidget(btn)
            self.dest_buttons[d] = btn
        dest_group.setLayout(dest_layout)

        p1_layout.addWidget(src_group)
        p1_layout.addWidget(dest_group)
        self.stack.addWidget(page1)

        # Page 2: Capture Window Settings
        page2 = QtWidgets.QWidget()
        p2_layout = QtWidgets.QVBoxLayout(page2)
        
        color_layout = QtWidgets.QHBoxLayout()
        color_layout.addWidget(QtWidgets.QLabel("Fill Color:"))
        self.color_btn = QtWidgets.QPushButton("Pick Color (#ff0000)")
        self.color_btn.clicked.connect(self.pick_color)
        color_layout.addWidget(self.color_btn)
        p2_layout.addLayout(color_layout)

        p2_layout.addWidget(QtWidgets.QLabel("Overlay Opacity (0.0 - 1.0):"))
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(30)
        self.opacity_slider.valueChanged.connect(self.update_opacity)
        p2_layout.addWidget(self.opacity_slider)

        p2_layout.addWidget(QtWidgets.QLabel("Line Width (1 - 10):"))
        self.linewidth_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.linewidth_slider.setRange(1, 10)
        self.linewidth_slider.setValue(3)
        self.linewidth_slider.valueChanged.connect(self.update_linewidth)
        p2_layout.addWidget(self.linewidth_slider)
        p2_layout.addStretch()
        self.stack.addWidget(page2)

        # Page 3: Overlay & Font Settings
        page3 = QtWidgets.QWidget()
        p3_layout = QtWidgets.QVBoxLayout(page3)

        p3_layout.addWidget(QtWidgets.QLabel("Translation Window Alpha (0.0 - 1.0):"))
        self.alpha_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(50)
        self.alpha_slider.valueChanged.connect(self.update_alpha)
        p3_layout.addWidget(self.alpha_slider)

        p3_layout.addWidget(QtWidgets.QLabel("Font Size (5 - 20):"))
        self.fontsize_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.fontsize_slider.setRange(5, 20)
        self.fontsize_slider.setValue(10)
        self.fontsize_slider.valueChanged.connect(self.update_fontsize)
        p3_layout.addWidget(self.fontsize_slider)
        p3_layout.addStretch()
        self.stack.addWidget(page3)

        main_layout.addWidget(sidebar_widget)
        main_layout.addWidget(self.stack)

        # Connect sidebar navigation
        btn_ocr.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        btn_capture.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        btn_overlay.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        btn_snip_now.clicked.connect(self.trigger_snip)

    def set_source_language(self, val, btn):
        if hasattr(self, 'current_src_btn'):
            self.current_src_btn.setChecked(False)
        self.current_src_btn = btn
        btn.setChecked(True)
        self.source_lang_option = val
        print(f"Source language option updated: {val}")
        # Restart Flask server with new source language option
        self.restart_flask_server()

    def set_dest_language(self, lang, btn):
        if hasattr(self, 'current_dest_btn'):
            self.current_dest_btn.setChecked(False)
        self.current_dest_btn = btn
        btn.setChecked(True)
        self.dest_lang = lang
        print(f"Destination language updated: {lang}")

    def pick_color(self):
        col = QtWidgets.QColorDialog.getColor()
        if col.isValid():
            self.fill_color = col.name()
            self.color_btn.setText(f"Pick Color ({self.fill_color})")

    def update_opacity(self, val):
        self.opacity = val / 100.0

    def update_linewidth(self, val):
        self.line_width = val

    def update_alpha(self, val):
        self.alpha = val / 100.0

    def update_fontsize(self, val):
        self.font_size = val

    def start_flask_server(self):
        python_executable = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
        if not python_executable.exists():
            python_executable = sys.executable
        server_script = Path(__file__).parent / "python" / "eocr_server.py"
        
        cmd = [str(python_executable), str(server_script), str(self.source_lang_option)]
        print(f"Starting Flask server: {' '.join(cmd)}")
        try:
            self.flask_process = subprocess.Popen(cmd)
        except Exception as e:
            print(f"Failed to start Flask server: {e}")

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
        snip_script = Path(__file__).parent / "python" / "snip0.py"

        # Arguments: destination, fill_color_hex, opacity, line_width, alpha, font_size
        cmd = [
            str(python_executable),
            str(snip_script),
            str(self.dest_lang),
            str(self.fill_color),
            str(self.opacity),
            str(self.line_width),
            str(self.alpha),
            str(self.font_size)
        ]
        print(f"Launching snip script: {' '.join(cmd)}")
        try:
            self.snip_process = subprocess.Popen(cmd, cwd=str(snip_script.parent))
        except Exception as e:
            print(f"Failed to launch snip script: {e}")

    def init_global_hotkey(self):
        # Register global hotkey Alt+Shift+M using Windows API via ctypes
        if sys.platform == 'win32':
            try:
                # MOD_ALT = 0x0001, MOD_SHIFT = 0x0004
                # VK_M = 0x4D
                ctypes.windll.user32.RegisterHotKey(None, 1, 0x0001 | 0x0004, 0x4D)
                self.nativeEventFilter = HotkeyFilter(self.trigger_snip)
                QtWidgets.QApplication.instance().installNativeEventFilter(self.nativeEventFilter)
                print("Global hotkey Alt+Shift+M registered successfully.")
            except Exception as e:
                print(f"Failed to register global hotkey: {e}")

    def closeEvent(self, event):
        if self.flask_process:
            self.flask_process.terminate()
        if sys.platform == 'win32':
            try:
                ctypes.windll.user32.UnregisterHotKey(None, 1)
            except:
                pass
        event.accept()

if sys.platform == 'win32':
    class HotkeyFilter(QtCore.QAbstractNativeEventFilter):
        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        def nativeEventFilter(self, eventType, message):
            if eventType == b"windows_generic_MSG" or eventType == "windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(message.__int__())
                if msg.message == 0x0312:  # WM_HOTKEY
                    if msg.wParam == 1:
                        self.callback()
                        return True, 0
            return False, 0

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = LingoLensApp()
    window.show()
    sys.exit(app.exec_())
