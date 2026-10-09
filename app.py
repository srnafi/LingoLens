"""LingoLens Control Center — frameless single-screen UI (Linear-minimal).

Layout (action only, no marketing copy):
    [icon LingoLens]  [OCR status pill] [settings] [–] [×]   <- custom titlebar
    [      Snip & Translate  ·  Alt+Shift+M      ]           <- hero CTA
    [ FROM ▾ ] [swap] [ TO ▾ ]                               <- language pair
    [ RECENT: chips ]                                        <- hidden when empty

All appearance knobs (capture fill/opacity/border, text color/alpha/size)
live in the Settings dialog (gear button). Backend contracts unchanged:
Flask OCR server on :5000, capture.py argv order, Alt+Shift+M hotkey.
"""
import sys
import json
import subprocess
import ctypes
import ctypes.wintypes
from pathlib import Path

# Set DPI awareness BEFORE any Qt import. Without this, Windows bitmap-scales
# the whole window on scaled displays and all text renders blurry.
# (Mirrors python/capture.py.)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PyQt5 import QtWidgets, QtCore, QtGui

SETTINGS_FILE = Path(__file__).parent / "settings.json"

# Source languages. Option int selects the EasyOCR model bundle
# (must stay in sync with python/ocr_server.py LANGUAGE_MAP).
FROM_LANGS = [
    ("English", 1), ("Spanish", 1), ("French", 1), ("Italian", 1),
    ("Portuguese", 1), ("Vietnamese", 1), ("German", 1),
    ("Chinese", 2), ("Japanese", 3), ("Russian", 4),
    ("Bengali", 5), ("Korean", 6),
]
FROM_SHORT = ["EN", "ES", "FR", "IT", "PT", "VI", "DE",
              "ZH", "JA", "RU", "BN", "KO"]

TO_LANGS = [
    ("English", "en"), ("Spanish", "es"), ("French", "fr"), ("German", "de"),
    ("Italian", "it"), ("Portuguese", "pt"), ("Russian", "ru"),
    ("Vietnamese", "vi"), ("Bengali", "bn"), ("Hindi", "hi"),
    ("Chinese (Simplified)", "zh-CN"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Arabic", "ar"), ("Urdu", "ur"), ("Dutch", "nl"), ("Turkish", "tr"),
    ("Polish", "pl"), ("Indonesian", "id"), ("Thai", "th"),
]

MAX_RECENTS = 3


def _base_name(name):
    """'Chinese (Simplified)' -> 'chinese'. Used for From/To swap matching."""
    return name.split("(")[0].strip().lower()


def _is_swappable(from_name, to_name):
    """A pair can flip only if both sides exist in both lists (OCR model needed)."""
    from_bases = {_base_name(n) for n, _ in FROM_LANGS}
    to_bases = {_base_name(n) for n, _ in TO_LANGS}
    return (_base_name(from_name) in to_bases
            and _base_name(to_name) in from_bases)


def _paint_icon(kind, size=18, color="#e8eaf2"):
    """Paint a small icon with QPainter — no font/emoji dependency.

    Emoji/symbol glyphs (bolt, gear) do not exist in Segoe UI and render as
    blank buttons on systems without a color-emoji font fallback for Qt.
    Painted paths always render.
    """
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    c = QtGui.QColor(color)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(c)
    cx = size / 2.0
    if kind == "gear":
        # 8 teeth + ring body + clear punched hole.
        for i in range(8):
            p.save()
            p.translate(cx, cx)
            p.rotate(i * 45.0)
            tooth_w = size * 0.16
            tooth_h = size * 0.20
            p.drawRect(QtCore.QRectF(-tooth_w / 2.0,
                                     -size * 0.46,
                                     tooth_w, tooth_h))
            p.restore()
        p.drawEllipse(QtCore.QRectF(cx - size * 0.30, cx - size * 0.30,
                                    size * 0.60, size * 0.60))
        p.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
        p.drawEllipse(QtCore.QRectF(cx - size * 0.13, cx - size * 0.13,
                                    size * 0.26, size * 0.26))
    elif kind == "bolt":
        s = size / 18.0
        p.drawPolygon(QtGui.QPolygonF([
            QtCore.QPointF(10.5 * s, 1.5 * s),
            QtCore.QPointF(5.5 * s, 10.0 * s),
            QtCore.QPointF(8.6 * s, 10.0 * s),
            QtCore.QPointF(7.2 * s, 16.5 * s),
            QtCore.QPointF(12.6 * s, 6.8 * s),
            QtCore.QPointF(9.5 * s, 6.8 * s),
        ]))
    p.end()
    return QtGui.QIcon(pm)


# Linear-minimal dark theme. Flat fills + one linear gradient (QSS supports
# qlineargradient; it does NOT support blur/glow, so depth comes from the
# drop-shadow effect applied in code).
LINEAR_QSS = """
QWidget {
    background-color: transparent;
    color: #f4f4f8;
    font-family: 'Segoe UI', Inter, Arial, sans-serif;
    font-size: 10pt;
}
QWidget#card {
    background-color: #0d0f14;
    border: 1px solid #2a2d36;
    border-radius: 14px;
}
QLabel#appTitle {
    font-size: 12pt;
    font-weight: 800;
}
QLabel#captionLabel {
    color: #6c7086;
    font-size: 8.5pt;
    font-weight: 700;
}
QPushButton {
    background-color: #14161d;
    color: #e8eaf2;
    border: 1px solid #2a2d36;
    border-radius: 8px;
    padding: 8px 12px;
}
QPushButton:hover {
    background-color: #1a1d26;
    border-color: #5e6ad2;
}
QPushButton:pressed {
    background-color: #101218;
}
QPushButton:disabled {
    color: #565b70;
    border-color: #1c1e24;
    background-color: #101218;
}
QPushButton:focus {
    outline: none;
    border-color: #5e6ad2;
}
QPushButton#ctaButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #707aea, stop:0.5 #5e6ad2, stop:1 #4953ad);
    color: #ffffff;
    font-size: 12pt;
    font-weight: 700;
    border: 1px solid #828cea;
    border-radius: 12px;
    padding: 13px;
}
QPushButton#ctaButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7d87f2, stop:0.5 #6a74de, stop:1 #515bb8);
    border-color: #929bf2;
}
QPushButton#ctaButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #5a64d6, stop:1 #3f4796);
}
QPushButton#statusButton {
    font-size: 9pt;
    font-weight: 700;
}
QPushButton#chipButton {
    border-radius: 12px;
    padding: 5px 13px;
    font-size: 9pt;
    font-weight: 600;
    color: #a5a9bd;
}
QPushButton#chipButton:hover {
    color: #ffffff;
}
QPushButton#toolButton {
    font-size: 13pt;
    padding: 4px 10px;
    min-width: 42px;
}
QPushButton#winButton {
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #8b8fa3;
    font-size: 11pt;
    min-width: 34px;
    padding: 4px 6px;
}
QPushButton#winButton:hover {
    background-color: #1c1f27;
    color: #ffffff;
    border: none;
}
QPushButton#closeButton {
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #8b8fa3;
    font-size: 11pt;
    min-width: 34px;
    padding: 4px 6px;
}
QPushButton#closeButton:hover {
    background-color: #e81123;
    color: #ffffff;
    border: none;
}
QComboBox {
    background-color: #14161d;
    border: 1px solid #2a2d36;
    border-radius: 8px;
    padding: 9px 12px;
    color: #e8eaf2;
}
QComboBox:hover {
    border-color: #5e6ad2;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox QAbstractItemView {
    background-color: #14161d;
    border: 1px solid #2a2d36;
    selection-background-color: #5e6ad2;
    selection-color: #ffffff;
    outline: none;
}
QDialog {
    background-color: #0d0f14;
}
QGroupBox {
    border: 1px solid #2a2d36;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 16px;
    padding-left: 12px;
    padding-right: 12px;
    padding-bottom: 12px;
    font-weight: 700;
    color: #8b8fa3;
    font-size: 9pt;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: #2a2d36;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #5e6ad2;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #6c78dd;
}
QFrame#swatch {
    border: 1px solid #2a2d36;
    border-radius: 5px;
}
"""

STATUS_STYLE = {
    # state: (text, accent color)
    "ready": ("OCR ready", "#4ade80"),
    "starting": ("OCR starting", "#f9e2af"),
    "offline": ("OCR offline — retry", "#f38ba8"),
}


class LingoLensControlCenter(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # Frameless + translucent: rounded outer corners and a dark custom
        # titlebar. (Native Win32 chrome is square and light — the old look.)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("LingoLens")
        self._drag_pos = None

        # State & appearance defaults
        self.source_lang_option = 1
        self.source_lang_name = "English"
        self.dest_lang = "en"
        self.dest_lang_name = "English"
        self.fill_color = "#ff0000"
        self.text_color = "#000000"
        self.opacity = 0.3
        self.line_width = 3
        self.alpha = 0.7
        self.font_size = 12
        self.recent_pairs = []

        self.flask_process = None
        self.snip_process = None
        self.nativeEventFilter = None

        self.init_ui()
        # Window hugs its content — no dead space, no manual resize().
        self.layout().setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.load_settings()
        self.start_flask_server()
        self.init_global_hotkey()

    # ---------- settings persistence ----------
    def save_settings(self):
        """Persist user preferences to disk."""
        settings = {
            "source_lang_option": self.source_lang_option,
            "source_lang_name": self.source_lang_name,
            "dest_lang": self.dest_lang,
            "dest_lang_name": self.dest_lang_name,
            "fill_color": self.fill_color,
            "text_color": self.text_color,
            "opacity": self.opacity,
            "line_width": self.line_width,
            "alpha": self.alpha,
            "font_size": self.font_size,
            "recent_pairs": self.recent_pairs,
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
            self.source_lang_name = settings.get("source_lang_name", "English")
            self.dest_lang = settings.get("dest_lang", "en")
            self.dest_lang_name = settings.get("dest_lang_name", "English")
            self.fill_color = settings.get("fill_color", "#ff0000")
            self.text_color = settings.get("text_color", "#000000")
            self.opacity = settings.get("opacity", 0.3)
            self.line_width = settings.get("line_width", 3)
            self.alpha = settings.get("alpha", 0.7)
            self.font_size = settings.get("font_size", 12)
            self.recent_pairs = self._sanitize_recents(
                settings.get("recent_pairs", []))

            # Reflect loaded values in the combos without firing handlers.
            from_idx = self._find_from_index(
                self.source_lang_name, self.source_lang_option)
            to_idx = self._find_to_index(self.dest_lang)
            self.from_combo.blockSignals(True)
            self.from_combo.setCurrentIndex(from_idx)
            self.from_combo.blockSignals(False)
            self.to_combo.blockSignals(True)
            self.to_combo.setCurrentIndex(to_idx)
            self.to_combo.blockSignals(False)
            self.source_lang_name = FROM_LANGS[from_idx][0]
            self.source_lang_option = FROM_LANGS[from_idx][1]
            self.dest_lang = TO_LANGS[to_idx][1]
            self.dest_lang_name = TO_LANGS[to_idx][0]
            self._update_swap_state()
            self._refresh_recent_chips()
            print(f"Settings loaded from {SETTINGS_FILE}")
        except Exception as e:
            print(f"Failed to load settings: {e}")

    def reset_defaults(self):
        """Reset all settings to factory defaults."""
        self.source_lang_option = 1
        self.source_lang_name = "English"
        self.dest_lang = "en"
        self.dest_lang_name = "English"
        self.fill_color = "#ff0000"
        self.text_color = "#000000"
        self.opacity = 0.3
        self.line_width = 3
        self.alpha = 0.7
        self.font_size = 12
        self.from_combo.blockSignals(True)
        self.from_combo.setCurrentIndex(0)
        self.from_combo.blockSignals(False)
        self.to_combo.blockSignals(True)
        self.to_combo.setCurrentIndex(0)
        self.to_combo.blockSignals(False)
        self._update_swap_state()
        self.save_settings()
        self.restart_flask_server()
        print("Settings reset to defaults")

    # ---------- main UI: action only ----------
    def init_ui(self):
        # Outer transparent layer: room for the card's drop shadow.
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        card = QtWidgets.QWidget()
        card.setObjectName("card")
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QtGui.QColor(0, 0, 0, 180))
        card.setGraphicsEffect(shadow)
        root.addWidget(card)

        body = QtWidgets.QVBoxLayout(card)
        body.setContentsMargins(20, 14, 20, 18)
        body.setSpacing(13)

        # ---- custom dark titlebar: icon + wordmark ... status, gear, min, close
        bar_wrap = QtWidgets.QWidget()
        bar = QtWidgets.QHBoxLayout(bar_wrap)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)

        self.title_icon_lbl = QtWidgets.QLabel()
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            pm = QtGui.QPixmap(str(icon_path)).scaled(
                20, 20, QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation)
            self.title_icon_lbl.setPixmap(pm)
        bar.addWidget(self.title_icon_lbl)

        app_title = QtWidgets.QLabel(
            '<span style="color:#f4f4f8">Lingo</span>'
            '<span style="color:#7c86e6">Lens</span>')
        app_title.setObjectName("appTitle")
        app_title.setTextFormat(QtCore.Qt.RichText)
        bar.addWidget(app_title)
        bar.addStretch()

        self.status_button = QtWidgets.QPushButton()
        self.status_button.setObjectName("statusButton")
        self.status_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.status_button.setToolTip(
            "OCR engine status — click to re-check / restart")
        self.status_button.clicked.connect(self._on_status_clicked)
        self.status_button.setMaximumWidth(230)  # pill hugs its text
        self._set_status("starting")
        bar.addWidget(self.status_button)

        gear_btn = QtWidgets.QPushButton()
        gear_btn.setObjectName("winButton")
        gear_btn.setIcon(_paint_icon("gear", 18))
        gear_btn.setIconSize(QtCore.QSize(18, 18))
        gear_btn.setCursor(QtCore.Qt.PointingHandCursor)
        gear_btn.setToolTip("Overlay & capture settings")
        gear_btn.clicked.connect(self.open_settings)
        bar.addWidget(gear_btn)

        min_btn = QtWidgets.QPushButton("\u2013")
        min_btn.setObjectName("winButton")
        min_btn.setCursor(QtCore.Qt.PointingHandCursor)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)
        bar.addWidget(min_btn)

        close_btn = QtWidgets.QPushButton("\u00d7")
        close_btn.setObjectName("closeButton")
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setToolTip("Quit LingoLens")
        close_btn.clicked.connect(self.close)
        bar.addWidget(close_btn)

        # Drag the frameless window by the titlebar background.
        bar_wrap.mousePressEvent = lambda e: self._title_press(e)
        bar_wrap.mouseMoveEvent = lambda e: self._title_move(e)
        bar_wrap.mouseReleaseEvent = lambda e: self._title_release(e)
        body.addWidget(bar_wrap)

        # ---- hero action (note: && renders a literal &)
        self.snip_button = QtWidgets.QPushButton(
            "Snip && Translate    \u00b7    Alt+Shift+M")
        self.snip_button.setObjectName("ctaButton")
        self.snip_button.setIcon(_paint_icon("bolt", 22, "#ffffff"))
        self.snip_button.setIconSize(QtCore.QSize(22, 22))
        self.snip_button.setMinimumHeight(60)
        self.snip_button.setCursor(QtCore.Qt.PointingHandCursor)
        # Stretch to fill, but never dictate the window width.
        self.snip_button.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.snip_button.setToolTip(
            "Capture a screen region and translate it in place (Alt+Shift+M)")
        self.snip_button.clicked.connect(self.trigger_snip)
        body.addWidget(self.snip_button)

        # ---- language row: From, swap, To
        lang_row = QtWidgets.QHBoxLayout()
        lang_row.setSpacing(8)

        from_col = QtWidgets.QVBoxLayout()
        from_col.setSpacing(5)
        from_cap = QtWidgets.QLabel("FROM")
        from_cap.setObjectName("captionLabel")
        from_col.addWidget(from_cap)
        self.from_combo = QtWidgets.QComboBox()
        for name, _opt in FROM_LANGS:
            self.from_combo.addItem(name)
        # Hug content: never stretch to the longest item name.
        self.from_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.from_combo.setMinimumContentsLength(9)
        self.from_combo.setMinimumWidth(150)
        self.from_combo.currentIndexChanged.connect(self._on_from_changed)
        from_col.addWidget(self.from_combo)
        lang_row.addLayout(from_col, 1)

        # Swap glyph only (text ⇄ renders in Segoe UI; emoji don't).
        self.swap_button = QtWidgets.QPushButton("\u21c4")
        self.swap_button.setObjectName("toolButton")
        self.swap_button.setFixedSize(40, 40)
        self.swap_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.swap_button.setToolTip("Swap languages")
        self.swap_button.clicked.connect(self._swap_languages)
        lang_row.addWidget(self.swap_button, 0, QtCore.Qt.AlignBottom)

        to_col = QtWidgets.QVBoxLayout()
        to_col.setSpacing(5)
        to_cap = QtWidgets.QLabel("TO")
        to_cap.setObjectName("captionLabel")
        to_col.addWidget(to_cap)
        self.to_combo = QtWidgets.QComboBox()
        for name, _code in TO_LANGS:
            self.to_combo.addItem(name)
        # Hug content: never stretch to the longest item name.
        self.to_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.to_combo.setMinimumContentsLength(9)
        self.to_combo.setMinimumWidth(150)
        self.to_combo.currentIndexChanged.connect(self._on_to_changed)
        to_col.addWidget(self.to_combo)
        lang_row.addLayout(to_col, 1)
        body.addLayout(lang_row)

        # ---- recent pairs (chips are actions: click to re-apply)
        self.recents_row = QtWidgets.QHBoxLayout()
        self.recents_row.setSpacing(7)
        self.recents_caption = QtWidgets.QLabel("RECENT")
        self.recents_caption.setObjectName("captionLabel")
        self.recents_row.addWidget(self.recents_caption)
        self.recents_chips = QtWidgets.QHBoxLayout()
        self.recents_chips.setSpacing(7)
        self.recents_row.addLayout(self.recents_chips)
        self.recents_row.addStretch()
        self.recents_wrap = QtWidgets.QWidget()
        self.recents_wrap.setLayout(self.recents_row)
        body.addWidget(self.recents_wrap)

    # ---------- frameless drag ----------
    def _title_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = (event.globalPos()
                              - self.frameGeometry().topLeft())
            event.accept()

    def _title_move(self, event):
        if (event.buttons() & QtCore.Qt.LeftButton
                and self._drag_pos is not None):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def _title_release(self, event):
        self._drag_pos = None
        event.accept()

    # ---------- language logic ----------
    @staticmethod
    def _find_from_index(name, option):
        for i, (n, opt) in enumerate(FROM_LANGS):
            if n == name:
                return i
        for i, (n, opt) in enumerate(FROM_LANGS):
            if opt == option:
                return i
        return 0

    @staticmethod
    def _find_to_index(code):
        for i, (n, c) in enumerate(TO_LANGS):
            if c == code:
                return i
        return 0

    @staticmethod
    def _sanitize_recents(raw):
        valid_from = {n for n, _ in FROM_LANGS}
        valid_to = {c for _, c in TO_LANGS}
        clean = []
        for entry in raw if isinstance(raw, list) else []:
            if (isinstance(entry, dict)
                    and entry.get("from") in valid_from
                    and entry.get("to") in valid_to):
                clean.append({"from": entry["from"], "to": entry["to"]})
        return clean[:MAX_RECENTS]

    def _on_from_changed(self, idx):
        name, opt = FROM_LANGS[idx]
        option_changed = (opt != self.source_lang_option)
        self.source_lang_name = name
        self.source_lang_option = opt
        self.save_settings()
        # Languages sharing one model bundle need no server restart.
        if option_changed:
            self.restart_flask_server()
        else:
            print(f"Source language updated: {name} (same OCR model, no restart)")
        self._update_swap_state()

    def _on_to_changed(self, idx):
        name, code = TO_LANGS[idx]
        self.dest_lang_name = name
        self.dest_lang = code
        print(f"Destination language updated: {name}")
        self.save_settings()
        self._update_swap_state()

    def _update_swap_state(self):
        ok = _is_swappable(self.source_lang_name, self.dest_lang_name)
        self.swap_button.setEnabled(ok)
        if ok:
            self.swap_button.setToolTip("Swap languages")
        else:
            self.swap_button.setToolTip(
                f"No OCR model for '{self.dest_lang_name}' — can't swap")

    def _swap_languages(self):
        from_name = self.source_lang_name
        to_name = TO_LANGS[self.to_combo.currentIndex()][0]
        if not _is_swappable(from_name, to_name):
            return
        new_from = 0
        for i, (n, _o) in enumerate(FROM_LANGS):
            if _base_name(n) == _base_name(to_name):
                new_from = i
                break
        new_to = self._find_to_index(
            next(c for n, c in TO_LANGS
                 if _base_name(n) == _base_name(from_name)))
        self.from_combo.setCurrentIndex(new_from)  # fires handler
        self.to_combo.setCurrentIndex(new_to)      # fires handler

    # ---------- recents ----------
    def _push_recent(self):
        entry = {"from": self.source_lang_name, "to": self.dest_lang}
        self.recent_pairs = [e for e in self.recent_pairs if e != entry]
        self.recent_pairs.insert(0, entry)
        self.recent_pairs = self.recent_pairs[:MAX_RECENTS]
        self.save_settings()
        self._refresh_recent_chips()

    def _refresh_recent_chips(self):
        while self.recents_chips.count():
            item = self.recents_chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for entry in self.recent_pairs:
            from_short = FROM_SHORT[self._find_from_index(entry["from"], 1)]
            to_short = entry["to"].split("-")[0].upper()
            chip = QtWidgets.QPushButton(f"{from_short} \u2192 {to_short}")
            chip.setObjectName("chipButton")
            chip.setCursor(QtCore.Qt.PointingHandCursor)
            chip.setToolTip(f"{entry['from']} → "
                            f"{self._to_display_name(entry['to'])}")
            chip.clicked.connect(
                lambda _c, e=dict(entry): self._apply_recent(e))
            self.recents_chips.addWidget(chip)
        has = bool(self.recent_pairs)
        self.recents_wrap.setVisible(has)

    @staticmethod
    def _to_display_name(code):
        for n, c in TO_LANGS:
            if c == code:
                return n
        return code

    def _apply_recent(self, entry):
        self.from_combo.setCurrentIndex(
            self._find_from_index(entry["from"], self.source_lang_option))
        self.to_combo.setCurrentIndex(self._find_to_index(entry["to"]))

    # ---------- OCR status pill (live Flask /health) ----------
    def _set_status(self, state):
        text, accent = STATUS_STYLE[state]
        dot = "\u25cc" if state == "starting" else "\u25cf"
        self.status_button.setText(f"{dot}  {text}")
        self.status_button.setStyleSheet(
            f"QPushButton#statusButton {{"
            f" background-color: #14161d;"
            f" color: {accent};"
            f" border: 1px solid {accent};"
            f" border-radius: 13px;"
            f" padding: 6px 14px;"
            f"}}")

    def _on_status_clicked(self):
        """Manual re-check; restart the server if it is down."""
        import requests as _requests
        try:
            resp = _requests.get("http://localhost:5000/health", timeout=2)
            if resp.status_code == 200:
                self._set_status("ready")
                return
            self._set_status("starting")
        except Exception:
            self._set_status("offline")
            print("Status check failed — restarting Flask server...")
            self.restart_flask_server()

    def _poll_flask_health(self):
        """Poll Flask /health endpoint and reflect it on the status pill."""
        import requests as _requests

        def check():
            try:
                resp = _requests.get("http://localhost:5000/health", timeout=2)
                if resp.status_code == 200:
                    self._set_status("ready")
                else:
                    self._set_status("starting")
                    QtCore.QTimer.singleShot(2000, check)
            except Exception:
                self._set_status("offline")
                QtCore.QTimer.singleShot(3000, check)
        QtCore.QTimer.singleShot(2000, check)

    # ---------- settings dialog (all appearance knobs live here) ----------
    def open_settings(self):
        self._build_settings_dialog().exec_()

    def _build_settings_dialog(self):
        """Build the Settings dialog (split out so tests can inspect it)."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setMinimumWidth(400)
        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setSpacing(6)

        # Capture box group.
        cap_group = QtWidgets.QGroupBox("Capture box")
        cap_layout = QtWidgets.QVBoxLayout()
        fill_row = QtWidgets.QHBoxLayout()
        fill_row.addWidget(QtWidgets.QLabel("Selection fill:"))
        self._dlg_fill_swatch = QtWidgets.QFrame()
        self._dlg_fill_swatch.setObjectName("swatch")
        self._dlg_fill_swatch.setFixedSize(30, 20)
        fill_row.addWidget(self._dlg_fill_swatch)
        fill_btn = QtWidgets.QPushButton("Choose…")
        fill_btn.clicked.connect(lambda: self._pick_color_in_dlg(
            "fill", self._dlg_fill_swatch))
        fill_row.addStretch()
        fill_row.addWidget(fill_btn)
        cap_layout.addLayout(fill_row)
        self._dlg_opacity_lbl = QtWidgets.QLabel()
        cap_layout.addWidget(self._dlg_opacity_lbl)
        self._dlg_opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._dlg_opacity.setRange(0, 100)
        self._dlg_opacity.valueChanged.connect(self._dlg_update_opacity)
        cap_layout.addWidget(self._dlg_opacity)
        self._dlg_width_lbl = QtWidgets.QLabel()
        cap_layout.addWidget(self._dlg_width_lbl)
        self._dlg_width = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._dlg_width.setRange(1, 10)
        self._dlg_width.valueChanged.connect(self._dlg_update_width)
        cap_layout.addWidget(self._dlg_width)
        cap_group.setLayout(cap_layout)
        layout.addWidget(cap_group)

        # Overlay text group.
        txt_group = QtWidgets.QGroupBox("Overlay text")
        txt_layout = QtWidgets.QVBoxLayout()
        tc_row = QtWidgets.QHBoxLayout()
        tc_row.addWidget(QtWidgets.QLabel("Text color:"))
        self._dlg_text_swatch = QtWidgets.QFrame()
        self._dlg_text_swatch.setObjectName("swatch")
        self._dlg_text_swatch.setFixedSize(30, 20)
        tc_row.addWidget(self._dlg_text_swatch)
        tc_btn = QtWidgets.QPushButton("Choose…")
        tc_btn.clicked.connect(lambda: self._pick_color_in_dlg(
            "text", self._dlg_text_swatch))
        tc_row.addStretch()
        tc_row.addWidget(tc_btn)
        txt_layout.addLayout(tc_row)
        self._dlg_alpha_lbl = QtWidgets.QLabel()
        txt_layout.addWidget(self._dlg_alpha_lbl)
        self._dlg_alpha = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._dlg_alpha.setRange(0, 100)
        self._dlg_alpha.valueChanged.connect(self._dlg_update_alpha)
        txt_layout.addWidget(self._dlg_alpha)
        self._dlg_font_lbl = QtWidgets.QLabel()
        txt_layout.addWidget(self._dlg_font_lbl)
        self._dlg_font = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._dlg_font.setRange(5, 25)
        self._dlg_font.valueChanged.connect(self._dlg_update_font)
        txt_layout.addWidget(self._dlg_font)
        txt_group.setLayout(txt_layout)
        layout.addWidget(txt_group)

        self._refresh_settings_dlg()
        # Set slider positions without firing save-churn.
        for slider, val in ((self._dlg_opacity, int(self.opacity * 100)),
                            (self._dlg_width, self.line_width),
                            (self._dlg_alpha, int(self.alpha * 100)),
                            (self._dlg_font, self.font_size)):
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)
        self._update_dlg_labels()

        btn_row = QtWidgets.QHBoxLayout()
        reset_btn = QtWidgets.QPushButton("Reset defaults")
        reset_btn.setStyleSheet("color: #f38ba8;")
        reset_btn.clicked.connect(lambda: self._reset_from_dlg(dlg))
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        close_btn = QtWidgets.QPushButton("Done")
        close_btn.setDefault(True)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        return dlg

    def _refresh_settings_dlg(self):
        self._dlg_fill_swatch.setStyleSheet(
            f"QFrame#swatch {{ background-color: {self.fill_color}; }}")
        self._dlg_text_swatch.setStyleSheet(
            f"QFrame#swatch {{ background-color: {self.text_color}; }}")

    def _update_dlg_labels(self):
        self._dlg_opacity_lbl.setText(
            f"Selection opacity: {int(self.opacity * 100)}%")
        self._dlg_width_lbl.setText(
            f"Border width: {self.line_width}px")
        self._dlg_alpha_lbl.setText(
            f"Overlay background: {int(self.alpha * 100)}%")
        self._dlg_font_lbl.setText(f"Font size: {self.font_size}pt")

    def _pick_color_in_dlg(self, which, swatch):
        col = QtWidgets.QColorDialog.getColor()
        if col.isValid():
            if which == "fill":
                self.fill_color = col.name()
            else:
                self.text_color = col.name()
            swatch.setStyleSheet(
                f"QFrame#swatch {{ background-color: {col.name()}; }}")
            self.save_settings()

    def _dlg_update_opacity(self, val):
        self.opacity = val / 100.0
        self._dlg_opacity_lbl.setText(f"Selection opacity: {val}%")
        self.save_settings()

    def _dlg_update_width(self, val):
        self.line_width = val
        self._dlg_width_lbl.setText(f"Border width: {val}px")
        self.save_settings()

    def _dlg_update_alpha(self, val):
        self.alpha = val / 100.0
        self._dlg_alpha_lbl.setText(f"Overlay background: {val}%")
        self.save_settings()

    def _dlg_update_font(self, val):
        self.font_size = val
        self._dlg_font_lbl.setText(f"Font size: {val}pt")
        self.save_settings()

    def _reset_from_dlg(self, dlg):
        self.reset_defaults()
        self._refresh_settings_dlg()
        for slider, val in ((self._dlg_opacity, int(self.opacity * 100)),
                            (self._dlg_width, self.line_width),
                            (self._dlg_alpha, int(self.alpha * 100)),
                            (self._dlg_font, self.font_size)):
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)
        self._update_dlg_labels()
        print("Settings reset to defaults (from dialog)")

    # ---------- backend processes ----------
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
            self._set_status("offline")

    def restart_flask_server(self):
        if self.flask_process:
            print("Terminating old Flask server...")
            self.flask_process.terminate()
            try:
                self.flask_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.flask_process.kill()
        self._set_status("starting")
        self.start_flask_server()

    def trigger_snip(self):
        self._push_recent()
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
    # Crisp text on scaled displays (pairs with the per-monitor DPI awareness
    # set at the top of this file, before the Qt import).
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    _icon_path = Path(__file__).parent / "icon.png"
    if _icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(_icon_path)))
    app.setStyleSheet(LINEAR_QSS)
    window = LingoLensControlCenter()
    window.show()
    sys.exit(app.exec_())
