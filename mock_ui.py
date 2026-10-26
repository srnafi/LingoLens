"""LingoLens — concept UI mock (single-file, standalone).

A design exploration for the LingoLens Control Center. Nothing here is
wired to the real app: no Flask server, no hotkey hook, no snip. It is a
self-contained, fully custom-painted PyQt5 mock so the look can be judged
on its own. Read-only with respect to the rest of the repo.

Run:
    .venv/Scripts/python.exe mock_ui.py
Headless snapshot (writes a PNG, no display needed):
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe mock_ui.py --shot out.png
"""

from __future__ import annotations

import math
import sys

from PyQt5.QtCore import (QEasingCurve, QElapsedTimer, QPointF, QRectF,
                          QSize, Qt, QTimer, QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QImage, QLinearGradient,
                         QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                         QRadialGradient)
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QSizePolicy, QWidget,
                             QVBoxLayout)

# ---------------------------------------------------------------------------
#  Design tokens
# ---------------------------------------------------------------------------
FAM = ["Inter", "Segoe UI Variable Display", "Segoe UI", "Helvetica Neue", "Arial"]
BN_FAM = ["Nirmala UI", "Vrinda", "Segoe UI", "Arial"]

PALETTES = {
    "aurora": {
        "bg1": "#0A0E1E", "bg2": "#161C3E",
        "text": "#EEF2FF", "soft": "#AEB7DC", "muted": "#7A84A8",
        "card": "#FFFFFF", "card_edge": "#FFFFFF", "sheen": "#FFFFFF",
        "indigo": "#6366F1", "indigo2": "#8B5CF6", "cyan": "#22D3EE",
        "fuchsia": "#D946EF", "green": "#34D399", "amber": "#FBBF24",
        "rose": "#FB7185",
        "card_a": 26, "card_edge_a": 40, "sheen_a": 16, "blob_a": 52,
    },
    "day": {
        "bg1": "#F5F7FE", "bg2": "#E6EBFB",
        "text": "#101426", "soft": "#3B4260", "muted": "#5F6883",
        "card": "#FFFFFF", "card_edge": "#0B1020", "sheen": "#FFFFFF",
        "indigo": "#4F46E5", "indigo2": "#7C3AED", "cyan": "#0891B2",
        "fuchsia": "#C026D3", "green": "#059669", "amber": "#D97706",
        "rose": "#E11D48",
        "card_a": 236, "card_edge_a": 30, "sheen_a": 90, "blob_a": 40,
    },
}
THEME = {"name": "aurora"}
THEME_ORDER = ["aurora", "day"]


def C(key, a=None):
    """Palette colour, optionally re-alpha'd."""
    p = PALETTES[THEME["name"]]
    col = QColor(p[key])
    if a is not None:
        col.setAlpha(max(0, min(255, int(a))))
    return col


def A(key):
    """Alpha carried in the palette itself (glass cards etc)."""
    return PALETTES[THEME["name"]][key]


def _load_fonts():
    """Load bundled/system TTFs directly.

    Qt and QFontDatabase are only fully initialised once a
    QGuiApplication exists, so this runs right after it is built. It also
    covers the (common on this box) case where Qt enumerates no system
    fonts at all — without it, every glyph falls back to a missing font
    and renders as nothing.
    """
    from PyQt5.QtGui import QFontDatabase
    for path in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                 "C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/nirmala.ttf"):
        try:
            QFontDatabase.addApplicationFont(path)
        except Exception:
            pass


def font(px, weight=QFont.Normal, fam=None, tracking=0.0):
    f = QFont()
    try:
        f.setFamilies(fam or FAM)
    except AttributeError:  # pragma: no cover - very old Qt
        f.setFamily((fam or FAM)[-1])
    f.setPixelSize(int(px))
    f.setWeight(weight)
    if tracking:
        f.setLetterSpacing(QFont.AbsoluteSpacing, tracking)
    return f


def mix(c1, c2, t):
    """Linear colour blend (QColor.interpolate is Qt6-only)."""
    a, b = QColor(c1), QColor(c2)
    t = max(0.0, min(1.0, float(t)))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t),
                  int(a.alpha() + (b.alpha() - a.alpha()) * t))


def rrect(rect, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(rect), r, r)
    return p


def txt(p, rect, text, f, color, flags=Qt.AlignVCenter | Qt.AlignLeft):
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(QRectF(rect), int(flags), text)


def elide(f, text, width):
    return QFontMetrics(f).elidedText(text, Qt.ElideRight, int(max(10, width)))


# ---------------------------------------------------------------------------
#  Animation helpers
# ---------------------------------------------------------------------------
class Tween(QVariantAnimation):
    def __init__(self, owner, value=0.0, ms=170, curve=QEasingCurve.OutCubic):
        super().__init__(owner)
        self.owner, self.val = owner, float(value)
        self.setDuration(ms)
        self.setEasingCurve(curve)
        self.valueChanged.connect(self._on)

    def _on(self, v):
        self.val = float(v)
        self.owner.update()

    def go(self, target):
        self.stop()
        self.setStartValue(self.val)
        self.setEndValue(float(target))
        self.start()


class Hover(QWidget):
    """Clickable surface with hover/press micro-motion."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.hover = Tween(self, 0, 150)
        self.press = Tween(self, 0, 80)

    def enterEvent(self, e):
        if self.isEnabled():
            self.hover.go(1)

    def leaveEvent(self, e):
        self.hover.go(0)
        self.press.go(0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self.press.go(1)
            e.accept()
        else:
            e.ignore()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self.press.go(0)
            if self.rect().contains(e.pos()):
                self.clicked.emit()


# ---------------------------------------------------------------------------
#  Vector icons on a 24x24 grid
# ---------------------------------------------------------------------------
def draw_icon(p, name, rect, color, width=1.9):
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    rect = QRectF(rect)
    u = min(rect.width(), rect.height()) / 24.0
    p.translate(rect.center().x() - 12 * u, rect.center().y() - 12 * u)
    p.scale(u, u)
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)

    def L(x1, y1, x2, y2):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def poly(*pts):
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))

    if name == "camera":
        p.drawRoundedRect(QRectF(3, 7, 18, 13), 3.5, 3.5)
        path = QPainterPath()
        path.moveTo(8, 7); path.lineTo(9.6, 4.5)
        path.lineTo(14.4, 4.5); path.lineTo(16, 7)
        p.drawPath(path)
        p.drawEllipse(QPointF(12, 13.5), 3.4, 3.4)
    elif name == "swap":
        L(4, 8, 20, 8); poly((16, 4), (20, 8), (16, 12))
        L(4, 16, 20, 16); poly((8, 12), (4, 16), (8, 20))
    elif name == "chevron":
        poly((7, 9.5), (12, 14.5), (17, 9.5))
    elif name == "gear":
        path = QPainterPath()
        n = 32
        for i in range(n):
            ang = 2 * math.pi * (i - 0.5) / n
            r = 9.4 if i % 4 in (1, 2) else 7.2
            pt = QPointF(12 + r * math.cos(ang), 12 + r * math.sin(ang))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(QPointF(12, 12), 3.1, 3.1)
    elif name == "sun":
        p.drawEllipse(QPointF(12, 12), 4, 4)
        for ang in range(0, 360, 45):
            r = math.radians(ang)
            L(12 + 6.6 * math.cos(r), 12 + 6.6 * math.sin(r),
              12 + 9 * math.cos(r), 12 + 9 * math.sin(r))
    elif name == "moon":
        outer = QPainterPath(); outer.addEllipse(QPointF(12, 12), 7.6, 7.6)
        inner = QPainterPath(); inner.addEllipse(QPointF(15.6, 9.4), 6.6, 6.6)
        p.setBrush(QColor(color)); p.setPen(Qt.NoPen)
        p.drawPath(outer.subtracted(inner))
    elif name == "minimize":
        L(6, 12, 18, 12)
    elif name == "close":
        L(6.5, 6.5, 17.5, 17.5); L(17.5, 6.5, 6.5, 17.5)
    elif name == "layers":
        poly((12, 4), (20, 8.4), (12, 12.8), (4, 8.4), (12, 4))
        poly((5.4, 12.6), (12, 16), (18.6, 12.6))
    elif name == "text":
        L(5, 6, 19, 6); L(12, 6, 12, 19)
    elif name == "copy":
        p.drawRoundedRect(QRectF(8, 8, 11, 11), 2.5, 2.5)
        path = QPainterPath()
        path.moveTo(16, 5.5); path.lineTo(5.5, 5.5); path.lineTo(5.5, 16)
        p.drawPath(path)
    elif name == "region":
        pen = p.pen(); pen.setStyle(Qt.DashLine); p.setPen(pen)
        p.drawRoundedRect(QRectF(4, 5, 16, 14), 3, 3)
    elif name == "history":
        p.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 300 * 16)
        poly((12, 3.5), (12, 8.5), (16.5, 6))
        L(12, 8, 12, 12.6); L(12, 12.6, 15.4, 14.6)
    p.restore()


# ---------------------------------------------------------------------------
#  Chrome parts
# ---------------------------------------------------------------------------
class LensMark(QWidget):
    """Rotating lens glyph — doubles as the engine indicator."""

    def __init__(self, size=42):
        super().__init__()
        self.setFixedSize(size, size)
        self.state = "ready"
        self.t0 = QElapsedTimer()
        self.t0.start()
        self._t = QTimer(self)
        self._t.setInterval(33)
        self._t.timeout.connect(self.update)
        self._t.start()

    def set_state(self, s):
        self.state = s
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        s = float(self.width())
        cx = cy = s / 2.0
        radius, stroke = s * 0.30, s * 0.095
        spin = self.t0.elapsed() / 1000.0 * 105.0
        dim = C("muted", 90) if self.state == "ready" else C("amber", 150)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("card_edge", 40), stroke, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        p.setPen(QPen(C("cyan"), stroke, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
                  int((90 - spin) * 16), int(268 * 16))
        ang = math.radians(-38 - spin)
        p.setPen(Qt.NoPen)
        p.setBrush(C("fuchsia"))
        p.drawEllipse(QPointF(cx + radius * math.cos(ang),
                              cy + radius * math.sin(ang)), stroke * 0.55, stroke * 0.55)
        p.setBrush(C("bg1", 240))
        p.drawEllipse(QPointF(cx, cy), 5.6, 5.6)
        p.setBrush(C("green") if self.state == "ready" else C("amber"))
        p.drawEllipse(QPointF(cx, cy), 3.4, 3.4)
        p.setBrush(dim)
        p.drawEllipse(QPointF(cx + radius * math.cos(ang + 2.6),
                              cy + radius * math.sin(ang + 2.6)), 2.0, 2.0)


class Wordmark(QWidget):
    def __init__(self):
        super().__init__()
        self.f = font(19, QFont.Bold, tracking=-0.4)
        self.fs = font(8.4, QFont.Bold, tracking=1.4)
        fm = QFontMetrics(self.f)
        self.w1 = fm.horizontalAdvance("Lingo")
        self.w2 = fm.horizontalAdvance("Lens")
        pill = QFontMetrics(self.fs).horizontalAdvance("CONSOLE") + 20
        self.pill_w = pill
        width = self.w1 + self.w2 + 12 + pill + 4
        self.setFixedSize(width, 44)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        fm = QFontMetrics(self.f)
        y = (self.height() + fm.ascent() - fm.descent()) / 2.0
        a = QPainterPath(); a.addText(0, y, self.f, "Lingo")
        p.fillPath(a, C("text"))
        grad = QLinearGradient(self.w1, 0, self.w1 + self.w2, 0)
        grad.setColorAt(0.0, C("indigo2"))
        grad.setColorAt(1.0, C("cyan"))
        b = QPainterPath(); b.addText(self.w1, y, self.f, "Lens")
        p.fillPath(b, grad)
        pill = QRectF(self.w1 + self.w2 + 12, (self.height() - 20) / 2.0,
                      self.pill_w, 20)
        p.fillPath(rrect(pill, 10), C("card", 24))
        p.setPen(QPen(C("card_edge", 46), 1)); p.drawPath(rrect(pill, 10))
        txt(p, pill, "CONSOLE", self.fs, C("soft"), Qt.AlignCenter)


class IconButton(Hover):
    def __init__(self, icon, size=34, danger=False, tip=""):
        super().__init__()
        self.icon, self.danger = icon, danger
        self.setFixedSize(size, size)
        self.spin = Tween(self, 0, 380, QEasingCurve.InOutCubic)
        if tip:
            self.setToolTip(tip)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        h, pr = self.hover.val, self.press.val
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = 1 - 0.08 * pr
        p.translate(r.center()); p.scale(s, s); p.translate(-r.center())
        bg = C("rose", 220 * h) if self.danger else C("card", 34 * h)
        p.fillPath(rrect(r, 11), bg)
        col = QColor("#FFFFFF") if (self.danger and h > .5) else mix(C("muted"), C("text"), h)
        if self.icon == "gear":
            p.translate(r.center()); p.rotate(65 * h); p.translate(-r.center())
        elif self.icon in ("sun", "moon"):
            p.translate(r.center()); p.rotate(self.spin.val); p.translate(-r.center())
        draw_icon(p, self.icon, r.adjusted(8, 8, -8, -8), col)


class TopBar(QWidget):
    theme_clicked = pyqtSignal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.mark = LensMark(42)
        lay.addWidget(self.mark)
        lay.addWidget(Wordmark())
        lay.addStretch(1)

        self.btn_theme = IconButton("sun", 34, tip="Switch theme")
        self.btn_settings = IconButton("gear", 34, tip="Settings")
        self.btn_min = IconButton("minimize", 34, tip="Minimize")
        self.btn_close = IconButton("close", 34, danger=True, tip="Close")
        for b in (self.btn_theme, self.btn_settings, self.btn_min, self.btn_close):
            lay.addWidget(b)
        self.btn_theme.clicked.connect(self.theme_clicked.emit)
        self.btn_min.clicked.connect(win.showMinimized)
        self.btn_close.clicked.connect(win.close)

    def refresh_theme_icon(self):
        self.btn_theme.icon = "moon" if THEME["name"] == "day" else "sun"
        self.btn_theme.update()


# ---------------------------------------------------------------------------
#  Language pair
# ---------------------------------------------------------------------------
class LangCard(Hover):
    def __init__(self, badge, name, sub, accent="cyan", width=206, height=68):
        super().__init__()
        self.badge, self.name, self.sub = badge, name, sub
        self.accent = accent
        self.setFixedHeight(height)
        self.setMinimumWidth(width)  # stretches to the column, never overflows

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h, pr = self.hover.val, self.press.val
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        s = 1 - 0.012 * pr
        p.translate(r.center()); p.scale(s, s); p.translate(-r.center())
        path = rrect(r, 17)
        p.fillPath(path, C("card", int(A("card_a") + 10 * h)))
        edge = C(self.accent, int(28 + 120 * h)) if h > 0.02 else C("card_edge", A("card_edge_a"))
        p.setPen(QPen(edge, 1.2))
        p.drawPath(path)

        badge = QRectF(13, (self.height() - 42) / 2.0, 42, 42)
        acc = C(self.accent)
        p.fillPath(rrect(badge, 13), C(self.accent, 46))
        txt(p, badge, self.badge, font(11, QFont.Bold), mix(acc, C("text"), 0.34),
            Qt.AlignCenter)

        x = 67
        txt(p, QRectF(x, 12, self.width() - x - 30, 22), self.name,
            font(12.5, QFont.DemiBold), C("text"))
        txt(p, QRectF(x, self.height() - 32, self.width() - x - 30, 20), self.sub,
            font(8.6), C("muted"))
        draw_icon(p, "chevron", QRectF(self.width() - 27, self.height() / 2 - 8, 16, 16),
                  mix(C("muted"), C("text"), h), 2.0)


class SwapButton(Hover):
    def __init__(self, size=46):
        super().__init__()
        self.setFixedSize(size, size)
        self.rot = Tween(self, 0, 420, QEasingCurve.OutBack)
        self.clicked.connect(lambda: self.rot.go(self.rot.val + 180))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        h, pr = self.hover.val, self.press.val
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        s = 1 - 0.08 * pr
        p.translate(r.center()); p.scale(s, s)
        r = r.translated(-r.center())
        p.fillPath(rrect(r, 23), C("card", int(14 + 30 * h)))
        p.setPen(QPen(mix(C("cyan"), C("indigo"), h), 1.3))
        p.drawPath(rrect(r, 23))
        p.rotate(self.rot.val)
        draw_icon(p, "swap", QRectF(-10, -10, 20, 20),
                  mix(C("soft"), C("text"), h), 1.9)


class Chip(Hover):
    def __init__(self, a, b, active=False):
        super().__init__()
        self.a, self.b, self.active = a, b, active
        self.f = font(9.4, QFont.Bold, tracking=0.5)
        fm = QFontMetrics(self.f)
        self.wa = fm.horizontalAdvance(a)
        self.wb = fm.horizontalAdvance(b)
        self.setFixedSize(self.wa + self.wb + 58, 34)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h = self.hover.val
        r = QRectF(self.rect()).adjusted(.5, 3.5, -.5, -.5)
        path = rrect(r, r.height() / 2)
        p.fillPath(path, C("cyan", 40) if self.active else C("card", int(14 + 18 * h)))
        p.setPen(QPen(C("cyan", 150) if self.active else C("card_edge", int(40 + 40 * h)), 1))
        p.drawPath(path)
        col = C("text") if (self.active or h > .3) else C("soft")
        cy = r.center().y()
        x = 15
        txt(p, QRectF(x, r.top(), self.wa + 2, r.height()), self.a, self.f, col)
        x += self.wa + 9
        p.setPen(QPen(col, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(x, cy), QPointF(x + 11, cy))
        p.drawPolyline(QPolygonF([QPointF(x + 7, cy - 3.4), QPointF(x + 11, cy),
                                  QPointF(x + 7, cy + 3.4)]))
        x += 19
        txt(p, QRectF(x, r.top(), self.wb + 2, r.height()), self.b, self.f, col)


# ---------------------------------------------------------------------------
#  Hero action
# ---------------------------------------------------------------------------
class HeroButton(Hover):
    def __init__(self, height=88):
        super().__init__()
        self.setFixedHeight(height)
        self.label = "Snip & Translate"
        self.caps = ["Alt", "Shift", "M"]
        self.shine = Tween(self, 0, 800, QEasingCurve.InOutCubic)

    def enterEvent(self, e):
        super().enterEvent(e)
        self.shine.stop(); self.shine.val = 0.0; self.shine.go(1.0)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h, pr = self.hover.val, self.press.val
        btn = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        c = btn.center()
        s = 1 - 0.014 * pr
        p.translate(c); p.scale(s, s); p.translate(-c)

        glow = QRadialGradient(c.x(), btn.bottom() - 6, btn.width() * 0.46)
        glow.setColorAt(0.0, C("indigo", int(90 + 50 * h)))
        glow.setColorAt(1.0, C("indigo", 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(btn.left() + 20, btn.bottom() - 40,
                             btn.width() - 40, 62))

        path = rrect(btn, 22)
        grad = QLinearGradient(btn.left(), btn.top(), btn.right(), btn.bottom())
        grad.setColorAt(0.0, C("indigo"))
        grad.setColorAt(0.55, C("indigo2"))
        grad.setColorAt(1.0, C("cyan"))
        p.fillPath(path, grad)
        p.fillPath(path, QColor(255, 255, 255, int(22 * h)))
        if 0.0 < self.shine.val < 1.0:
            x = btn.left() - 120 + (btn.width() + 200) * self.shine.val
            sweep = QPainterPath()
            sweep.addPolygon(QPolygonF([QPointF(x, btn.top()),
                                        QPointF(x + 54, btn.top()),
                                        QPointF(x + 16, btn.bottom()),
                                        QPointF(x - 38, btn.bottom())]))
            sweep.closeSubpath()
            p.fillPath(sweep.intersected(path), QColor(255, 255, 255, 54))
        p.setPen(QPen(QColor(255, 255, 255, 70), 1.1)); p.setBrush(Qt.NoBrush)
        p.drawPath(rrect(btn.adjusted(.5, .5, -.5, -.5), 21.5))

        f_text, f_cap = font(15, QFont.Bold, tracking=-0.2), font(9.6, QFont.Bold)
        fm_t, fm_c = QFontMetrics(f_text), QFontMetrics(f_cap)
        tw = fm_t.horizontalAdvance(self.label)
        cap_w = [fm_c.horizontalAdvance(t) + 22 for t in self.caps]
        caps_total = sum(cap_w) + 7 * (len(cap_w) - 1)
        total = 30 + 12 + tw + 22 + caps_total
        x = c.x() - total / 2.0
        draw_icon(p, "camera", QRectF(x, c.y() - 14, 28, 28), QColor("#FFFFFF"), 1.8)
        x += 42
        txt(p, QRectF(x, btn.top(), tw + 6, btn.height()), self.label, f_text,
            QColor("#FFFFFF"))
        x += tw + 18
        for t, w in zip(self.caps, cap_w):
            kr = QRectF(x, c.y() - 12, w, 24)
            # dark chip, not white: keeps the white keycap text legible even
            # over the light cyan end of the gradient.
            p.fillPath(rrect(kr, 8), QColor(24, 20, 64, 118))
            p.setPen(QPen(QColor(255, 255, 255, 70), 1)); p.drawPath(rrect(kr, 8))
            txt(p, kr, t, f_cap, QColor(255, 255, 255, 242), Qt.AlignCenter)
            x += w + 7


class OptionTile(Hover):
    def __init__(self, icon, title, sub, active=False, width=166, height=76):
        super().__init__()
        self.icon, self.title, self.sub = icon, title, sub
        self.active = active
        self.setFixedSize(width, height)
        self.clicked.connect(self._toggle)

    def _toggle(self):
        self.active = not self.active
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h = self.hover.val
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rrect(r, 15)
        p.fillPath(path, C("indigo", 40) if self.active else C("card", int(A("card_a") - 4 * A("card_a") / 26 + 12 * h)))
        p.setPen(QPen(C("indigo", 170) if self.active else C("card_edge", int(A("card_edge_a") + 30 * h)), 1.1))
        p.drawPath(path)

        chip = QRectF(12, 12, 28, 28)
        p.fillPath(rrect(chip, 9), C("cyan", 40) if self.active else C("card", 46))
        draw_icon(p, self.icon, chip.adjusted(5, 5, -5, -5),
                  C("cyan") if self.active else mix(C("soft"), C("text"), 0.75 + 0.25 * h),
                  2.0 if self.active else 2.2)
        if self.active:
            dot = QRectF(self.width() - 24, 14, 12, 12)
            p.setPen(Qt.NoPen); p.setBrush(C("green")); p.drawEllipse(dot)
        txt(p, QRectF(12, 45, self.width() - 24, 18), self.title,
            font(10.4, QFont.DemiBold), C("text"))
        txt(p, QRectF(12, 60, self.width() - 24, 16), self.sub, font(8.4),
            C("soft"))


# ---------------------------------------------------------------------------
#  Right rail
# ---------------------------------------------------------------------------
class StatusCard(QWidget):
    def __init__(self, height=132):
        super().__init__()
        self.setFixedHeight(height)
        self.t0 = QElapsedTimer()
        self.t0.start()
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self.update)
        self._t.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rrect(r, 18)
        p.fillPath(path, C("card", A("card_a")))
        p.setPen(QPen(C("card_edge", A("card_edge_a")), 1.1))
        p.drawPath(path)
        t = self.t0.elapsed() / 1000.0

        p.save()
        p.setClipPath(path)
        gr = QRadialGradient(r.left() + 30, r.top() + 10, 150)
        gr.setColorAt(0.0, C("green", 34))
        gr.setColorAt(1.0, C("green", 0))
        p.setPen(Qt.NoPen); p.setBrush(gr)
        p.drawRect(r)
        p.restore()

        cx, cy = r.left() + 34, r.top() + 34
        for k in range(3):
            ph = ((t * 0.55) + k / 3.0) % 1.0
            rad = 9 + ph * 17
            p.setPen(QPen(C("green", int(120 * (1 - ph))), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setPen(Qt.NoPen); p.setBrush(C("green"))
        p.drawEllipse(QPointF(cx, cy), 6.0, 6.0)

        txt(p, QRectF(cx + 22, cy - 22, 180, 20), "Engine ready",
            font(12, QFont.DemiBold), C("text"))
        txt(p, QRectF(cx + 22, cy - 4, 200, 18), "EasyOCR + OpenVINO",
            font(8.8), C("soft"))
        txt(p, QRectF(cx + 22, cy + 11, 200, 16), "on-device · no cloud",
            font(8.4), C("muted"))

        pill = QRectF(r.right() - 74, r.top() + 16, 58, 22)
        p.setBrush(C("green", 46)); p.setPen(QPen(C("green", 120), 1))
        p.drawPath(rrect(pill, 11))
        p.setBrush(C("green"))
        p.drawEllipse(QRectF(pill.left() + 9, pill.center().y() - 3, 6, 6))
        txt(p, pill.adjusted(20, 0, -6, 0), "LIVE", font(8.6, QFont.Bold), C("green"))

        base_y = r.bottom() - 18
        bw, gap = 9.0, 3.5
        for i in range(16):
            amp = 0.45 + 0.55 * abs(math.sin(t * 1.5 + i * 0.7))
            hgt = 4 + 16 * amp
            bar = QRectF(r.left() + 16 + i * (bw + gap), base_y - hgt, bw, hgt)
            p.setPen(Qt.NoPen)
            p.setBrush(C("cyan", 160 if i % 4 == 0 else 105))
            p.drawPath(rrect(bar, 2.5))
        txt(p, QRectF(r.left() + 16 + 16 * (bw + gap) + 8, base_y - 30, 96, 18),
            "142 ms", font(8.8, QFont.DemiBold), C("soft"))
        txt(p, QRectF(r.left() + 16 + 16 * (bw + gap) + 8, base_y - 14, 96, 16),
            "latency", font(8.0), C("muted"))


class PreviewCard(QWidget):
    """Mock of the in-place overlay: source line replaced by the translation."""

    def __init__(self, height=210):
        super().__init__()
        self.keep_source = False
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rrect(r, 18)
        p.fillPath(path, C("card", A("card_a")))
        p.setPen(QPen(C("card_edge", A("card_edge_a")), 1.1))
        p.drawPath(path)

        txt(p, QRectF(16, 12, 200, 18), "Overlay preview",
            font(10, QFont.DemiBold), C("soft"))
        txt(p, QRectF(r.right() - 130, 12, 114, 18), "paragraph mode",
            font(8.2), C("muted"), Qt.AlignRight | Qt.AlignVCenter)

        screen = QRectF(14, 38, r.width() - 28, r.height() - 76)
        p.fillPath(rrect(screen, 13), C("bg1", 210 if THEME["name"] == "aurora" else 130))
        p.setPen(QPen(C("card_edge", 34), 1))
        p.drawPath(rrect(screen, 13))

        p.save()
        p.setClipPath(rrect(screen, 13))
        for i, w in enumerate([.34, .62, .48]):
            y = screen.top() + 14 + i * 15
            p.setPen(Qt.NoPen)
            p.setBrush(C("card", 26))
            p.drawPath(rrect(QRectF(screen.left() + 14, y, (screen.width() - 60) * w, 4), 2))
        for i, w in enumerate([.30, .55]):
            y = screen.top() + 146 + i * 15
            p.setPen(Qt.NoPen)
            p.setBrush(C("card", 22))
            p.drawPath(rrect(QRectF(screen.left() + 14, y, (screen.width() - 60) * w, 4), 2))

        box = QRectF(screen.left() + 12, screen.top() + 56,
                     screen.width() - 24, 84)
        p.setBrush(C("indigo", 46))
        p.setPen(Qt.NoPen)
        p.drawPath(rrect(box, 9))
        p.setPen(QPen(C("cyan", 190), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rrect(box.adjusted(1, 1, -1, -1), 8))

        inner = box.adjusted(12, 9, -12, -9)
        if getattr(self, "keep_source", False):
            p.setFont(font(8.6))
            p.setPen(C("muted"))
            p.drawText(QRectF(inner.left(), inner.top(), inner.width(), 30),
                       int(Qt.TextWordWrap | Qt.AlignTop | Qt.AlignLeft),
                       "The quick brown fox jumps over the lazy dog")
            dst = QRectF(inner.left(), inner.top() + 30,
                         inner.width(), inner.height() - 30)
        else:
            dst = inner
        p.setFont(font(13.2, QFont.DemiBold, BN_FAM))
        p.setPen(C("text"))
        p.drawText(dst, int(Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignLeft),
                   "দ্রুত বাদামী শিয়ালটি অলস কুকুরের উপর দিয়ে লাফায়")
        p.restore()

        txt(p, QRectF(16, r.bottom() - 24, r.width() - 32, 18),
            "translated in place · background kept", font(8.2), C("soft"))


class StatTile(QWidget):
    def __init__(self, value, label, accent="cyan", height=78):
        super().__init__()
        self.value, self.label, self.accent = value, label, accent
        self.setFixedHeight(height)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rrect(r, 16)
        p.fillPath(path, C("card", A("card_a")))
        p.setPen(QPen(C("card_edge", A("card_edge_a")), 1.1))
        p.drawPath(path)
        p.save(); p.setClipPath(path)
        gr = QLinearGradient(r.left(), r.bottom(), r.right(), r.top())
        gr.setColorAt(0.0, C(self.accent, 46))
        gr.setColorAt(1.0, C(self.accent, 0))
        p.setPen(Qt.NoPen); p.setBrush(gr); p.drawRect(r)
        p.restore()
        txt(p, QRectF(14, 12, r.width() - 28, 26), self.value,
            font(19, QFont.Bold, tracking=-0.3), C("text"))
        txt(p, QRectF(14, 42, r.width() - 28, 18), self.label,
            font(8.6), C("soft"))


class Footer(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(34)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(QPen(C("card_edge", 28), 1))
        p.drawLine(QPointF(0, 8.5), QPointF(self.width(), 8.5))
        txt(p, QRectF(0, 12, self.width() * 0.7, 20),
            "Global hotkey works in any app · screenshots never leave the device",
            font(8.6), C("muted"))
        txt(p, QRectF(self.width() * 0.6, 12, self.width() * 0.4, 20),
            "v1.2.0 · GPL-3.0", font(8.6), C("muted"),
            Qt.AlignRight | Qt.AlignVCenter)


# ---------------------------------------------------------------------------
#  Window
# ---------------------------------------------------------------------------
SHADOW = 30
BODY_W, BODY_H = 900, 612
RADIUS = 24


class MockWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(BODY_W + 2 * SHADOW, BODY_H + 2 * SHADOW)
        self.setWindowTitle("LingoLens — Control Center (mock)")
        _load_fonts()  # idempotent; safe for any entry point
        self._bg = None
        self._drag = None
        self.t0 = QElapsedTimer()
        self.t0.start()
        self._anim = QTimer(self)
        self._anim.setInterval(40)
        self._anim.timeout.connect(self.update)

        root = QVBoxLayout(self)
        root.setContentsMargins(SHADOW + 24, SHADOW + 18, SHADOW + 24, SHADOW + 16)
        root.setSpacing(0)

        self.top = TopBar(self)
        root.addWidget(self.top)
        root.addSpacing(18)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(22)
        body.addWidget(self._left_column(), 1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(14)
        right.addWidget(StatusCard())
        self.preview = PreviewCard()
        right.addWidget(self.preview)
        stats = QHBoxLayout(); stats.setSpacing(14)
        stats.addWidget(StatTile("128", "snips today", "cyan"))
        stats.addWidget(StatTile("94%", "avg confidence", "fuchsia"))
        right.addLayout(stats)
        wrap = QWidget()
        wrap.setLayout(right)
        wrap.setFixedWidth(312)
        body.addWidget(wrap, 0)
        root.addLayout(body)
        root.addWidget(Footer())

        self.top.theme_clicked.connect(self.cycle_theme)
        self.tiles[1].clicked.connect(self._sync_preview)
        self._recolour_labels()

    # -- left column -------------------------------------------------------
    def _left_column(self):
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        head = QWidget()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        from PyQt5.QtWidgets import QLabel
        title = QLabel("Translate your screen, in place.")
        title.setFont(font(26, QFont.Bold, tracking=-0.6))
        sub = QLabel("Snip any region — LingoLens reads it, removes the original "
                     "text and prints the translation where it stood.")
        sub.setFont(font(10.4))
        sub.setWordWrap(True)
        self._plain_labels = [(title, "text"), (sub, "soft")]
        hl.addWidget(title); hl.addWidget(sub)
        col.addWidget(head)
        col.addSpacing(18)

        pair = QHBoxLayout(); pair.setSpacing(12)
        self.src = LangCard("EN", "English", "OCR · Latin model", "cyan")
        self.dst = LangCard("BN", "Bengali", "target · Bangla script", "indigo")
        swap = SwapButton()
        pair.addWidget(self.src, 1)
        pair.addWidget(swap, 0, Qt.AlignVCenter)
        pair.addWidget(self.dst, 1)
        col.addLayout(pair)
        col.addSpacing(18)

        chips = QHBoxLayout(); chips.setSpacing(9)
        for i, (a, b) in enumerate([("EN", "BN"), ("BN", "EN"), ("EN", "RU"), ("JA", "EN")]):
            chips.addWidget(Chip(a, b, active=(i == 0)))
        chips.addStretch(1)
        col.addLayout(chips)
        col.addStretch(1)

        from PyQt5.QtWidgets import QLabel as _L
        lab = _L("CAPTURE OPTIONS")
        lab.setFont(font(8.4, QFont.Bold, tracking=1.6))
        self._plain_labels.append((lab, "muted"))
        col.addWidget(lab)
        col.addSpacing(10)

        opts = QHBoxLayout(); opts.setSpacing(12)
        self.tiles = [OptionTile("layers", "Paragraph mode", "group lines", True),
                      OptionTile("text", "Keep source text", "show both", False),
                      OptionTile("copy", "Copy to clipboard", "on snip", True)]
        for t in self.tiles:
            opts.addWidget(t, 1)
        col.addLayout(opts)
        col.addSpacing(18)

        self.hero = HeroButton()
        col.addWidget(self.hero)
        return self._wrap(col)

    @staticmethod
    def _wrap(layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    # -- theme -------------------------------------------------------------
    def cycle_theme(self):
        nxt = THEME_ORDER[(THEME_ORDER.index(THEME["name"]) + 1) % len(THEME_ORDER)]
        THEME["name"] = nxt
        self._bg = None
        self.top.refresh_theme_icon()
        self._recolour_labels()
        for child in self.findChildren(QWidget):
            child.update()
        self.update()

    def _sync_preview(self):
        """The preview must obey the Keep-source-text toggle."""
        self.preview.keep_source = self.tiles[1].active
        self.preview.update()

    def _recolour_labels(self):
        for lb, key in self._plain_labels:
            lb.setStyleSheet(f"color:{C(key).name()};background:transparent;")

    # -- painting ----------------------------------------------------------
    def body_rect(self):
        return QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

    def _render_bg(self):
        pm = QPixmap(self.size())
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHints(QPainter.Antialiasing)
        body = self.body_rect()

        for i in range(SHADOW, 0, -1):
            a = int(52 * (1 - i / float(SHADOW)) ** 2.6)
            if a <= 0:
                continue
            p.setPen(QPen(QColor(4, 6, 16, a), 1.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(body.adjusted(-i, -i + 3, i, i + 3),
                              RADIUS + i, RADIUS + i)

        path = rrect(body, RADIUS)
        grad = QLinearGradient(body.topLeft(), body.bottomRight())
        grad.setColorAt(0.0, C("bg1"))
        grad.setColorAt(1.0, C("bg2"))
        p.fillPath(path, grad)

        p.save()
        p.setClipPath(path)
        sheen = QLinearGradient(body.topLeft(), QPointF(body.left(), body.top() + 260))
        sheen.setColorAt(0.0, C("sheen", A("sheen_a")))
        sheen.setColorAt(1.0, C("sheen", 0))
        p.setPen(Qt.NoPen); p.setBrush(sheen)
        p.drawRect(body)
        p.restore()

        p.setPen(QPen(C("card_edge", 46 if THEME["name"] == "aurora" else 60), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rrect(body.adjusted(.6, .6, -.6, -.6), RADIUS - .6))
        p.end()
        return pm

    def paintEvent(self, e):
        if self._bg is None:
            self._bg = self._render_bg()
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self._bg)

        body = self.body_rect()
        path = rrect(body, RADIUS)
        t = self.t0.elapsed() / 1000.0
        p.save()
        p.setClipPath(path)
        p.setPen(Qt.NoPen)
        blobs = [(C("indigo", A("blob_a")), 0.16, 0.06, 300, 0.23, 0.0),
                 (C("cyan", int(A("blob_a") * 0.8)), 0.92, 0.14, 260, -0.19, 2.1),
                 (C("fuchsia", int(A("blob_a") * 0.7)), 0.55, 1.02, 320, 0.15, 4.2)]
        for col, fx, fy, rad, sp, phase in blobs:
            cx = body.left() + body.width() * fx + 26 * math.sin(t * sp + phase)
            cy = body.top() + body.height() * fy + 22 * math.cos(t * sp * 1.3 + phase)
            g = QRadialGradient(QPointF(cx, cy), rad)
            g.setColorAt(0.0, col)
            g.setColorAt(1.0, QColor(col.red(), col.green(), col.blue(), 0))
            p.setBrush(g)
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))
        p.restore()

    # -- frameless drag ----------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------
def _boot_fonts(app):
    _load_fonts()
    app.setFont(font(10))


def snapshot(win, path, scale=2, canvas="#cfd3de"):
    win.show()
    for _ in range(8):
        QApplication.processEvents()
    img = QImage(win.size() * scale, QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(scale)
    img.fill(QColor(canvas))
    p = QPainter(img)
    win.render(p)
    p.end()
    img.save(path)
    return path


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _boot_fonts(app)
    win = MockWindow()
    if "--shot" in sys.argv:
        out = sys.argv[sys.argv.index("--shot") + 1]
        print(snapshot(win, out))
        return 0
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())