"""
ui_kit.py - drop-in design system for PyQt5 desktop apps (dark theme).

Copy this file next to your app. Then:

    from ui_kit import apply_theme, FramelessWindow, FramelessDialog, Section, \
        SliderRow, ColorButton, Toggle, Button, IconButton, icon, snapshot

    app = QApplication(sys.argv)
    apply_theme(app)            # Fusion style + global stylesheet

Everything here is anti-aliased, token-driven and consistent. Change the look
by editing TOKENS only. Do not scatter hex colours through your app code.
"""
import os
import tempfile
from string import Template

from PyQt5.QtCore import (Qt, QByteArray, QEasingCurve, QPointF, QPropertyAnimation,
                          QRectF, QSize, pyqtProperty, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QIcon, QLinearGradient,
                         QPainter, QPen, QPixmap)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (QApplication, QColorDialog, QComboBox, QDialog,
                             QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                             QLabel, QPushButton, QSlider, QCheckBox,
                             QVBoxLayout, QWidget)

# --------------------------------------------------------------------------
# 1. DESIGN TOKENS - the single source of truth
# --------------------------------------------------------------------------
TOKENS = dict(
    # surfaces (dark -> light = further back -> closer to the user)
    bg_top="#1a1d29", bg="#121420",
    surface="#181b28", surface_2="#20243a", surface_3="#2a2f4a",
    border="rgba(255,255,255,0.08)", border_strong="rgba(255,255,255,0.16)",
    # text
    text="#eceef8", text_dim="#9aa1bd", text_faint="#646b88",
    # brand / semantic
    accent="#4aa8ff", accent_2="#6a7bff", accent_soft="rgba(74,168,255,0.18)",
    danger="#ff6b81", success="#3ddc97", warning="#ffb454", teal="#2dd4bf",
    # shape
    radius_lg=18, radius_md=14, radius_sm=10,
    # type
    font='"Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", Arial',
)

# --------------------------------------------------------------------------
# 2. ICONS - tiny inline SVG set (Lucide-style, 24x24 grid, stroked)
#    Never use unicode glyphs or emoji as icons; they render differently
#    on every machine. Add more from https://lucide.dev (copy the <path> d).
# --------------------------------------------------------------------------
_ICONS = {
    "close": "M18 6 6 18M6 6l12 12",
    "minimize": "M5 12h14",
    "maximize": "M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7",
    "check": "M20 6 9 17l-5-5",
    "chevron-down": "m6 9 6 6 6-6",
    "refresh": "M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8M21 3v5h-5",
    "swap": "M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4",
    "collapse": "M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7",
    "copy": ("M10 8h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z"
             "M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"),
    "settings": ("M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08"
                 "a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74"
                 "l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25"
                 "a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25"
                 "a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08"
                 "a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38"
                 "a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
                 "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"),
    "sliders": "M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4",
    "camera": ("M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9"
               "a2 2 0 0 0-2-2h-3l-2.5-3zM12 10a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"),
}


def _svg(name, color, stroke=2.0):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="{_ICONS[name]}"/></svg>')


def icon(name, color=None, size=16):
    """Crisp (2x) QIcon from the inline set."""
    color = color or TOKENS["text_dim"]
    r = QSvgRenderer(QByteArray(_svg(name, color).encode()))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def icon_file(name, color=None):
    """Write the icon to a temp .svg and return a path usable in QSS url()."""
    color = color or TOKENS["text_dim"]
    path = os.path.join(tempfile.gettempdir(), f"uikit_{name}_{color.strip('#')}.svg")
    with open(path, "w") as f:
        f.write(_svg(name, color))
    return path.replace("\\", "/")


# --------------------------------------------------------------------------
# 3. GLOBAL STYLESHEET - every stock widget you might use is styled here.
#    Qt widgets that are NOT styled fall back to ugly OS defaults.
#    QSS does NOT support: box-shadow, transition, gap, flex/grid,
#    text-transform. Use QGraphicsDropShadowEffect / QPropertyAnimation /
#    layout spacing / QFont.setLetterSpacing instead.
# --------------------------------------------------------------------------
_QSS = Template(r"""
* { font-family: $font; font-size: 13px; color: $text; outline: 0; }

/* stock dialogs we don't control (QColorDialog etc.) */
QColorDialog, QMessageBox, QInputDialog, QFileDialog { background: $bg; }

/* ---- frameless window / dialog shell ---- */
#Window {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $bg_top, stop:1 $bg);
    border: 1px solid $border;
    border-radius: ${radius_lg}px;
}
#TitleLabel   { font-size: 14px; font-weight: 600; }
#Dim          { color: $text_dim; }
#Value        { color: $text; font-weight: 600; }
#SectionTitle { color: $text_dim; font-size: 11px; font-weight: 700; }

/* ---- cards ---- */
#Section {
    background: $surface;
    border: 1px solid $border;
    border-radius: ${radius_md}px;
}

/* ---- buttons: variants via dynamic property ---- */
QPushButton {
    background: $surface_2; border: 1px solid $border;
    border-radius: ${radius_sm}px; padding: 8px 16px; font-weight: 600;
}
QPushButton:hover    { background: $surface_3; border-color: $border_strong; }
QPushButton:pressed  { background: $surface; }
QPushButton:disabled { color: $text_faint; background: $surface; }

QPushButton[variant="primary"] {
    border: none; color: white;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_2);
}
QPushButton[variant="primary"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #66b8ff, stop:1 #8290ff);
}
QPushButton[variant="primary"]:pressed { padding-top: 9px; padding-bottom: 7px; }

QPushButton[variant="ghost"] {
    background: transparent; border: 1px solid transparent; color: $text_dim;
}
QPushButton[variant="ghost"]:hover { background: rgba(255,255,255,0.06); color: $text; }

QPushButton[variant="danger"] {
    background: rgba(255,107,129,0.10); color: $danger;
    border: 1px solid rgba(255,107,129,0.30);
}
QPushButton[variant="danger"]:hover {
    background: rgba(255,107,129,0.20); border-color: rgba(255,107,129,0.55);
}

#IconBtn { background: transparent; border: none; border-radius: 8px; padding: 0; }
#IconBtn:hover { background: rgba(255,255,255,0.09); }
#IconBtn[danger="true"]:hover { background: rgba(255,107,129,0.28); }

QPushButton[variant="chip"] {
    background: $surface_2; border: 1px solid $border; border-radius: 9px;
    padding: 6px 12px; font-size: 12px; font-weight: 700;
}
QPushButton[variant="chip"]:hover { border-color: $accent; background: $accent_soft; }

#SwapBtn { background: $surface_2; border: 1px solid $border; border-radius: ${radius_sm}px; padding: 0; }
#SwapBtn:hover { background: $surface_3; border-color: $border_strong; }

#Caption { color: $text_faint; font-size: 11px; font-weight: 700; }
#Brand   { font-size: 21px; font-weight: 800; }
#Keycap  { background: rgba(255,255,255,0.22); border-radius: 6px; padding: 2px 7px;
           font-size: 11px; font-weight: 700; color: white; }
#Sep     { background: $border; border: none; min-height: 1px; max-height: 1px; }
#Original { color: $text_dim; font-size: 12px; }
#Translated { font-size: 14px; font-weight: 600; }

/* ---- inputs ---- */
QLineEdit {
    background: $surface_2; border: 1px solid $border;
    border-radius: ${radius_sm}px; padding: 9px 12px;
    selection-background-color: $accent;
}
QLineEdit:focus { border: 1px solid $accent; }

QComboBox {
    background: $surface_2; border: 1px solid $border;
    border-radius: ${radius_sm}px; padding: 9px 12px; min-height: 24px;   /* = 44px tall */
}
QComboBox:hover { border-color: $border_strong; }
QComboBox:on    { border-color: $accent; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url($chevron); width: 14px; height: 14px; }
QComboBox QAbstractItemView {
    background: $surface; border: 1px solid $border_strong;
    border-radius: ${radius_sm}px; padding: 4px;
    selection-background-color: $accent_soft; selection-color: $text;
}

/* ---- slider: groove + filled sub-page + round handle ---- */
QSlider:horizontal { min-height: 24px; }   /* room so the handle is NOT clipped */
QSlider::groove:horizontal { height: 6px; background: rgba(255,255,255,0.10); border-radius: 3px; }
QSlider::sub-page:horizontal {
    border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_2);
}
QSlider::handle:horizontal {
    width: 14px; height: 14px;                       /* + 2*2px border = 18px outer */
    margin: -6px 0;                                  /* -(18 - 6)/2 centres on groove */
    border-radius: 9px; background: white; border: 2px solid $accent;
}
QSlider::handle:horizontal:hover { border-color: #9ad0ff; }

/* ---- progress ---- */
QProgressBar { background: rgba(255,255,255,0.08); border: none; border-radius: 4px;
               min-height: 8px; max-height: 8px; }
QProgressBar::chunk { border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_2); }

/* ---- scrollbars ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.18); border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.3); }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: rgba(255,255,255,0.18); border-radius: 3px; min-width: 30px; }

/* ---- menus / tooltips ---- */
QMenu { background: $surface; border: 1px solid $border_strong; border-radius: ${radius_sm}px; padding: 6px; }
QMenu::item { padding: 8px 18px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; }
QMenu::separator { height: 1px; background: $border; margin: 6px 8px; }
QToolTip { background: $surface_2; color: $text; border: 1px solid $border_strong; padding: 6px 8px; }
""")


def qss():
    return _QSS.substitute(**TOKENS, chevron=icon_file("chevron-down", TOKENS["text_dim"]))


def apply_theme(app: QApplication):
    """Call once, right after creating QApplication."""
    app.setStyle("Fusion")          # consistent base on every OS; QSS behaves best on it
    app.setStyleSheet(qss())


def enable_hidpi():
    """Call BEFORE creating QApplication."""
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


# --------------------------------------------------------------------------
# 4. SMALL WIDGETS
# --------------------------------------------------------------------------
class Button(QPushButton):
    """Button(text, variant='secondary'|'primary'|'ghost'|'danger')"""

    def __init__(self, text="", variant="secondary", parent=None):
        super().__init__(text, parent)
        self.setProperty("variant", variant)      # set BEFORE first show
        self.setCursor(Qt.PointingHandCursor)


class IconButton(QPushButton):
    def __init__(self, name, slot=None, danger=False, tooltip="", parent=None):
        super().__init__(parent)
        self.setObjectName("IconBtn")
        self.setProperty("danger", danger)
        self.setIcon(icon(name, TOKENS["text_dim"], 16))
        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        if slot:
            self.clicked.connect(slot)


class Toggle(QCheckBox):
    """Animated, anti-aliased switch painted with QPainter."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._k = 1.0 if checked else 0.0
        self.setChecked(checked)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.toggled.connect(self._run)

    def _run(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._k)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self):
        return self._k

    def _set(self, v):
        self._k = v
        self.update()

    knob = pyqtProperty(float, _get, _set)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        rad = r.height() / 2
        p.setBrush(QColor(255, 255, 255, 38))
        p.drawRoundedRect(r, rad, rad)
        p.setOpacity(self._k)
        p.setBrush(QColor(TOKENS["accent"]))
        p.drawRoundedRect(r, rad, rad)
        p.setOpacity(1)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(3 + 20 * self._k, 3, 18, 18))


class ColorButton(QPushButton):
    """Swatch + hex label. The swatch has a light ring so BLACK is visible on
    a dark UI (an invisible swatch is a classic bug)."""
    colorChanged = pyqtSignal(QColor)

    def __init__(self, color="#ff3b30", parent=None):
        super().__init__(parent)
        self.setProperty("variant", "secondary")
        self.setCursor(Qt.PointingHandCursor)
        self._color = QColor(color)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self):
        return QColor(self._color)

    def setColor(self, c):
        self._color = QColor(c)
        self._refresh()

    def _refresh(self):
        s = 20
        pm = QPixmap(s * 2, s * 2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 110), 2.4))
        p.setBrush(self._color)
        p.drawEllipse(QRectF(2, 2, s * 2 - 4, s * 2 - 4))
        p.end()
        pm.setDevicePixelRatio(2)
        self.setIcon(QIcon(pm))
        self.setText(self._color.name().upper())

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, "Choose color",
                                  QColorDialog.DontUseNativeDialog)
        if c.isValid():
            self.setColor(c)
            self.colorChanged.emit(c)


def caption(text):
    """Small letter-spaced caps label (FROM / TO / RECENT)."""
    l = QLabel(text.upper())
    l.setObjectName("Caption")
    f = l.font()
    f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
    l.setFont(f)
    return l


class Pill(QWidget):
    """Status chip with a pulsing dot. state: ok | busy | error | idle.
    Painted with QPainter so it is perfectly anti-aliased."""
    COLORS = {"ok": TOKENS["success"], "busy": TOKENS["warning"],
              "error": TOKENS["danger"], "idle": TOKENS["text_dim"]}

    def __init__(self, text="", state="ok", parent=None):
        super().__init__(parent)
        self._text, self._state, self._glow = text, state, 0.0
        self.setFixedHeight(30)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        self.setFont(f)
        self._anim = QPropertyAnimation(self, b"glow", self)
        self._anim.setDuration(1600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def setState(self, text, state):
        self._text, self._state = text, state
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return QSize(QFontMetrics(self.font()).horizontalAdvance(self._text) + 50, 30)

    def _get(self):
        return self._glow

    def _set(self, v):
        self._glow = v
        self.update()

    glow = pyqtProperty(float, _get, _set)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self.COLORS[self._state])
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fill, border = QColor(c), QColor(c)
        fill.setAlpha(28)
        border.setAlpha(130)
        p.setPen(QPen(border, 1))
        p.setBrush(fill)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        cx, cy = 17.0, r.center().y()
        halo = QColor(c)
        halo.setAlphaF(0.40 * (1 - self._glow))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        rad = 4 + 5 * self._glow
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setBrush(c)
        p.drawEllipse(QPointF(cx, cy), 4, 4)
        p.setPen(c.lighter(125))
        p.drawText(QRectF(30, 0, self.width() - 38, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self._text)


class LogoMark(QWidget):
    """Placeholder app mark: dark rounded tile with a glowing lens ring.
    Replace with your own SVG/PNG logo when you have one."""

    def __init__(self, size=34, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        r = QRectF(0.5, 0.5, w - 1, w - 1)
        g = QLinearGradient(0, 0, w, w)
        g.setColorAt(0, QColor("#26304d"))
        g.setColorAt(1, QColor("#141a2c"))
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawRoundedRect(r, w * 0.3, w * 0.3)
        c = QPointF(w / 2, w / 2)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(TOKENS["accent"]), w * 0.085))
        p.drawEllipse(c, w * 0.26, w * 0.26)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TOKENS["accent_2"]))
        p.drawEllipse(c, w * 0.11, w * 0.11)
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawEllipse(QPointF(w * 0.46, w * 0.45), w * 0.035, w * 0.035)


def polish_combo(combo: QComboBox):
    """Give a QComboBox popup real rounded corners (stock popup is square)."""
    popup = combo.view().window()
    popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    popup.setAttribute(Qt.WA_TranslucentBackground)
    combo.setCursor(Qt.PointingHandCursor)
    return combo


# --------------------------------------------------------------------------
# 5. LAYOUT BUILDING BLOCKS
# --------------------------------------------------------------------------
class Section(QFrame):
    """Card with a small-caps heading. Use INSTEAD of QGroupBox (whose title
    straddles the border and looks dated)."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("Section")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 18)
        v.setSpacing(14)
        if title:
            h = QLabel(title.upper())
            h.setObjectName("SectionTitle")
            f = h.font()
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
            h.setFont(f)
            v.addWidget(h)
        self.body = v

    def add(self, w):
        self.body.addWidget(w)
        return w

    def add_row(self, label, widget):
        """label on the left, control on the right"""
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addStretch()
        row.addWidget(widget)
        self.body.addLayout(row)
        return widget


class SliderRow(QWidget):
    """Label on the left, live value on the right, slider underneath."""
    valueChanged = pyqtSignal(int)

    def __init__(self, label, lo, hi, value, suffix="", parent=None):
        super().__init__(parent)
        self._suffix = suffix
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(QLabel(label))
        top.addStretch()
        self._val = QLabel(objectName="Value")
        top.addWidget(self._val)
        v.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._changed)
        v.addWidget(self.slider)
        self.slider.setValue(value)
        self._changed(value)

    def _changed(self, v):
        self._val.setText(f"{v}{self._suffix}")
        self.valueChanged.emit(v)

    def value(self):
        return self.slider.value()

    def setValue(self, v):
        self.slider.setValue(v)


# --------------------------------------------------------------------------
# 6. FRAMELESS SHELL (smooth rounded corners + shadow + custom title bar)
# --------------------------------------------------------------------------
class _FrameMixin:
    MARGIN = 22          # transparent margin that hosts the drop shadow
    TITLEBAR_H = 52

    def _setup_frame(self, title, width, minimize, is_dialog, header=None, actions=()):
        self.setWindowFlags(Qt.FramelessWindowHint | (Qt.Dialog if is_dialog else Qt.Window))
        self.setAttribute(Qt.WA_TranslucentBackground)   # <- required for smooth corners
        self.setWindowTitle(title)
        self._drag = None
        m = self.MARGIN
        outer = QVBoxLayout(self)
        outer.setContentsMargins(m, m, m, m)
        self.card = QFrame(self)
        self.card.setObjectName("Window")
        self.card.setGraphicsEffect(QGraphicsDropShadowEffect(
            self.card, blurRadius=36, xOffset=0, yOffset=8, color=QColor(0, 0, 0, 150)))
        outer.addWidget(self.card)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(1, 1, 1, 1)      # stay inside the 1px border
        root.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(22, 14, 12, 4)
        bar.setSpacing(2)
        bar.addWidget(header if header is not None else QLabel(title, objectName="TitleLabel"))
        bar.addStretch()
        for a in actions:                 # extra icon buttons (settings, expand...)
            bar.addWidget(a)
        if minimize:
            bar.addWidget(IconButton("minimize", self.showMinimized, tooltip="Minimize"))
        bar.addWidget(IconButton("close", self.reject if is_dialog else self.close,
                                 danger=True, tooltip="Close"))
        root.addLayout(bar)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(22, 10, 22, 22)
        self.body.setSpacing(16)
        root.addLayout(self.body, 1)
        self.setFixedWidth(width + 2 * m)

    # drag by the title strip
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.pos().y() < self.MARGIN + self.TITLEBAR_H:
            h = self.windowHandle()
            if h is not None and hasattr(h, "startSystemMove") and h.startSystemMove():
                return                                     # native move (snap, etc.)
            self._drag = e.globalPos() - self.frameGeometry().topLeft()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag)
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)


class FramelessWindow(_FrameMixin, QWidget):
    """Add content with  self.body.addWidget(...)  /  self.body.addLayout(...)"""

    def __init__(self, title="App", width=460, minimize=True, parent=None,
                 header=None, actions=()):
        """header: optional QWidget shown instead of the plain title label
        (logo + brand + status pill...). actions: extra IconButtons placed
        before the window controls."""
        super().__init__(parent)
        self._setup_frame(title, width, minimize, is_dialog=False,
                          header=header, actions=actions)


class FramelessDialog(_FrameMixin, QDialog):
    """Modal dialog with the same shell. Close button = reject()."""

    def __init__(self, title="Dialog", parent=None, width=460):
        super().__init__(parent)
        self._setup_frame(title, width, minimize=False, is_dialog=True)


# --------------------------------------------------------------------------
# 7. VISUAL FEEDBACK LOOP - render to PNG so you can LOOK at your UI
# --------------------------------------------------------------------------
def snapshot(widget, path="/tmp/ui.png", bg="#cfd3de", scale=2):
    """Render `widget` to a PNG (2x supersampled, tightly cropped) over a light
    backdrop so rounded corners + shadow are visible. Works headless:

        QT_QPA_PLATFORM=offscreen python your_script.py

    Then LOOK at the PNG and critique it against the checklist in SKILL.md.
    Do NOT use QT_SCALE_FACTOR for this - it misbehaves on the offscreen platform."""
    from PyQt5.QtGui import QImage
    widget.show()
    widget.adjustSize()
    QApplication.processEvents()
    img = QImage(widget.size() * scale, QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(scale)       # QWidget.render honours the device's DPR
    img.fill(QColor(bg))
    p = QPainter(img)
    widget.render(p)
    p.end()
    img.save(path)
    return path


# --------------------------------------------------------------------------
# 8. PROGRAMMATIC CHECKS (for when you can't / don't trust your eyes)
# --------------------------------------------------------------------------
def _lum(c: QColor):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c.red()) + 0.7152 * f(c.green()) + 0.0722 * f(c.blue())


def contrast_ratio(fg, bg):
    """WCAG contrast. >= 4.5 for body text, >= 3 for large text / UI glyphs."""
    a, b = _lum(QColor(fg)), _lum(QColor(bg))
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def readable_text_on(bg):
    """Pick black or white text for an arbitrary background colour
    (use this for overlay/translation text drawn over user-chosen colours)."""
    return QColor("#101218") if contrast_ratio("#101218", bg) >= contrast_ratio("#ffffff", bg) \
        else QColor("#ffffff")


def lint(root: QWidget):
    """Return a list of human-readable design problems found under `root`.
    Run it in your snapshot script and fix everything it prints."""
    from PyQt5.QtWidgets import QGroupBox, QPushButton as _PB, QMessageBox
    out = []
    if not (root.windowFlags() & Qt.FramelessWindowHint):
        out.append("Top-level window uses the native title bar (white bar on a dark UI). "
                   "Use FramelessWindow / FramelessDialog.")
    if not root.testAttribute(Qt.WA_TranslucentBackground):
        out.append("WA_TranslucentBackground not set -> rounded corners will be square/jagged.")
    for w in root.findChildren(QWidget):
        n = type(w).__name__
        if isinstance(w, QGroupBox):
            out.append(f"QGroupBox '{w.title()}': use Section(title) instead.")
        if isinstance(w, _PB) and w.property("variant") is None and not w.objectName():
            out.append(f"Button '{w.text()}' has no variant (use ui_kit.Button(text, variant)).")
        if isinstance(w, _PB) and w.cursor().shape() != Qt.PointingHandCursor:
            out.append(f"Button '{w.text()}' lacks pointing-hand cursor.")
        ss = w.styleSheet()
        if ss and "#" in ss and "rgba" not in ss and w.objectName() not in ("Window",):
            out.append(f"{n} has a hard-coded colour in setStyleSheet; move it to TOKENS/qss().")
        if isinstance(w, QLabel) and w.buddy() is not None and "&" in w.text() and "&&" not in w.text():
            out.append(f"Label '{w.text()}' has a buddy, so a lone '&' becomes a mnemonic.")
        if isinstance(w, _PB) and "&" in w.text() and "&&" not in w.text():
            out.append(f"Button '{w.text()}': use '&&' to show a literal ampersand.")
    return out
