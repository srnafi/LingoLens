"""Custom-painted Control Center widgets (theme-aware via ``ui.theme``).

All widgets read colour through ``ui.theme.Th`` at paint time so a
theme change repaints the window with a single animation.
"""

import math
import time

from PyQt5.QtCore import (QEasingCurve, QPoint, QPointF,
                          QParallelAnimationGroup, QPropertyAnimation, QRectF,
                          QSize, Qt, QTimer, QVariantAnimation,
                          pyqtSignal)
from PyQt5.QtGui import (QBrush, QColor, QConicalGradient, QFont, QFontMetrics,
                         QLinearGradient, QPainter, QPainterPath, QPen,
                         QPolygonF, QRadialGradient)
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QColorDialog,
                             QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                             QListWidget, QListWidgetItem, QStyle,
                             QStyledItemDelegate, QVBoxLayout, QWidget)

from ui.theme import (PALETTES, THEME_LABELS, THEME_ORDER, Th, alpha,
                      app_font, css, draw_text, lerp, mix, rounded)


# ==========================================================================
#  Animation + base widget
# ==========================================================================
class Tween(QVariantAnimation):
    def __init__(self, owner, value=0.0, ms=180, curve=QEasingCurve.OutCubic):
        super().__init__(owner)
        self.owner = owner
        self.val = float(value)
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


class HoverWidget(QWidget):
    """Clickable widget with hover/press micro-animation. Honors disabled."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.hover = Tween(self, 0, 160)
        self.press = Tween(self, 0, 90)

    def enterEvent(self, e):
        if self.isEnabled():
            self.hover.go(1)

    def leaveEvent(self, e):
        self.hover.go(0)
        self.press.go(0)

    def mousePressEvent(self, e):
        if not self.isEnabled():
            e.ignore()
            return
        if e.button() == Qt.LeftButton:
            self.press.go(1)
            e.accept()
        else:
            e.ignore()

    def mouseReleaseEvent(self, e):
        if not self.isEnabled():
            return
        if e.button() == Qt.LeftButton:
            self.press.go(0)
            if self.rect().contains(e.pos()):
                self.clicked.emit()


def draw_icon(p, name, rect, color, width=1.9):
    """Vector icons on a 24x24 grid -> crisp at any DPI."""
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

    if name == "close":
        L(6, 6, 18, 18); L(18, 6, 6, 18)
    elif name == "minimize":
        L(6, 12, 18, 12)
    elif name == "back":
        poly((14.5, 6), (8.5, 12), (14.5, 18))
    elif name == "chevron":
        poly((7, 9.5), (12, 14.5), (17, 9.5))
    elif name == "check":
        poly((5, 12.5), (10, 17.5), (19, 7))
    elif name == "swap":
        L(4, 8, 20, 8); poly((16, 4), (20, 8), (16, 12))
        L(4, 16, 20, 16); poly((8, 12), (4, 16), (8, 20))
    elif name == "camera":
        p.drawRoundedRect(QRectF(3, 7, 18, 13), 3.5, 3.5)
        path = QPainterPath()
        path.moveTo(8, 7); path.lineTo(9.6, 4.5); path.lineTo(14.4, 4.5); path.lineTo(16, 7)
        p.drawPath(path)
        p.drawEllipse(QPointF(12, 13.5), 3.4, 3.4)
    elif name == "gear":
        path = QPainterPath()
        n = 32
        for i in range(n):
            a = 2 * math.pi * (i - 0.5) / n
            r = 9.4 if i % 4 in (1, 2) else 7.2
            pt = QPointF(12 + r * math.cos(a), 12 + r * math.sin(a))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        path.closeSubpath()
        p.drawPath(path)
        p.drawEllipse(QPointF(12, 12), 3.1, 3.1)
    elif name == "region":
        pen = p.pen(); pen.setStyle(Qt.DashLine); p.setPen(pen)
        p.drawRoundedRect(QRectF(4, 5, 16, 14), 3, 3)
    elif name == "window":
        p.drawRoundedRect(QRectF(4, 5, 16, 14), 3, 3)
        L(4, 9.5, 20, 9.5)
    elif name == "monitor":
        p.drawRoundedRect(QRectF(3, 5, 18, 12), 2.5, 2.5)
        L(9, 20, 15, 20); L(12, 17, 12, 20)
    elif name == "sun":
        p.drawEllipse(QPointF(12, 12), 4, 4)
        for a in range(0, 360, 45):
            r = math.radians(a)
            L(12 + 6.6 * math.cos(r), 12 + 6.6 * math.sin(r),
              12 + 9 * math.cos(r), 12 + 9 * math.sin(r))
    elif name == "moon":
        outer = QPainterPath(); outer.addEllipse(QPointF(12, 12), 7.6, 7.6)
        inner = QPainterPath(); inner.addEllipse(QPointF(15.6, 9.4), 6.6, 6.6)
        p.setBrush(QColor(color)); p.setPen(Qt.NoPen)
        p.drawPath(outer.subtracted(inner))
    p.restore()


# ==========================================================================
#  Themed label (recoloured on theme morph)
# ==========================================================================
from PyQt5.QtWidgets import QLabel as _QLabel  # noqa: E402  (ui.theme, not ui/__init__: dpi ordering unaffected)


class ThemeLabel(_QLabel):
    def __init__(self, text, key="soft", pt=9.5, weight=QFont.Normal, wrap=False):
        super().__init__(text)
        self._theme_key = key
        self.setFont(app_font(pt, weight))
        self.setWordWrap(wrap)
        self.setStyleSheet(f"color:{css(Th.c(key))}; background:transparent;")
        self.setAttribute(Qt.WA_TranslucentBackground)

    def refresh(self):
        self.setStyleSheet(f"color:{css(Th.c(self._theme_key))}; background:transparent;")


def make_label(text, pt=9.5, weight=QFont.Normal, key="soft", wrap=False):
    return ThemeLabel(text, key, pt, weight, wrap)


# ==========================================================================
#  Small parts
# ==========================================================================
class IconButton(HoverWidget):
    def __init__(self, icon, size=34, danger=False, tip=""):
        super().__init__()
        self.icon, self.danger = icon, danger
        self.setFixedSize(size, size)
        if tip:
            self.setToolTip(tip)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        h, pr = self.hover.val, self.press.val
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = 1 - 0.08 * pr
        p.translate(r.center()); p.scale(s, s); p.translate(-r.center())
        bg = alpha(Th.c("rose"), 215 * h) if self.danger else alpha(Th.c("glass"), int(20 * h))
        p.fillPath(rounded(r, r.width() * 0.34), bg)
        col = QColor("white") if (self.danger and h > .5) else mix(Th.c("muted"), Th.c("text"), h)
        if self.icon == "gear":
            p.translate(r.center()); p.rotate(70 * h); p.translate(-r.center())
        draw_icon(p, self.icon, r.adjusted(7, 7, -7, -7), col)


class Wordmark(QWidget):
    """'Lingo' in theme text + 'Lens' in a cyan->fuchsia sweep (brand)."""

    def __init__(self):
        super().__init__()
        self.f = app_font(13.5, QFont.Bold, -0.2)
        fm = QFontMetrics(self.f)
        self.w1 = fm.horizontalAdvance("Lingo ")
        self.setFixedSize(self.w1 + fm.horizontalAdvance("Lens") + 4, 36)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        fm = QFontMetrics(self.f)
        y = (self.height() + fm.ascent() - fm.descent()) / 2.0
        a = QPainterPath(); a.addText(0, y, self.f, "Lingo")
        b = QPainterPath(); b.addText(self.w1, y, self.f, "Lens")
        p.fillPath(a, Th.c("text"))
        g = QLinearGradient(self.w1, 0, self.width(), 0)
        g.setColorAt(0, Th.c("cyan")); g.setColorAt(1, mix(Th.c("cyan"), Th.c("fuchsia"), .5))
        p.fillPath(b, QBrush(g))


class StatusPill(QWidget):
    """Pulsing status pill; takes a palette KEY, so it morphs with the theme.

    Clickable: the window wires ``clicked`` to the backend health re-check.
    """

    clicked = pyqtSignal()

    def __init__(self, text, key="green"):
        super().__init__()
        self.text, self.key = text, key
        self.font_ = app_font(8.4, QFont.DemiBold)
        self.setCursor(Qt.PointingHandCursor)
        self._pulse = 0.0
        self._flash_k = 0.0  # one-shot state-change flash, tweens 1 -> 0
        self.flash = Tween(self, 0.0, 450)
        self.flash.valueChanged.connect(self._on_flash)
        a = QVariantAnimation(self, duration=1700, loopCount=-1)
        a.setStartValue(0.0); a.setEndValue(1.0)
        a.valueChanged.connect(lambda v: (setattr(self, "_pulse", v), self.update()))
        a.start()
        self._fit()

    def _fit(self):
        self.setFixedSize(QFontMetrics(self.font_).horizontalAdvance(self.text) + 36, 28)

    def _on_flash(self, v):
        self._flash_k = float(v)

    def set_state(self, text, key):
        if text == self.text and key == self.key:
            return  # repeated same-state poll: no flash, no resize churn
        self.text, self.key = text, key
        self._fit()
        self.flash.val = 1.0  # single ease-out tween 1 -> 0 (no self-cancel)
        self.flash.go(0.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        col = Th.c(self.key)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rounded(r, r.height() / 2)
        fk = max(0.0, min(1.0, self._flash_k))
        if fk > 0.003:  # one-shot state-change halo, eases out with the tween
            halo = rounded(r.adjusted(-2.5 * fk, -2.5 * fk, 2.5 * fk, 2.5 * fk),
                           r.height() / 2 + 2.5 * fk)
            p.setPen(QPen(alpha(col, 120 * fk), 1.5))
            p.drawPath(halo)
            p.fillPath(path, alpha(col, 26 + 70 * fk))
        else:
            p.fillPath(path, alpha(col, 26))
        p.setPen(QPen(alpha(col, 85), 1)); p.drawPath(path)
        c = QPointF(15, r.center().y())
        p.setPen(Qt.NoPen)
        p.setBrush(alpha(col, 110 * (1 - self._pulse)))
        p.drawEllipse(c, 3.5 + 5 * self._pulse, 3.5 + 5 * self._pulse)
        p.setBrush(col); p.drawEllipse(c, 3.5, 3.5)
        draw_text(p, QRectF(26, 0, self.width() - 26, self.height()), self.text,
                  self.font_, mix(col, QColor("white"), .55))


class Card(QWidget):
    def __init__(self, radius=18):
        super().__init__()
        self.radius = radius

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rounded(r, self.radius)
        fill = QLinearGradient(r.topLeft(), r.bottomLeft())
        fill.setColorAt(0, Th.c("card_a")); fill.setColorAt(1, Th.c("card_b"))
        p.fillPath(path, QBrush(fill))
        edge = QLinearGradient(r.topLeft(), r.bottomLeft())
        edge.setColorAt(0, Th.c("card_edge_a")); edge.setColorAt(1, Th.c("card_edge_b"))
        p.setPen(QPen(QBrush(edge), 1)); p.drawPath(path)


# ==========================================================================
#  Hero button
# ==========================================================================
class HeroButton(HoverWidget):
    """[camera] Snip & Translate [Alt][Shift][M] — gradient, glow, shine sweep.

    No busy/fake-progress state: the Control Center never learns when the
    snip pipeline finishes, so the button only reports press + launch.
    """

    def __init__(self):
        super().__init__()
        self.setFixedHeight(96)
        self.label = "Snip & Translate"
        self.caps = ["Alt", "Shift", "M"]
        self.shine = Tween(self, 0, 750, QEasingCurve.InOutCubic)

    def enterEvent(self, e):
        super().enterEvent(e)
        self.shine.stop(); self.shine.val = 0.0; self.shine.go(1)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h, pr = self.hover.val, self.press.val
        btn = QRectF(self.rect()).adjusted(10, 6, -10, -30)
        c = btn.center()
        s = 1 - 0.018 * pr
        p.translate(c); p.scale(s, s); p.translate(-c)

        for i in range(14, 0, -1):
            grow = i * 1.3
            r = btn.adjusted(-grow, -grow + 11, grow, grow + 11)
            a = (4.0 + 5.0 * h) * (1 - i / 15.0) ** 1.4
            p.fillPath(rounded(r, 20 + grow), alpha(Th.c("indigo"), a * 2.2))

        path = rounded(btn, 20)
        g = QLinearGradient(btn.topLeft(), btn.bottomRight())
        g.setColorAt(0, Th.c("cyan")); g.setColorAt(0.55, Th.c("indigo")); g.setColorAt(1, Th.c("fuchsia"))
        p.fillPath(path, QBrush(g))
        sheen = QLinearGradient(btn.topLeft(), btn.bottomLeft())
        sheen.setColorAt(0, QColor(255, 255, 255, 62)); sheen.setColorAt(0.55, QColor(255, 255, 255, 0))
        sheen.setColorAt(1, QColor(0, 0, 0, 36))
        p.fillPath(path, QBrush(sheen))
        p.fillPath(path, QColor(255, 255, 255, int(16 * h)))

        if 0.0 < self.shine.val < 1.0:
            x = lerp(btn.left() - 90, btn.right() + 30, self.shine.val)
            sweep = QPainterPath()
            sweep.addPolygon(QPolygonF([QPointF(x, btn.top()), QPointF(x + 46, btn.top()),
                                        QPointF(x + 14, btn.bottom()), QPointF(x - 32, btn.bottom())]))
            sweep.closeSubpath()
            p.fillPath(sweep.intersected(path), QColor(255, 255, 255, 46))

        rim = QLinearGradient(btn.topLeft(), btn.bottomLeft())
        rim.setColorAt(0, QColor(255, 255, 255, 120)); rim.setColorAt(1, QColor(255, 255, 255, 18))
        p.setPen(QPen(QBrush(rim), 1)); p.setBrush(Qt.NoBrush)
        p.drawPath(rounded(btn.adjusted(.5, .5, -.5, -.5), 19.5))

        f_text, f_cap = app_font(12.5, QFont.Bold), app_font(8.3, QFont.Bold)
        fm_t, fm_c = QFontMetrics(f_text), QFontMetrics(f_cap)
        tw = fm_t.horizontalAdvance(self.label)
        cap_w = [fm_c.horizontalAdvance(t) + 18 for t in self.caps]
        caps_total = sum(cap_w) + 6 * max(0, len(cap_w) - 1)
        total = 24 + 10 + tw + (18 + caps_total if self.caps else 0)
        x = c.x() - total / 2
        draw_icon(p, "camera", QRectF(x, c.y() - 12, 24, 24), QColor("white"), 1.7)
        x += 34
        draw_text(p, QRectF(x, btn.top(), tw + 4, btn.height()), self.label, f_text, QColor("white"))
        x += tw + 18
        for t, w in zip(self.caps, cap_w):
            r = QRectF(x, c.y() - 11, w, 22)
            p.fillPath(rounded(r, 7), QColor(255, 255, 255, 52))
            draw_text(p, r, t, f_cap, QColor(255, 255, 255, 240), Qt.AlignCenter)
            x += w + 6


class PillButton(HoverWidget):
    def __init__(self, text, kind="primary", width=120, height=40):
        super().__init__()
        self.text, self.kind = text, kind
        self.setFixedSize(width, height)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h, pr = self.hover.val, self.press.val
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = 1 - 0.03 * pr
        p.translate(r.center()); p.scale(s, s); p.translate(-r.center())
        path = rounded(r, r.height() * 0.38)
        if self.kind == "primary":
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, Th.c("cyan")); g.setColorAt(1, Th.c("indigo"))
            p.fillPath(path, QBrush(g))
            p.fillPath(path, QColor(255, 255, 255, int(24 * h)))
            p.setPen(QPen(QColor(255, 255, 255, 70), 1)); p.drawPath(path)
            col = QColor("white")
        else:
            base = Th.c("rose") if self.kind == "danger" else Th.c("glass")
            p.fillPath(path, alpha(base, 16 + 20 * h))
            p.setPen(QPen(alpha(base, 70 + 70 * h), 1)); p.drawPath(path)
            col = mix(Th.c("rose"), QColor("white"), .35) if self.kind == "danger" else Th.c("text")
        draw_text(p, r, self.text, app_font(10, QFont.DemiBold), col, Qt.AlignCenter)


# ==========================================================================
#  Language picker: custom translucent popup.
#
#  The two sides have different shapes (FROM: 12 (name, model-option) rows;
#  TO: 20 (name, translation-code) rows), so the selector takes plain
#  accessor functions instead of one shared LANGS table:
#      badge_of(i, row) -> short badge text, label_of(i, row) -> full name.
# ==========================================================================
POP_PAD, POP_RADIUS, ROW_H = 20, 18, 42


class LangDelegate(QStyledItemDelegate):
    def __init__(self, parent, items, current):
        super().__init__(parent)
        self.items = items      # [(badge, label), ...]
        self.current = current  # index

    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), ROW_H)

    def paint(self, p, opt, idx):
        p.save()
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        i = idx.row()
        badge_txt, name = self.items[i]
        r = QRectF(opt.rect).adjusted(2, 2, -2, -2)
        hover = bool(opt.state & QStyle.State_MouseOver)
        cur = i == self.current
        path = rounded(r, 12)
        if cur:
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0, alpha(Th.c("cyan"), 52)); g.setColorAt(1, alpha(Th.c("indigo"), 62))
            p.fillPath(path, QBrush(g))
            p.setPen(QPen(alpha(Th.c("cyan"), 80), 1)); p.drawPath(path)
        elif hover:
            p.fillPath(path, alpha(Th.c("glass"), 18))
        badge = QRectF(r.left() + 7, r.center().y() - 13, 34, 26)
        p.fillPath(rounded(badge, 8), alpha(Th.c("glass"), 34 if cur else 15))
        draw_text(p, badge, badge_txt, app_font(7.8, QFont.Bold),
                  Th.c("text") if (cur or hover) else Th.c("soft"), Qt.AlignCenter)
        nx = badge.right() + 12
        f_name = app_font(10, QFont.DemiBold if cur else QFont.Normal)
        name_w = QFontMetrics(f_name).horizontalAdvance(name)
        right = r.right() - (30 if cur else 12)
        avail = max(40, right - nx)
        shown = QFontMetrics(f_name).elidedText(name, Qt.ElideRight, int(avail))
        draw_text(p, QRectF(nx, r.top(), avail, r.height()), shown, f_name,
                  Th.c("text") if (cur or hover) else Th.c("soft"))
        if cur:
            draw_icon(p, "check", QRectF(r.right() - 26, r.center().y() - 8, 16, 16), Th.c("cyan"), 2.2)
        p.restore()


class LangPopup(QWidget):
    picked = pyqtSignal(int)
    dismissed = pyqtSignal()

    def __init__(self, items, current, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._gone = False
        self.lst = QListWidget(self)
        self.lst.setFrameShape(QFrame.NoFrame)
        self.lst.setMouseTracking(True)
        self.lst.setFocusPolicy(Qt.NoFocus)
        self.lst.setSelectionMode(QAbstractItemView.NoSelection)
        self.lst.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lst.viewport().setAutoFillBackground(False)
        # rgba()-only stylesheet: no hard-coded hex (lint-clean, theme-proof).
        self.lst.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 1px; }
            QScrollBar::handle:vertical { background: rgba(128,128,128,110); border-radius: 3px; min-height: 28px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        self.lst.setItemDelegate(LangDelegate(self.lst, items, current))
        cur_item = None
        for i, (_badge, label) in enumerate(items):
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, i)
            self.lst.addItem(it)
            if i == current:
                cur_item = it
        self.lst.itemClicked.connect(self._click)
        self._cur_item = cur_item

    def _click(self, item):
        self.picked.emit(item.data(Qt.UserRole))
        self.close()

    def open_for(self, anchor, align="left", width=262):
        h_list = int(ROW_H * 7.5)
        w, h = width + 2 * POP_PAD, h_list + 12 + 2 * POP_PAD
        self.setFixedSize(w, h)
        self.lst.setGeometry(POP_PAD + 6, POP_PAD + 6, width - 12, h_list)
        tl = anchor.mapToGlobal(QPoint(0, 0))
        x = tl.x() - POP_PAD if align == "left" else tl.x() + anchor.width() - width - POP_PAD
        y = tl.y() + anchor.height() + 6 - POP_PAD
        scr = QApplication.screenAt(tl) or QApplication.primaryScreen()
        if y + h > scr.availableGeometry().bottom():
            y = tl.y() - h - 6 + POP_PAD
        self.move(x, y - 8)
        self.setWindowOpacity(0.0)
        self.show()
        if self._cur_item:
            self.lst.scrollToItem(self._cur_item, QAbstractItemView.PositionAtCenter)
        g = QParallelAnimationGroup(self)
        a1 = QPropertyAnimation(self, b"windowOpacity", self)
        a1.setDuration(150); a1.setStartValue(0.0); a1.setEndValue(1.0)
        a2 = QPropertyAnimation(self, b"pos", self)
        a2.setDuration(190); a2.setStartValue(QPoint(x, y - 8)); a2.setEndValue(QPoint(x, y))
        a2.setEasingCurve(QEasingCurve.OutCubic)
        g.addAnimation(a1); g.addAnimation(a2); g.start()
        self._anims = g

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        body = QRectF(self.rect()).adjusted(POP_PAD, POP_PAD, -POP_PAD, -POP_PAD)
        for i in range(10, 0, -1):
            grow = i * (POP_PAD - 4) / 10
            p.fillPath(rounded(body.adjusted(-grow, -grow + 6, grow, grow + 6), POP_RADIUS + grow),
                       QColor(2, 3, 12, 14))
        path = rounded(body, POP_RADIUS)
        g = QLinearGradient(body.topLeft(), body.bottomRight())
        g.setColorAt(0, mix(Th.c("bg_a"), Th.c("glass"), .05))
        g.setColorAt(1, Th.c("bg_b"))
        p.fillPath(path, QBrush(g))
        edge = QLinearGradient(body.topLeft(), body.bottomLeft())
        edge.setColorAt(0, alpha(Th.c("edge"), 64)); edge.setColorAt(1, alpha(Th.c("edge"), 16))
        p.setPen(QPen(QBrush(edge), 1)); p.setBrush(Qt.NoBrush)
        p.drawPath(rounded(body.adjusted(.5, .5, -.5, -.5), POP_RADIUS - .5))

    def hideEvent(self, e):
        if not self._gone:
            self._gone = True
            self.dismissed.emit()


class LangSelector(HoverWidget):
    """Language button; emits the picked row INDEX (main window maps it
    through ``ui.languages``). ``changed`` fires only on real changes."""

    changed = pyqtSignal(int)

    def __init__(self, rows, badge_of, label_of, index=0, align="left", parent=None):
        super().__init__(parent)
        self.rows, self.badge_of, self.label_of = rows, badge_of, label_of
        self.index, self.align = index, align
        self.setFixedHeight(54)
        self.openness = Tween(self, 0, 200)
        self._popup, self._closed_at = None, 0.0
        self.clicked.connect(self._toggle)

    def currentIndex(self):
        return self.index

    def setCurrentIndex(self, i, emit=False):
        i = max(0, min(len(self.rows) - 1, int(i)))
        if i != self.index:
            self.index = i
            self.update()
            if emit:
                self.changed.emit(i)
        else:
            self.update()

    def _items(self):
        return [(self.badge_of(i, r), self.label_of(i, r))
                for i, r in enumerate(self.rows)]

    def _toggle(self):
        if time.monotonic() - self._closed_at < 0.2:
            return
        self._popup = LangPopup(self._items(), self.index, self.window())
        self._popup.picked.connect(self._on_pick)
        self._popup.dismissed.connect(self._on_dismiss)
        self.openness.go(1)
        self._popup.open_for(self, self.align)

    def _on_pick(self, i):
        if i != self.index:
            self.index = i
            self.update()
            self.changed.emit(i)

    def _on_dismiss(self):
        self._closed_at = time.monotonic()
        self.openness.go(0)
        if self._popup:
            self._popup.deleteLater(); self._popup = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h, o = self.hover.val, self.openness.val
        a = max(h, o)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rounded(r, 17)
        p.fillPath(path, alpha(Th.c("glass"), int(lerp(11, 20, a))))
        p.setPen(QPen(mix(alpha(Th.c("glass"), 30), alpha(Th.c("cyan"), 190), o if o > h else h * .35), 1.2))
        p.drawPath(path)
        items = self._items()
        badge_txt, name = items[self.index]
        badge = QRectF(9, (self.height() - 32) / 2, 38, 32)
        g = QLinearGradient(badge.topLeft(), badge.bottomRight())
        g.setColorAt(0, alpha(Th.c("cyan"), 90)); g.setColorAt(1, alpha(Th.c("indigo"), 120))
        p.fillPath(rounded(badge, 11), QBrush(g))
        draw_text(p, badge, badge_txt, app_font(8.6, QFont.Bold), Th.c("text"), Qt.AlignCenter)
        f = app_font(10, QFont.DemiBold)
        short = name.split(" (")[0]
        txt = QFontMetrics(f).elidedText(short, Qt.ElideRight, int(self.width() - 45 - 14 - 30))
        draw_text(p, QRectF(59, 0, self.width() - 92, self.height()), txt, f, Th.c("text"))
        p.save()
        p.translate(self.width() - 22, self.height() / 2)
        p.rotate(180 * o)
        draw_icon(p, "chevron", QRectF(-8, -8, 16, 16), mix(Th.c("muted"), Th.c("text"), a), 2.0)
        p.restore()


class SwapButton(HoverWidget):
    """Swap icon with an OutBack spin on click. Muted when disabled —
    the window disables it when ``is_swappable`` is False (no OCR
    model for the target language)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 46)
        self.rot = Tween(self, 0, 420, QEasingCurve.OutBack)
        self.clicked.connect(lambda: self.rot.go(self.rot.val + 180))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        h, pr = self.hover.val, self.press.val
        en = self.isEnabled()
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        s = 1 - 0.08 * pr
        p.translate(r.center()); p.scale(s, s)
        r = r.translated(-r.center())
        p.fillPath(rounded(r, 23), alpha(Th.c("glass"), int(lerp(12, 24, h)) if en else 6))
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        if en:
            g.setColorAt(0, mix(alpha(Th.c("glass"), 40), alpha(Th.c("cyan"), 210), h))
            g.setColorAt(1, mix(alpha(Th.c("glass"), 16), alpha(Th.c("fuchsia"), 210), h))
        else:
            g.setColorAt(0, alpha(Th.c("glass"), 18))
            g.setColorAt(1, alpha(Th.c("glass"), 10))
        p.setPen(QPen(QBrush(g), 1.3)); p.drawPath(rounded(r, 23))
        p.rotate(self.rot.val)
        col = mix(Th.c("soft"), QColor("white"), h) if en else alpha(Th.c("muted"), 120)
        draw_icon(p, "swap", QRectF(-10, -10, 20, 20), col, 1.9)


class Chip(HoverWidget):
    """Recent-pair quick-apply chip (A -> B short codes)."""

    def __init__(self, a, b, parent=None):
        super().__init__(parent)
        self.a, self.b, self.active = a, b, False
        self.f = app_font(8.8, QFont.Bold, 0.4)
        fm = QFontMetrics(self.f)
        self.wa, self.wb = fm.horizontalAdvance(a), fm.horizontalAdvance(b)
        self.setFixedSize(self.wa + self.wb + 56, 30)

    def set_active(self, v):
        self.active = v; self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        h = self.hover.val
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rounded(r, r.height() / 2)
        p.fillPath(path, alpha(Th.c("cyan"), 34) if self.active
                   else alpha(Th.c("glass"), int(lerp(11, 22, h))))
        p.setPen(QPen(alpha(Th.c("cyan"), 120) if self.active
                      else alpha(Th.c("glass"), int(lerp(24, 60, h))), 1))
        p.drawPath(path)
        col = Th.c("text") if (self.active or h > .3) else Th.c("soft")
        x = 14
        draw_text(p, QRectF(x, 0, self.wa + 2, self.height()), self.a, self.f, col)
        x += self.wa + 8
        p.setPen(QPen(alpha(col, 200), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cy = self.height() / 2
        p.drawLine(QPointF(x, cy), QPointF(x + 10, cy))
        p.drawPolyline(QPolygonF([QPointF(x + 6.5, cy - 3.2), QPointF(x + 10, cy), QPointF(x + 6.5, cy + 3.2)]))
        x += 18
        draw_text(p, QRectF(x, 0, self.wb + 2, self.height()), self.b, self.f, col)


# ==========================================================================
#  Toast
# ==========================================================================
class Toast(QWidget):
    def __init__(self, parent, bottom_margin=16):
        super().__init__(parent)
        self.text = ""
        self._bottom = bottom_margin
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.f = app_font(9.5, QFont.DemiBold)
        self.hide()
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._a = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rounded(r, r.height() / 2)
        p.fillPath(path, alpha(Th.c("bg_a"), 235))
        p.setPen(QPen(alpha(Th.c("glass"), 60), 1)); p.drawPath(path)
        draw_text(p, r.adjusted(16, 0, -16, 0), self.text, self.f, Th.c("text"), Qt.AlignCenter)

    def show_text(self, text):
        self.text = text
        fm = QFontMetrics(self.f)
        self.setFixedSize(fm.horizontalAdvance(text) + 40, 34)
        self.move((self.parent().width() - self.width()) // 2,
                  self.parent().height() - self.height() - self._bottom)
        self.show(); self.raise_()
        self._fx.setOpacity(0.0)
        a = QPropertyAnimation(self._fx, b"opacity", self)
        a.setDuration(160); a.setStartValue(0.0); a.setEndValue(1.0); a.start()
        self._a = a
        QTimer.singleShot(1600, self._fade)

    def _fade(self):
        a = QPropertyAnimation(self._fx, b"opacity", self)
        a.setDuration(280); a.setStartValue(1.0); a.setEndValue(0.0)
        a.finished.connect(self.hide); a.start()
        self._a = a


# ==========================================================================
#  Settings parts
# ==========================================================================
class GlowSlider(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, lo, hi, val, parent=None):
        super().__init__(parent)
        self.lo, self.hi, self._v = lo, hi, val
        self.setFixedHeight(26)
        self.setMinimumWidth(80)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.hover = Tween(self, 0, 140)
        self.grab_t = Tween(self, 0, 120)
        self._dragging = False

    def value(self):
        return self._v

    def setValue(self, v, emit=True):
        v = max(self.lo, min(self.hi, int(v)))
        if v != self._v:
            self._v = v; self.update()
            if emit:
                self.valueChanged.emit(v)

    def _track(self):
        return QRectF(10, (self.height() - 6) / 2, self.width() - 20, 6)

    def _x(self):
        tr = self._track()
        return tr.left() + (self._v - self.lo) / (self.hi - self.lo) * tr.width()

    def _from_x(self, x):
        tr = self._track()
        f = max(0.0, min(1.0, (x - tr.left()) / tr.width()))
        self.setValue(round(self.lo + f * (self.hi - self.lo)))

    def enterEvent(self, e): self.hover.go(1)
    def leaveEvent(self, e): self.hover.go(0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True; self.grab_t.go(1); self._from_x(e.x())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._from_x(e.x())

    def mouseReleaseEvent(self, e):
        self._dragging = False; self.grab_t.go(0)

    def wheelEvent(self, e):
        self.setValue(self._v + (1 if e.angleDelta().y() > 0 else -1))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        tr, x = self._track(), self._x()
        h, d = self.hover.val, self.grab_t.val
        p.fillPath(rounded(tr, 3), alpha(Th.c("glass"), 24))
        if x - tr.left() > 1:
            g = QLinearGradient(tr.left(), 0, tr.right(), 0)
            g.setColorAt(0, Th.c("cyan")); g.setColorAt(1, Th.c("fuchsia"))
            p.fillPath(rounded(QRectF(tr.left(), tr.top(), x - tr.left(), tr.height()), 3), QBrush(g))
        c = QPointF(x, self.height() / 2)
        glow = QRadialGradient(c, 17)
        glow.setColorAt(0, alpha(Th.c("indigo"), 80 + 90 * d + 30 * h)); glow.setColorAt(1, alpha(Th.c("indigo"), 0))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(glow)); p.drawEllipse(c, 17, 17)
        rad = 8 + 1.2 * h + 1.0 * d
        p.setBrush(QColor("white")); p.drawEllipse(c, rad, rad)
        p.setBrush(mix(Th.c("cyan"), Th.c("indigo"), .6)); p.drawEllipse(c, rad - 4.2, rad - 4.2)


class Swatches(QWidget):
    colorChanged = pyqtSignal(QColor)
    CELL = 28

    def __init__(self, presets, current, parent=None):
        super().__init__(parent)
        self.presets = [QColor(c) for c in presets]
        self.current = QColor(current)
        self.setFixedSize(self.CELL * (len(presets) + 1), 28)
        self.setCursor(Qt.PointingHandCursor)

    def set_color(self, c):
        self.current = QColor(c); self.update()

    def color(self):
        return QColor(self.current)

    def mousePressEvent(self, e):
        i = int(e.x() // self.CELL)
        if i < len(self.presets):
            self.set_color(self.presets[i]); self.colorChanged.emit(self.current)
        else:
            c = QColorDialog.getColor(self.current, self.window(), "Pick a color")
            if c.isValid():
                self.set_color(c); self.colorChanged.emit(c)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        is_preset = any(c.name() == self.current.name() for c in self.presets)
        for i in range(len(self.presets) + 1):
            c = QPointF(self.CELL * i + self.CELL / 2, 14)
            custom = i == len(self.presets)
            selected = (not is_preset) if custom else (self.presets[i].name() == self.current.name())
            if custom:
                g = QConicalGradient(c, 0)
                for k, col in enumerate(["#FF5E5E", "#FFD24D", "#4DFF88", "#4DD2FF", "#8A5CFF", "#FF5ED2", "#FF5E5E"]):
                    g.setColorAt(k / 6, QColor(col))
                p.setPen(Qt.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(c, 9.5, 9.5)
                p.setBrush(Th.c("bg_b")); p.drawEllipse(c, 6.2, 6.2)
                if not is_preset:
                    p.setBrush(self.current); p.drawEllipse(c, 6.2, 6.2)
                else:
                    p.setPen(QPen(Th.c("soft"), 1.6, Qt.SolidLine, Qt.RoundCap))
                    p.drawLine(QPointF(c.x() - 3, c.y()), QPointF(c.x() + 3, c.y()))
                    p.drawLine(QPointF(c.x(), c.y() - 3), QPointF(c.x(), c.y() + 3))
            else:
                p.setPen(Qt.NoPen); p.setBrush(self.presets[i]); p.drawEllipse(c, 9.5, 9.5)
                hl = QRadialGradient(QPointF(c.x() - 3, c.y() - 4), 10)
                hl.setColorAt(0, QColor(255, 255, 255, 80)); hl.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(QBrush(hl)); p.drawEllipse(c, 9.5, 9.5)
            if selected:
                p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(255, 255, 255, 230), 1.6))
                p.drawEllipse(c, 12.6, 12.6)


class SliderRow(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, label, lo, hi, val, suffix, parent=None):
        super().__init__(parent)
        self.suffix = suffix
        self.setFixedHeight(30)
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(8)
        lb = make_label(label, 9.5, QFont.Normal, "soft"); lb.setFixedWidth(134)
        self.slider = GlowSlider(lo, hi, val)
        self.val_lbl = make_label("", 9.5, QFont.Bold, "text")
        self.val_lbl.setFixedWidth(52); self.val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(lb); row.addWidget(self.slider, 1); row.addWidget(self.val_lbl)
        self.slider.valueChanged.connect(self._sync); self._sync(val)

    def _sync(self, v):
        self.val_lbl.setText(f"{v}{self.suffix}")
        self.valueChanged.emit(v)

    def value(self):
        return self.slider.value()

    def setValue(self, v):
        self.slider.setValue(v)


class ColorRow(QWidget):
    colorChanged = pyqtSignal(QColor)

    def __init__(self, label, presets, current, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(8)
        lb = make_label(label, 9.5, QFont.Normal, "soft")
        self.sw = Swatches(presets, current)
        self.hex = make_label(QColor(current).name().upper(), 8.8, QFont.DemiBold, "muted")
        self.hex.setFixedWidth(58); self.hex.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(lb); row.addStretch(1); row.addWidget(self.sw); row.addWidget(self.hex)
        self.sw.colorChanged.connect(self._sync)

    def _sync(self, c):
        self.hex.setText(c.name().upper())
        self.colorChanged.emit(c)

    def set_color(self, c):
        self.sw.set_color(c)
        self.hex.setText(QColor(c).name().upper())


class ThemePicker(QWidget):
    picked = pyqtSignal(str)

    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.current = current
        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.hover_i = -1

    def set_current(self, name):
        self.current = name; self.update()

    def _cell_w(self):
        return self.width() / max(1, len(THEME_ORDER))

    def _idx(self, x):
        cw = self._cell_w()
        if cw <= 0:
            return 0
        return max(0, min(len(THEME_ORDER) - 1, int(x / cw)))

    def mouseMoveEvent(self, e):
        i = self._idx(e.x())
        if i != self.hover_i:
            self.hover_i = i; self.update()

    def leaveEvent(self, e):
        self.hover_i = -1; self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        name = THEME_ORDER[self._idx(e.x())]
        if name != self.current:
            self.current = name
            self.picked.emit(name)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        cw = self._cell_w()
        for i, name in enumerate(THEME_ORDER):
            pal = PALETTES[name]
            cell = QRectF(i * cw, 0, cw, self.height())
            ring = QRectF(0, 0, 36, 36)
            ring.moveCenter(QPointF(cell.center().x(), 20))
            g = QLinearGradient(ring.topLeft(), ring.bottomRight())
            g.setColorAt(0, pal.cyan); g.setColorAt(.5, pal.indigo); g.setColorAt(1, pal.fuchsia)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(ring)
            p.setBrush(pal.bg_a); p.drawEllipse(ring.center(), 8, 8)
            sel = name == self.current
            if sel:
                p.setBrush(Qt.NoBrush); p.setPen(QPen(Th.c("text"), 1.8)); p.drawEllipse(ring.adjusted(-3, -3, 3, 3))
            elif i == self.hover_i:
                p.setBrush(Qt.NoBrush); p.setPen(QPen(alpha(Th.c("text"), 120), 1.4))
                p.drawEllipse(ring.adjusted(-3, -3, 3, 3))
            draw_text(p, QRectF(cell.left(), 40, cell.width(), 16), THEME_LABELS[name],
                      app_font(8.6, QFont.DemiBold), Th.c("text") if sel else Th.c("muted"),
                      Qt.AlignHCenter | Qt.AlignVCenter)


class OverlayPreview(QWidget):
    """Live style preview of the capture box.

    Reads a plain dict (``fill`` hex, ``fill_op`` %, ``border`` px)
    so it stays decoupled from the settings object.
    """

    def __init__(self, st, parent=None):
        super().__init__(parent)
        self.st = st
        self.setFixedHeight(84)

    def paintEvent(self, e):
        st = self.st
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = rounded(r, 16)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, mix(Th.c("bg_a"), QColor("black"), .25))
        g.setColorAt(1, Th.c("bg_b"))
        p.fillPath(path, QBrush(g))
        p.setPen(QPen(alpha(Th.c("glass"), 26), 1)); p.drawPath(path)

        for i, w in enumerate([.46, .70, .36, .60, .42]):
            y = r.top() + 12 + i * 13
            x = r.left() + 14
            p.fillPath(rounded(QRectF(x, y, 22, 4), 2), alpha(Th.c("cyan"), 85))
            p.fillPath(rounded(QRectF(x + 28, y, (r.width() - 70) * w, 4), 2), alpha(Th.c("glass"), 26))

        box = QRectF(r.left() + r.width() * .22, r.top() + r.height() * .18,
                     r.width() * .56, r.height() * .62)
        fill = QColor(st["fill"])
        p.fillPath(rounded(box, 7), alpha(fill, st["fill_op"] * 2.55))
        if st["border"] > 0:
            p.setPen(QPen(fill, st["border"])); p.setBrush(Qt.NoBrush)
            p.drawPath(rounded(box.adjusted(st["border"] / 2, st["border"] / 2,
                                            -st["border"] / 2, -st["border"] / 2), 7))
