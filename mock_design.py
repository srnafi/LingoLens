"""LingoLens — "Studio" concept UI mock (single file, standalone, read-only).

A design exploration for the LingoLens Control Center: dark aurora shell with
drifting gradient blobs, left icon rail, From/To language cards with animated
swap, gradient Snip & Translate hero, and a live simulated pipeline pane
(Detect -> OCR -> Translate -> Overlay). Nothing is wired to the real app:
no Flask server, no hotkey hook, no capture. Pure PyQt5, all vector-painted,
no assets, no QSS.

Run:
    .venv/Scripts/python.exe mock_design.py
Headless snapshot:
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe mock_design.py --shot out.png
"""

from __future__ import annotations

import math
import os
import sys
import time

from PyQt5.QtCore import (QEasingCurve, QPointF, QRectF, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QKeySequence,
                         QLinearGradient, QPainter, QPainterPath, QPen,
                         QRadialGradient)
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QShortcut,
                             QStackedWidget, QVBoxLayout, QWidget)

# ---------------------------------------------------------------------------
#  Tokens — same hexes as ui/theme.py (aurora / day), reused verbatim
# ---------------------------------------------------------------------------
FAMS = ["Inter", "Segoe UI Variable Display", "Segoe UI", "Arial"]
BN_FAMS = ["Nirmala UI", "Vrinda", "Segoe UI", "Arial"]

PAL = {
    "aurora": dict(bg1="#0E1230", bg2="#171C3C", text="#F4F6FF", soft="#C5CBE8",
                   muted="#7F88B0", indigo="#6366F1", indigo2="#8B5CF6",
                   cyan="#22D3EE", fuchsia="#D946EF", green="#34D399",
                   amber="#FBBF24", rose="#FB7185", card="#FFFFFF",
                   edge="#FFFFFF", card_a=16, edge_a=44, blob_a=30, glow=60),
    "day": dict(bg1="#F6F8FE", bg2="#E9EEFB", text="#131726", soft="#3B4256",
                muted="#7A839B", indigo="#4F46E5", indigo2="#7C3AED",
                cyan="#0EA5E9", fuchsia="#C026D3", green="#0FA97A",
                amber="#C77D0A", rose="#E11D48", card="#FFFFFF",
                edge="#0B1020", card_a=235, edge_a=30, blob_a=26, glow=26),
}
THEME_ORDER = ["aurora", "day"]

FROM_LANGS = [("English", 1), ("Spanish", 1), ("French", 1), ("Italian", 1),
              ("Portuguese", 1), ("Vietnamese", 1), ("German", 1),
              ("Chinese", 2), ("Japanese", 3), ("Russian", 4),
              ("Bengali", 5), ("Korean", 6)]
FROM_SHORT = ["EN", "ES", "FR", "IT", "PT", "VI", "DE", "ZH", "JA", "RU", "BN", "KO"]
TO_LANGS = [("English", "en"), ("Spanish", "es"), ("French", "fr"), ("German", "de"),
            ("Italian", "it"), ("Portuguese", "pt"), ("Russian", "ru"),
            ("Vietnamese", "vi"), ("Bengali", "bn"), ("Hindi", "hi"),
            ("Chinese (Simplified)", "zh-CN"), ("Japanese", "ja"), ("Korean", "ko"),
            ("Arabic", "ar"), ("Urdu", "ur"), ("Dutch", "nl"), ("Turkish", "tr"),
            ("Polish", "pl"), ("Indonesian", "id"), ("Thai", "th")]
TO_SHORT = [c.split("-")[0].upper() for _, c in TO_LANGS]


class _Th:
    a, b = PAL["aurora"], PAL["aurora"]
    t = 1.0

    @classmethod
    def c(cls, k):
        x, y = cls.a[k], cls.b[k]
        if isinstance(x, (str, QColor)):
            c1, c2 = QColor(x), QColor(y)
            return QColor(int(c1.red() + (c2.red() - c1.red()) * cls.t),
                          int(c1.green() + (c2.green() - c1.green()) * cls.t),
                          int(c1.blue() + (c2.blue() - c1.blue()) * cls.t),
                          int(c1.alpha() + (c2.alpha() - c1.alpha()) * cls.t))
        return x + (y - x) * cls.t

    @classmethod
    def alpha(cls, k):
        return int(cls.c(k))


Th = _Th


def alpha(c, a):
    c = QColor(c)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def rrect(rect, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(rect), r, r)
    return p


def font(px, weight=QFont.Normal, fam=None, tracking=0.0):
    f = QFont()
    try:
        f.setFamilies(fam or FAMS)
    except AttributeError:
        f.setFamily((fam or FAMS)[-1])
    f.setPointSizeF(px)
    f.setWeight(weight)
    if tracking:
        f.setLetterSpacing(QFont.AbsoluteSpacing, tracking)
    return f


def draw_text(p, rect, text, f, color, flags=Qt.AlignVCenter | Qt.AlignLeft):
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(QRectF(rect), int(flags), text)


def draw_icon(p, name, rect, color, w=1.9):
    """Vector icon set in a 24x24 normalized space."""
    p.save()
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    p.translate(rect.x(), rect.y())
    k = rect.width() / 24.0
    p.scale(k, k)
    pen = QPen(QColor(color), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    L = lambda x1, y1, x2, y2: p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    if name == "lens":
        p.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        L(13.2, 13.2, 19.5, 19.5)
    elif name == "snap":
        for cx, cy, sx, sy in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
            p.drawPolyline([QPointF(cx, cy + 3.5 * sy), QPointF(cx, cy),
                            QPointF(cx + 3.5 * sx, cy)])
        L(10.5, 12, 13.5, 12)
        L(12, 10.5, 12, 13.5)
    elif name == "home":
        p.drawPolyline([QPointF(4.5, 11), QPointF(12, 4.5), QPointF(19.5, 11)])
        p.drawRect(QRectF(9.5, 11.5, 5, 8))
    elif name == "history":
        p.drawEllipse(QRectF(5, 5, 14, 14))
        p.drawPolyline([QPointF(12, 12), QPointF(12, 8.2)])
        p.drawPolyline([QPointF(12, 12), QPointF(15.2, 14)])
    elif name == "gear":
        p.drawEllipse(QRectF(7.2, 7.2, 9.6, 9.6))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(12 + 7.6 * math.cos(a), 12 + 7.6 * math.sin(a)),
                       QPointF(12 + 10.2 * math.cos(a), 12 + 10.2 * math.sin(a)))
    elif name == "sun":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(12 + 10.4 * math.cos(a), 12 + 10.4 * math.sin(a)),
                       QPointF(12 + 12.6 * math.cos(a), 12 + 12.6 * math.sin(a)))
    elif name == "moon":
        p1 = QPainterPath()
        p1.addEllipse(QPointF(12, 12), 8.2, 8.2)
        p2 = QPainterPath()
        p2.addEllipse(QPointF(9.7, 10.6), 6.4, 6.4)
        p.setBrush(alpha(color, 200))
        p.drawPath(p1.subtracted(p2))
    elif name == "close":
        L(6.5, 6.5, 17.5, 17.5)
        L(17.5, 6.5, 6.5, 17.5)
    elif name == "minus":
        L(6, 12, 18, 12)
    elif name == "swap":
        p.drawPolyline([QPointF(7, 8), QPointF(7, 16.6)])
        p.drawPolyline([QPointF(4.2, 14), QPointF(7, 16.8), QPointF(9.8, 14)])
        p.drawPolyline([QPointF(17, 16), QPointF(17, 7.4)])
        p.drawPolyline([QPointF(14.2, 10), QPointF(17, 7.2), QPointF(19.8, 10)])
    elif name == "check":
        p.drawPolyline([QPointF(5.5, 12.5), QPointF(10, 17), QPointF(18.5, 7)])
    elif name == "chevron":
        p.drawPolyline([QPointF(8.5, 10), QPointF(12, 13.5), QPointF(15.5, 10)])
    elif name == "chev_r":
        p.drawPolyline([QPointF(9.5, 9), QPointF(14.5, 12), QPointF(9.5, 15)])
    elif name == "back":
        p.drawPolyline([QPointF(15.5, 7), QPointF(9, 12), QPointF(15.5, 17)])
    p.restore()


# ---------------------------------------------------------------------------
#  Mock state — mirrors settings.json keys, defaults read from the real file
# ---------------------------------------------------------------------------
class MockState:
    def __init__(self, settings_path):
        self.fill = "#6366F1"
        self.op = 42
        self.bw = 2
        self.fs = 7
        self.theme = "aurora"
        self.src = 0            # FROM_LANGS index
        self.dst = 9            # TO_LANGS index (Bengali)
        self.recents = [(0, 9), (10, 0), (0, 6)]   # (from_idx, to_idx)
        try:
            import json
            raw = json.load(open(settings_path, encoding="utf-8"))
            self.fill = raw.get("fill_color", self.fill)
            self.op = int(raw.get("opacity", 0.42) * 100)
            self.bw = raw.get("line_width", self.bw)
            self.fs = raw.get("font_size", self.fs)
            self.theme = raw.get("theme", self.theme)
            for n, o in FROM_LANGS:
                if n == raw.get("source_lang_name"):
                    self.src = FROM_LANGS.index((n, o))
            for i, (n, c) in enumerate(TO_LANGS):
                if c == raw.get("dest_lang"):
                    self.dst = i
            if raw.get("recent_pairs"):
                self.recents = []
                for e in raw["recent_pairs"][:3]:
                    fi = next((i for i, (n, _) in enumerate(FROM_LANGS)
                               if n == e.get("from")), 0)
                    ti = next((i for i, (n, c) in enumerate(TO_LANGS)
                               if c == e.get("to")), 0)
                    self.recents.append((fi, ti))
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  Base interactive widget
# ---------------------------------------------------------------------------
class Hover(QWidget):
    clicked = pyqtSignal()

    def __init__(self, *a, cursor=True, **k):
        super().__init__(*a, **k)
        self.hv = 0.0
        self._pressed = False
        if cursor:
            self.setCursor(Qt.PointingHandCursor)
        self._ha = QVariantAnimation(self, duration=160,
                                     easingCurve=QEasingCurve.OutCubic)
        self._ha.valueChanged.connect(self._on_hover)

    def _on_hover(self, v):
        self.hv = v
        self.update()

    def _tween(self, to):
        self._ha.stop()
        self._ha.setStartValue(self.hv)
        self._ha.setEndValue(to)
        self._ha.start()

    def enterEvent(self, e):
        self._tween(1.0)

    def leaveEvent(self, e):
        self._tween(0.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pressed = True

    def mouseReleaseEvent(self, e):
        if (e.button() == Qt.LeftButton and self._pressed
                and self.rect().contains(e.pos())):
            self.clicked.emit()
        self._pressed = False


# ---------------------------------------------------------------------------
#  Small primitives: LensMark, Wordmark, EnginePill, RailButton, IconButton
# ---------------------------------------------------------------------------
class LensMark(QWidget):
    def __init__(self, size, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, Th.c("indigo"))
        g.setColorAt(1, Th.c("indigo2"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, r.width() * 0.27, r.width() * 0.27)
        draw_icon(p, "lens", r.adjusted(r.width() * 0.24, r.width() * 0.24,
                                        -r.width() * 0.24, -r.width() * 0.24),
                  "#FFFFFF", 1.7)


class Wordmark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(210, 46)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(0, 6, 34, 34)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, Th.c("indigo"))
        g.setColorAt(1, Th.c("indigo2"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, r.width() * 0.27, r.width() * 0.27)
        draw_icon(p, "lens", r.adjusted(8, 8, -8, -8), "#FFFFFF", 1.7)
        draw_text(p, QRectF(42, 5, 170, 22), "LingoLens",
                  font(15, QFont.Bold, tracking=0.7), Th.c("text"))
        draw_text(p, QRectF(42, 27, 170, 14), "screen OCR translator",
                  font(8.5, QFont.Normal, tracking=0.4), Th.c("muted"))


class EnginePill(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "ready"
        self.setFixedHeight(28)

    def set_state(self, s):
        self.state = s
        self.update()

    def sizeHint(self):
        return self.size()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        text = "EasyOCR + OpenVINO · on-device OCR" if self.state != "busy" \
            else "Translating… · EasyOCR + OpenVINO"
        f = font(9, QFont.DemiBold)
        w = int(QFontMetrics(f).horizontalAdvance(text)) + 42
        self.setFixedWidth(w)
        p.setPen(alpha(Th.c("edge"), Th.alpha("edge_a") * 0.6))
        p.setBrush(alpha(Th.c("card"), Th.alpha("card_a") * 0.7))
        p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        dot = {"ready": Th.c("green"), "busy": Th.c("amber"),
               "boot": Th.c("cyan")}[self.state]
        p.setBrush(dot)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(16, 14), 3.4, 3.4)
        draw_text(p, QRectF(26, 0, w - 30, 28), text, f, Th.c("soft"))


class RailButton(Hover):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.label = label
        self.sel = False
        self.setFixedSize(56, 56)

    def select(self, s):
        self.sel = s
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(6, 5, 44, 44)
        if self.sel:
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(Th.c("indigo"), 30 + 26 * self.hv))
            p.drawRoundedRect(r, 13, 13)
        else:
            p.setPen(alpha(Th.c("indigo"), 26 * self.hv))
            p.setBrush(alpha(Th.c("card"), 10 * self.hv))
            p.drawRoundedRect(r, 13, 13)
        col = Th.c("indigo") if self.sel else Th.c("muted")
        ic = QRectF(16, 15, 24, 24)
        draw_icon(p, self.icon, ic, col, 1.7)
        draw_text(p, QRectF(0, 40, 56, 14), self.label,
                  font(7.5, QFont.DemiBold), Th.c("muted") if not self.sel
                  else Th.c("soft"), Qt.AlignHCenter)


class IconButton(Hover):
    def __init__(self, icon, size=34, danger=False, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.danger = danger
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        if self.hv > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(Th.c("card"), 14 * self.hv))
            p.drawRoundedRect(r, r.width() / 2, r.width() / 2)
        col = Th.c("rose") if self.danger else Th.c("soft")
        draw_icon(p, self.icon, r.adjusted(6, 6, -6, -6), col, 1.8)


class TitleLabel(QWidget):
    def __init__(self, text, px=15, weight=QFont.Bold, key="text",
                 h=34, tracking=0.0, parent=None):
        super().__init__(parent)
        self._t, self._px, self._w, self._k, self._tr = text, px, weight, key, tracking
        self.setFixedHeight(h)
        fm = QFontMetrics(font(self._px, self._w, tracking=self._tr))
        self.setFixedWidth(fm.horizontalAdvance(text) + 2)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        draw_text(p, self.rect(), self._t,
                  font(self._px, self._w, tracking=self._tr), Th.c(self._k))


class PillButton(Hover):
    def __init__(self, text, kind="primary", w=120, parent=None):
        super().__init__(parent)
        self.text, self.kind = text, kind
        self.setFixedSize(w, 40)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.kind == "primary":
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, Th.c("indigo"))
            g.setColorAt(1, Th.c("indigo2"))
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 20, 20)
            col = QColor("#FFFFFF")
        else:
            p.setBrush(alpha(Th.c("card"), Th.alpha("card_a")))
            p.setPen(alpha(Th.c("rose"), 130))
            p.drawRoundedRect(r, 20, 20)
            col = Th.c("rose")
        draw_text(p, self.rect(), self.text, font(10, QFont.DemiBold), col,
                  Qt.AlignHCenter)


# ---------------------------------------------------------------------------
#  Language cards + swap
# ---------------------------------------------------------------------------
class LangCard(Hover):
    def __init__(self, badge, name, sub, parent=None):
        super().__init__(parent)
        self.badge, self.name, self.sub = badge, name, sub
        self.setFixedHeight(74)

    def set_lang(self, badge, name, sub):
        self.badge, self.name, self.sub = badge, name, sub
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(alpha(Th.c("edge"), Th.alpha("edge_a") * (0.6 + 0.4 * self.hv)))
        p.setBrush(alpha(Th.c("card"), Th.alpha("card_a") * (0.6 + 0.4 * self.hv)))
        p.drawRoundedRect(r, 18, 18)
        g = QLinearGradient(QPointF(14, 12), QPointF(52, 54))
        g.setColorAt(0, Th.c("indigo"))
        g.setColorAt(1, Th.c("indigo2"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(12, 19, 36, 36), 11, 11)
        draw_text(p, QRectF(12, 23, 36, 28), self.badge,
                  font(10.5, QFont.Bold), "#FFFFFF", Qt.AlignHCenter)
        draw_text(p, QRectF(60, 15, 250, 24), self.name,
                  font(13.5, QFont.DemiBold), Th.c("text"))
        draw_text(p, QRectF(60, 41, 250, 16), self.sub,
                  font(8.5), Th.c("muted"))
        draw_icon(p, "chevron", QRectF(self.width() - 30, 27, 18, 18),
                  Th.c("muted"), 1.9)


class SwapButton(Hover):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self._rot = 360.0
        self._ra = QVariantAnimation(self, duration=340,
                                     easingCurve=QEasingCurve.OutBack)
        self._ra.valueChanged.connect(lambda v: (setattr(self, "_rot", v),
                                                 self.update()))

    def spin(self):
        self._ra.stop()
        self._ra.setStartValue(self._rot)
        self._ra.setEndValue(self._rot + 180)
        self._ra.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, 34, 34)
        if self.hv > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(Th.c("indigo"), 46 + 30 * self.hv))
            p.drawEllipse(r)
        p.save()
        p.translate(20, 20)
        p.rotate(self._rot - 360)
        p.translate(-20, -20)
        draw_icon(p, "swap", QRectF(9, 9, 22, 22), Th.c("indigo"), 1.9)
        p.restore()


# ---------------------------------------------------------------------------
#  Snip hero + recent chips
# ---------------------------------------------------------------------------
class SnipButton(Hover):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(92)
        self.running = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        lift = -1.5 * self.hv
        r = r.translated(0, lift)
        glow = QRadialGradient(r.center(), r.width() * 0.62)
        glow.setColorAt(0, alpha(Th.c("indigo"), 90))
        glow.setColorAt(1, alpha(Th.c("indigo"), 0))
        p.setBrush(glow)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r.adjusted(-8, -6, 8, 10), 26, 26)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, Th.c("indigo"))
        g.setColorAt(1, Th.c("indigo2"))
        p.setBrush(g)
        p.setPen(alpha("#FFFFFF", 60))
        p.drawRoundedRect(r, 24, 24)
        p.setPen(Qt.NoPen)
        p.setBrush(alpha("#FFFFFF", 26))
        p.drawRoundedRect(QRectF(22, 23, 46, 46), 14, 14)
        draw_icon(p, "snap", QRectF(33, 34, 24, 24), "#FFFFFF", 2.0)
        draw_text(p, QRectF(80, 18, r.width() - 100, 30), "Snip & Translate",
                  font(16.5, QFont.Bold, tracking=0.2), "#FFFFFF")
        draw_text(p, QRectF(80, 51, r.width() - 100, 18),
                  "Drag a region · press Alt+Shift+M", font(9.5),
                  alpha("#FFFFFF", 200))


class RecentChip(Hover):
    def __init__(self, a, b, parent=None):
        super().__init__(parent)
        self.a, self.b = a, b
        self.pair = (a, b)   # (from_short, to_short)
        self.active = False
        self.setFixedHeight(30)

    def set_active(self, s):
        self.active = s
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setPen(alpha(Th.c("indigo") if self.active else Th.c("edge"),
                       max(40, int(Th.alpha("edge_a") * (0.5 + 0.5 * self.hv)))))
        p.setBrush(alpha(Th.c("indigo") if self.active else Th.c("card"),
                         (70 if self.active else Th.alpha("card_a"))))
        p.drawRoundedRect(QRectF(self.rect()), 15, 15)
        col = Th.c("indigo") if self.active else Th.c("soft")
        draw_text(p, self.rect(), f"{self.a}  →  {self.b}",
                  font(9.5, QFont.DemiBold), col, Qt.AlignHCenter)


# ---------------------------------------------------------------------------
#  Simulated pipeline: MiniScreen + StageRow
# ---------------------------------------------------------------------------
SRC_LINES = ["Nearby cafés in Old Town", "Open until 11 PM · 4.8 ★",
             "The quick brown fox jumps over the lazy dog"]
BN_LINES = ["কাছের পুরনো শহরের ক্যাফে", "রাত ১১টা পর্যন্ত খোলা",
            "দ্রুত বাদামি শিয়াল অলস কুকুরের উপর লাফ দেয়"]


class MiniScreen(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.prog = 0.0
        self.setFixedSize(430, 196)

    def set_prog(self, v):
        self.prog = v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#151B38"))
        g.setColorAt(1, QColor("#0B1026"))
        p.setBrush(g)
        p.setPen(alpha("#FFFFFF", 26))
        p.drawRoundedRect(r, 18, 18)
        # fake browser chrome
        p.setBrush(alpha("#FFFFFF", 16))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(r.left() + 16, 14, 110, 14), 7, 7)
        for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            p.setBrush(QColor(c))
            p.drawEllipse(QPointF(r.left() + 34 + i * 18, 21), 3.6, 3.6)
        box = QRectF(r.left() + 24, 52, r.width() - 48, r.height() - 72)
        if self.prog <= 0.0:
            pen = QPen(alpha("#FFFFFF", 60), 1.2, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box, 12, 12)
            draw_text(p, box, "Snip a region to translate in place",
                      font(9.5, QFont.DemiBold), alpha("#FFFFFF", 150),
                      Qt.AlignHCenter | Qt.AlignVCenter)
        else:
            n = len(SRC_LINES)
            show_boxes = self.prog < 0.66
            show_bn = self.prog >= 0.66
            for i in range(n):
                y = 56 + i * 46
                if show_boxes:
                    a = max(0.0, min(1.0, (self.prog - i * 0.10) * 8))
                    c = Th.c("indigo") if self.prog < 0.33 else Th.c("green")
                    rw = 250 - (i * 42)
                    p.setPen(QPen(alpha(c, 160 * a), 1.4))
                    p.setBrush(alpha(c, 34 * a))
                    p.drawRoundedRect(QRectF(box.left(), y, rw, 22), 6, 6)
                if show_bn:
                    p.setPen(Qt.NoPen)
                    p.setBrush(alpha(QColor(self.state.fill), self.state.op * 1.6))
                    p.drawRoundedRect(QRectF(box.left(), y, 270, 24), 6, 6)
                    fm = QFontMetrics(font(9, fam=BN_FAMS))
                    el = fm.elidedText(BN_LINES[i], Qt.ElideRight, 246)
                    draw_text(p, QRectF(box.left() + 12, y, 246, 24), el,
                              font(9, fam=BN_FAMS), "#FFFFFF", Qt.AlignVCenter)
            if show_bn:
                p.setBrush(alpha(Th.c("green"), 110))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(box.right() - 80, 40, 64, 20), 10, 10)
                draw_icon(p, "check", QRectF(box.right() - 74, 45, 12, 12),
                          "#FFFFFF", 2.2)
                draw_text(p, QRectF(box.right() - 60, 40, 42, 20), "Done",
                          font(8.5, QFont.Bold), "#FFFFFF", Qt.AlignVCenter)


class StageRow(QWidget):
    STAGES = ["Capture", "Detect", "OCR", "Translate", "Overlay"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.prog = 0.0
        self.setFixedHeight(150)

    def set_prog(self, v):
        self.prog = v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(alpha(Th.c("edge"), Th.alpha("edge_a") * 0.6))
        p.setBrush(alpha(Th.c("card"), Th.alpha("card_a") * 0.7))
        p.drawRoundedRect(r, 18, 18)
        draw_text(p, QRectF(16, 10, 200, 18), "Pipeline", font(9, QFont.DemiBold),
                  Th.c("muted"))
        p.setPen(alpha(Th.c("edge"), 40))
        p.drawLine(QPointF(16, 33), QPointF(r.right() - 16, 33))
        n = len(self.STAGES)
        for i, name in enumerate(self.STAGES):
            frac = self.prog * n - i
            done = frac >= 1.0
            active = 0.0 < frac < 1.0
            y = 36 + i * 21
            cx = 30
            if done:
                p.setPen(Qt.NoPen)
                p.setBrush(alpha(Th.c("green"), 200))
                p.drawEllipse(QPointF(cx, y), 5, 5)
                draw_icon(p, "check", QRectF(cx - 4, y - 4, 8, 8), "#FFFFFF", 2.4)
            elif active:
                p.setPen(Qt.NoPen)
                p.setBrush(alpha(Th.c("indigo"), 230))
                p.drawEllipse(QPointF(cx, y), 5, 5)
            else:
                p.setPen(alpha(Th.c("edge"), 90))
                p.setBrush(alpha(Th.c("card"), 30))
                p.drawEllipse(QPointF(cx, y), 5, 5)
            draw_text(p, QRectF(44, y - 9, 120, 18), name,
                      font(9.5, QFont.DemiBold),
                      Th.c("text") if active or done else Th.c("muted"))
            if i > 0:
                p.setPen(alpha(Th.c("edge"), 60))
                p.drawLine(QPointF(cx, y - 16), QPointF(cx, y - 6))


# ---------------------------------------------------------------------------
#  Settings controls
# ---------------------------------------------------------------------------
class ColorRow(QWidget):
    colorChanged = pyqtSignal(str)
    PRESETS = ["#6366F1", "#22D3EE", "#34D399", "#FBBF24", "#FB7185"]

    def __init__(self, label, current, parent=None):
        super().__init__(parent)
        self.label = label
        self.current = current
        self.setFixedHeight(44)

    def set_color(self, c):
        self.current = c
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        draw_text(p, QRectF(12, 0, 150, 44), self.label,
                  font(9.5, QFont.DemiBold), Th.c("soft"))
        x = self.width() - 190
        for c in self.PRESETS:
            r = QRectF(x, 8, 28, 28)
            p.setPen(alpha("#FFFFFF" if Th.alpha("card_a") < 128 else "#0B1020", 60))
            col = QColor(c)
            if self.current.lower() == c.lower():
                col = col.lighter(118)
            p.setBrush(col)
            p.drawEllipse(r)
            if self.current.lower() == c.lower():
                p.setPen(QPen(Th.c("text"), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(r.adjusted(-3, -3, 3, 3))
            x += 40

    def mousePressEvent(self, e):
        x = e.pos().x()
        i = int((x - (self.width() - 190)) / 40.0)
        if 0 <= i < len(self.PRESETS):
            self.current = self.PRESETS[i]
            self.colorChanged.emit(self.current)
            self.update()


class SliderRow(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, label, lo, hi, val, suffix, parent=None):
        super().__init__(parent)
        self.label, self.lo, self.hi, self.val, self.suffix = label, lo, hi, val, suffix
        self.setFixedHeight(42)
        self.setCursor(Qt.PointingHandCursor)

    def set_val(self, v):
        self.val = v
        self.update()

    def mousePressEvent(self, e):
        self.val = self._from_x(e.pos().x())
        self.valueChanged.emit(self.val)
        self.update()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.val = self._from_x(e.pos().x())
            self.valueChanged.emit(self.val)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        draw_text(p, QRectF(12, 0, 120, 42), self.label,
                  font(9.5, QFont.DemiBold), Th.c("soft"))
        vw = 64
        track = QRectF(130, 18, self.width() - 130 - vw - 12, 6)
        p.setBrush(alpha(Th.c("card"), 40))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(track, 3, 3)
        fr = self.hi - self.lo or 1
        fill = QRectF(track.left(), track.top(),
                      track.width() * (self.val - self.lo) / fr, track.height())
        p.setBrush(Th.c("indigo"))
        p.drawRoundedRect(fill, 3, 3)
        kx = fill.right() if fill.width() > 2 else track.left()
        p.setBrush(Th.c("text"))
        p.drawEllipse(QPointF(kx, 21), 7, 7)
        p.setBrush(Th.c("indigo"))
        p.drawEllipse(QPointF(kx, 21), 4, 4)
        draw_text(p, QRectF(self.width() - vw, 0, vw - 12, 42),
                  f"{self.val}{self.suffix}", font(9.5, QFont.DemiBold),
                  Th.c("text"), Qt.AlignRight)

    def _from_x(self, x):
        vw = 64
        left = 130.0
        span = self.width() - 130.0 - vw - 12
        t = (x - left) / span if span > 0 else 0.0
        return self.lo + int(round(max(0.0, min(1.0, t)) * (self.hi - self.lo)))


class SnipPreview(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setFixedHeight(150)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#151B38"))
        g.setColorAt(1, QColor("#0B1026"))
        p.setBrush(g)
        p.setPen(alpha("#FFFFFF", 26))
        p.drawRoundedRect(r, 18, 18)
        p.setBrush(alpha("#FFFFFF", 14))
        p.setPen(Qt.NoPen)
        for i in range(1, 4):
            p.drawRoundedRect(QRectF(r.left() + 20, r.top() + 16 + i * 30,
                                     r.width() - 40 - i * 40, 16), 8, 8)
        # selection box
        sel = QRectF(r.left() + 26, r.top() + 22, 240, 96)
        fill = QColor(self.state.fill)
        fill.setAlpha(int(self.state.op * 1.7))
        p.setBrush(fill)
        p.setPen(QPen(QColor(self.state.fill), self.state.bw))
        p.drawRoundedRect(sel, 10, 10)
        draw_text(p, sel.adjusted(8, 4, -8, -4), BN_LINES[1],
                  font(self.state.fs + 2, fam=BN_FAMS), "#FFFFFF",
                  Qt.AlignVCenter)


# ---------------------------------------------------------------------------
#  History rows
# ---------------------------------------------------------------------------
class HistoryRow(Hover):
    def __init__(self, a, b, meta, parent=None):
        super().__init__(parent)
        self.a, self.b, self.meta = a, b, meta
        self.pair = (a, b)
        self.setFixedHeight(54)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(alpha(Th.c("edge"), int(Th.alpha("edge_a") * (0.35 + 0.6 * self.hv))))
        p.setBrush(alpha(Th.c("card"), Th.alpha("card_a") * (0.35 + 0.6 * self.hv)))
        p.drawRoundedRect(r, 14, 14)
        g = QLinearGradient(QPointF(16, 10), QPointF(52, 44))
        g.setColorAt(0, Th.c("indigo"))
        g.setColorAt(1, Th.c("indigo2"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(14, 10, 34, 34), 10, 10)
        draw_text(p, QRectF(14, 13, 34, 28), self.a, font(9, QFont.Bold), "#FFFFFF",
                  Qt.AlignHCenter)
        draw_icon(p, "swap", QRectF(54, 17, 20, 20), Th.c("muted"), 1.6)
        g = QLinearGradient(QPointF(80, 10), QPointF(116, 44))
        g.setColorAt(0, Th.c("cyan"))
        g.setColorAt(1, Th.c("fuchsia"))
        p.setBrush(g)
        p.drawRoundedRect(QRectF(80, 10, 34, 34), 10, 10)
        draw_text(p, QRectF(80, 13, 34, 28), self.b, font(9, QFont.Bold), "#FFFFFF",
                  Qt.AlignHCenter)
        draw_text(p, QRectF(126, 8, 220, 20), f"{self.a} → {self.b}",
                  font(10.5, QFont.DemiBold), Th.c("text"))
        draw_text(p, QRectF(126, 29, 220, 16), self.meta, font(8.5), Th.c("muted"))
        draw_icon(p, "chev_r", QRectF(self.width() - 30, 18, 16, 16),
                  Th.c("muted"), 1.8)


# ---------------------------------------------------------------------------
#  Toast
# ---------------------------------------------------------------------------
class Toast(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.t = 0.0
        self.setFixedHeight(40)

    def show_text(self, text):
        self.text = text
        self._anim(1.0)
        QTimer.singleShot(2000, lambda: self._anim(0.0))

    def _anim(self, to):
        a = QVariantAnimation(self, duration=240, easingCurve=QEasingCurve.OutCubic)
        a.setStartValue(self.t)
        a.setEndValue(to)
        a.valueChanged.connect(lambda v: (setattr(self, "t", v), self.update()))
        a.start()
        self._a = a

    def paintEvent(self, e):
        if not self.text or self.t <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        f = font(9.5, QFont.DemiBold)
        w = int(QFontMetrics(f).horizontalAdvance(self.text)) + 44
        a = self.t
        r = QRectF((self.width() - w) / 2, 6 - 14 * (1 - a), w, 34)
        p.setPen(Qt.NoPen)
        p.setBrush(alpha("#10162E", 235 * a))
        p.drawRoundedRect(r, 17, 17)
        p.setPen(alpha("#FFFFFF", 40 * a))
        p.setBrush(alpha(Th.c("green"), 200 * a))
        p.drawEllipse(QPointF(r.left() + 16, r.center().y()), 4, 4)
        draw_text(p, r.adjusted(26, 0, -8, 0), self.text, f,
                  alpha("#FFFFFF", 240 * a), Qt.AlignVCenter | Qt.AlignLeft)


# ---------------------------------------------------------------------------
#  Pages
# ---------------------------------------------------------------------------
class HomePage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.win = shell
        s = shell.state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(0)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(Wordmark())
        bar.addStretch(1)
        self.pill = EnginePill()
        bar.addWidget(self.pill)
        bar.addSpacing(6)
        self.btn_min = IconButton("minus")
        self.btn_close = IconButton("close", danger=True)
        bar.addWidget(self.btn_min)
        bar.addWidget(self.btn_close)
        lay.addLayout(bar)
        lay.addSpacing(14)

        body = QHBoxLayout()
        body.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(0)
        self.src = LangCard(FROM_SHORT[s.src], FROM_LANGS[s.src][0], "Source · OCR model")
        left.addWidget(self.src)
        sw = QHBoxLayout()
        sw.addStretch(1)
        self.swap = SwapButton()
        sw.addWidget(self.swap)
        sw.addStretch(1)
        sw.setContentsMargins(0, 5, 0, 5)
        left.addLayout(sw)
        self.dst = LangCard(TO_SHORT[s.dst], TO_LANGS[s.dst][0],
                            "Translate to · online engine")
        left.addWidget(self.dst)
        left.addSpacing(12)
        self.snip = SnipButton()
        left.addWidget(self.snip)
        left.addSpacing(12)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chip_wrap = QWidget()
        self.chip_wrap.setLayout(chips)
        left.addWidget(self.chip_wrap)
        left.addStretch(1)
        body.addLayout(left, 1)
        right = QVBoxLayout()
        right.setSpacing(12)
        self.mini = MiniScreen(s)
        right.addWidget(self.mini)
        self.stages = StageRow()
        right.addWidget(self.stages)
        right.addStretch(1)
        body.addLayout(right, 0)
        lay.addLayout(body, 1)

        self.src.clicked.connect(self._cycle_src)
        self.dst.clicked.connect(self._cycle_dst)
        self.swap.clicked.connect(self._do_swap)
        self.snip.clicked.connect(self.win.run_pipeline)
        self.chips = []
        self._refresh_chips()
        self.pipe = QVariantAnimation(self, duration=3000, startValue=0.0, endValue=1.0)
        self.pipe.valueChanged.connect(self._on_pipe)
        self.pipe.finished.connect(self._on_pipe_done)

    def _cycle_src(self):
        s = self.win.state
        s.src = (s.src + 1) % len(FROM_LANGS)
        self.src.set_lang(FROM_SHORT[s.src], FROM_LANGS[s.src][0], "Source · OCR model")
        print(f"source: {FROM_LANGS[s.src][0]}", flush=True)
        self._refresh_chips()

    def _cycle_dst(self):
        s = self.win.state
        s.dst = (s.dst + 1) % len(TO_LANGS)
        self.dst.set_lang(TO_SHORT[s.dst], TO_LANGS[s.dst][0], "Translate to · online engine")
        print(f"dest: {TO_LANGS[s.dst][0]}", flush=True)
        self._refresh_chips()

    def _base(self, name):
        return name.split("(")[0].strip().lower()

    def _do_swap(self):
        s = self.win.state
        fname, tname = FROM_LANGS[s.src][0], TO_LANGS[s.dst][0]
        if self._base(fname) not in {self._base(n) for n, _ in TO_LANGS} or \
           self._base(tname) not in {self._base(n) for n, _ in FROM_LANGS}:
            self.win.toast.show_text(f"No OCR model for '{tname}' — can't swap")
            print("swap blocked", flush=True)
            return
        self.swap.spin()
        s.dst = next(i for i, (n, _) in enumerate(TO_LANGS)
                     if self._base(n) == self._base(fname))
        s.src = next(i for i, (n, _) in enumerate(FROM_LANGS)
                     if self._base(n) == self._base(tname))
        self.src.set_lang(FROM_SHORT[s.src], FROM_LANGS[s.src][0], "Source · OCR model")
        self.dst.set_lang(TO_SHORT[s.dst], TO_LANGS[s.dst][0], "Translate to · online engine")
        print(f"swapped: {FROM_LANGS[s.src][0]} -> {TO_LANGS[s.dst][0]}", flush=True)
        self._refresh_chips()

    def _refresh_chips(self):
        s = self.win.state
        lay = self.chip_wrap.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.chips = []
        for fi, ti in s.recents:
            chip = RecentChip(FROM_SHORT[fi], TO_SHORT[ti])
            chip.active = (fi == s.src and ti == s.dst)
            chip.pair = (fi, ti)
            chip.clicked.connect(self._apply_chip)
            lay.addWidget(chip)
            self.chips.append(chip)
        lay.addStretch(1)
        self.chip_wrap.setVisible(bool(s.recents))

    def _apply_chip(self):
        chip = self.sender()
        s = self.win.state
        s.src, s.dst = chip.pair
        self.src.set_lang(FROM_SHORT[s.src], FROM_LANGS[s.src][0], "Source · OCR model")
        self.dst.set_lang(TO_SHORT[s.dst], TO_LANGS[s.dst][0], "Translate to · online engine")
        self._refresh_chips()
        self.win.toast.show_text(f"Pair applied: {FROM_LANGS[s.src][0]} → {TO_LANGS[s.dst][0]}")

    def _on_pipe(self, v):
        self.mini.set_prog(v)
        self.stages.set_prog(v)

    def _on_pipe_done(self):
        self.pill.set_state("ready")
        s = self.win.state
        s.recents = [(s.src, s.dst)] + [r for r in s.recents if r != (s.src, s.dst)]
        s.recents = s.recents[:3]
        self._refresh_chips()
        self.win.toast.show_text(f"Translated 3 lines · {TO_LANGS[s.dst][0]}")
        print("pipeline done", flush=True)


class HistoryPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.win = shell
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(TitleLabel("History", 15, QFont.Bold, "text"))
        header.addStretch(1)
        lay.addLayout(header)
        self.rows = []
        for a, b, meta in (("EN", "BN", "Today 12:40 · 7 words · 310 ms"),
                           ("BN", "EN", "Today 11:02 · 23 words · 890 ms"),
                           ("EN", "RU", "Yesterday · 5 words · 264 ms")):
            row = HistoryRow(a, b, meta)
            row.clicked.connect(self._apply)
            lay.addWidget(row)
            self.rows.append(row)
        lay.addStretch(1)

    def _apply(self):
        row = self.sender()
        s = self.win.state
        s.src = FROM_SHORT.index(row.a)
        s.dst = TO_SHORT.index(row.b)
        self.win.main.src.set_lang(FROM_SHORT[s.src], FROM_LANGS[s.src][0], "Source · OCR model")
        self.win.main.dst.set_lang(TO_SHORT[s.dst], TO_LANGS[s.dst][0], "Translate to · online engine")
        self.win.main._refresh_chips()
        self.win.goto(0)
        self.win.toast.show_text(f"Loaded: {row.a} → {row.b}")
        print(f"history apply: {row.a} -> {row.b}", flush=True)


class SettingsPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.win = shell
        self.vals = shell.state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(10)
        self.btn_back = IconButton("back", 34)
        head.addWidget(self.btn_back)
        head.addWidget(TitleLabel("Settings", 15, QFont.Bold, "text", h=34))
        head.addStretch(1)
        lay.addLayout(head)

        self.preview = SnipPreview(self.vals)
        lay.addWidget(self.preview)

        card = QWidget()
        card.setAttribute(Qt.WA_TranslucentBackground)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(2)
        v.addWidget(TitleLabel("Capture box · overlay style", 9.5, QFont.DemiBold,
                               "soft", h=18))
        self.r_fill = ColorRow("Selection fill", self.vals.fill)
        self.r_op = SliderRow("Selection opacity", 0, 100, self.vals.op, " %")
        self.r_bw = SliderRow("Border width", 1, 10, self.vals.bw, " px")
        self.r_fs = SliderRow("Font size", 6, 24, self.vals.fs, " px")
        for w in (self.r_fill, self.r_op, self.r_bw, self.r_fs):
            v.addWidget(w)
        lay.addWidget(card, 1)
        lay.addStretch(1)
        foot = QHBoxLayout()
        self.btn_reset = PillButton("Reset defaults", "ghost", 132)
        self.btn_done = PillButton("Done", "primary", 120)
        foot.addWidget(self.btn_reset)
        foot.addStretch(1)
        foot.addWidget(self.btn_done)
        lay.addLayout(foot)

        self.r_fill.colorChanged.connect(lambda c: (setattr(self.vals, "fill", c),
                                                    self.preview.update(),
                                                    print("fill", c, flush=True)))
        self.r_op.valueChanged.connect(lambda v: (setattr(self.vals, "op", v),
                                                  self.preview.update()))
        self.r_bw.valueChanged.connect(lambda v: (setattr(self.vals, "bw", v),
                                                  self.preview.update()))
        self.r_fs.valueChanged.connect(lambda v: (setattr(self.vals, "fs", v),
                                                  self.preview.update()))
        self.btn_back.clicked.connect(lambda: self.win.goto(0))
        self.btn_reset.clicked.connect(self.reset)
        self.btn_done.clicked.connect(lambda: self.win.goto(0))

    def set_fill(self, c):
        self.r_fill.set_color(c)
        self.vals.fill = c
        self.preview.update()

    def set_op(self, v):
        self.r_op.set_val(v)
        self.vals.op = v
        self.preview.update()

    def set_bw(self, v):
        self.r_bw.set_val(v)
        self.vals.bw = v
        self.preview.update()

    def reset(self):
        self.set_fill("#6366F1")
        self.set_op(42)
        self.set_bw(2)
        self.set_fs(7)
        self.win.toast.show_text("Defaults restored")
        print("reset defaults", flush=True)

    def set_fs(self, v):
        self.r_fs.set_val(v)
        self.vals.fs = v
        self.preview.update()


# ---------------------------------------------------------------------------
#  Shell — frameless studio window with left rail + stacked pages
# ---------------------------------------------------------------------------
class Shell(QWidget):
    def __init__(self, settings_path):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.state = MockState(settings_path)
        self.theme_name = self.state.theme if self.state.theme in THEME_ORDER else "aurora"
        Th.a = PAL[self.theme_name]
        Th.b = PAL[self.theme_name]
        Th.t = 1.0
        self.setFixedSize(940, 600)
        self._drag_off = None
        self._phase = 0.0
        self._theme_anim = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        rail = QVBoxLayout()
        rail.setContentsMargins(8, 14, 8, 14)
        rail.setSpacing(4)
        rail.addWidget(LensMark(40), 0, Qt.AlignHCenter)
        rail.addSpacing(14)
        self.rail_btns = []
        for icon, label, idx in (("home", "Home", 0), ("history", "History", 1),
                                 ("gear", "Settings", 2)):
            b = RailButton(icon, label)
            b.clicked.connect(lambda i=idx: self.goto(i))
            rail.addWidget(b, 0, Qt.AlignHCenter)
            self.rail_btns.append(b)
        rail.addStretch(1)
        self.rail_theme = RailButton("sun", "Theme")
        self.rail_theme.clicked.connect(self._cycle_theme)
        rail.addWidget(self.rail_theme, 0, Qt.AlignHCenter)
        root.addLayout(rail)

        self.stack = QStackedWidget()
        self.stack.setAttribute(Qt.WA_TranslucentBackground)
        self.main = HomePage(self)
        self.history = HistoryPage(self)
        self.settings = SettingsPage(self)
        self.stack.addWidget(self.main)
        self.stack.addWidget(self.history)
        self.stack.addWidget(self.settings)
        root.addWidget(self.stack, 1)

        self.toast = Toast(self)
        self.toast.setGeometry(0, self.height() - 56, self.width(), 40)
        self._select_rail(0)
        self._fb = QTimer(self)
        self._fb.timeout.connect(self._tick)
        self._fb.start(33)
        QShortcut(QKeySequence("Alt+Shift+M"), self, activated=self.run_pipeline)

    # ------------------------------------------------------------ motion
    def _tick(self):
        self._phase += 0.014
        self.update()

    def _cycle_theme(self):
        nxt = THEME_ORDER[(THEME_ORDER.index(self.theme_name) + 1) % len(THEME_ORDER)]
        self.set_theme(nxt)

    def set_theme(self, name):
        if name not in THEME_ORDER or name == self.theme_name:
            return
        a = QVariantAnimation(self, duration=420, startValue=0.0, endValue=1.0)
        a.setEasingCurve(QEasingCurve.InOutCubic)
        Th.a = {k: (QColor(v) if isinstance(v, str) else v) for k, v in Th.a.items()}
        Th.b = PAL[name]
        Th.t = 0.0

        def on(v):
            Th.t = v
            self.update()
            for w in self.findChildren(QWidget):
                w.update()

        a.valueChanged.connect(on)
        a.start()
        self._theme_anim = a
        self.theme_name = name
        self.state.theme = name
        self.rail_theme.icon = "moon" if name == "day" else "sun"
        self.rail_theme.update()
        print(f"theme: {name}", flush=True)

    # ------------------------------------------------------------ pages
    def _select_rail(self, idx):
        for i, b in enumerate(self.rail_btns):
            b.select(i == idx)

    def goto(self, idx):
        if idx == self.stack.currentIndex():
            return
        self.stack.setCurrentIndex(idx)
        self._select_rail(idx)
        self._hug = None  # placeholder to keep attr parity
        print(f"page: {idx}", flush=True)

    # ------------------------------------------------------------ pipeline
    def run_pipeline(self):
        if self.main.pipe.state() == 2:  # Running
            return
        self.main.pill.set_state("busy")
        self.main.pipe.start()
        print("pipeline start", flush=True)

    # ------------------------------------------------------------ shell paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                        | QPainter.TextAntialiasing)
        body = QRectF(self.rect())
        g = QLinearGradient(body.topLeft(), body.bottomRight())
        g.setColorAt(0, Th.c("bg1"))
        g.setColorAt(1, Th.c("bg2"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(body, 26, 26)
        # drifting aurora blobs
        ph = self._phase
        w, h = body.width(), body.height()
        for key, cx, cy, rx, ry in (
                ("indigo", 0.16, 0.30, 300, 260),
                ("cyan", 0.86, 0.22, 250, 220),
                ("fuchsia", 0.70, 0.85, 280, 240)):
            x = cx * w + rx * 0.35 * math.sin(ph * (0.9 + 0.2 * rx / 250))
            y = cy * h + ry * 0.30 * math.cos(ph * (0.7 + 0.2 * ry / 250))
            rad = QRadialGradient(QPointF(x, y), rx)
            rad.setColorAt(0, alpha(Th.c(key), Th.alpha("blob_a")))
            rad.setColorAt(1, alpha(Th.c(key), 0))
            p.setBrush(rad)
            p.drawEllipse(QPointF(x, y), rx, ry)
        # rail divider
        p.setPen(alpha(Th.c("edge"), Th.alpha("edge_a") * 0.5))
        p.drawLine(QPointF(64, 18), QPointF(64, h - 18))
        # window edge
        p.setPen(alpha(Th.c("edge"), Th.alpha("edge_a")))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), 26, 26)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_off = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_off is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag_off)

    def mouseReleaseEvent(self, e):
        self._drag_off = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.stack.currentIndex() != 0:
            self.goto(0)
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.toast.setGeometry(0, self.height() - 56, self.width(), 40)


# ---------------------------------------------------------------------------
#  Entry
# ---------------------------------------------------------------------------
def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = Shell(os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json"))
    win.show()
    if "--shot" in sys.argv:
        from PyQt5.QtGui import QGuiApplication
        i = sys.argv.index("--shot")
        path = sys.argv[i + 1] if i + 1 < len(sys.argv) else "shot.png"
        for _ in range(4):
            app.processEvents()
        QGuiApplication.primaryScreen().grabWindow(win.winId()).save(path)
        print("shot:", path, flush=True)
        os._exit(0)
    app.exec_()


if __name__ == "__main__":
    main()