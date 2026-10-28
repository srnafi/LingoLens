"""Settings UI components, ported 1:1 from the reference prototype.

The reference (``settings_menu.html``) defines a 420 px card with 20 px
padding, five equal tabs behind a sliding accent pill, 48 px setting rows,
a framed capture preview, an engine spec card, language chips, provider
cards with an animated drawer, and a ghost/primary footer.

Everything here paints through :data:`ui.theme.Th`, so the existing theme
cross-fade still applies. Animations use the reference durations:

* tab pill 220 ms
* panel enter 180 ms (opacity 0 -> 1, +6 px -> 0)
* provider drawer 220 ms
* meters 250 ms with 40 ms per-segment stagger
* slider/hover micro-interactions 120-160 ms
"""
from PyQt5.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation,
                          QRect, QRectF, QSize, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QPainter,
                         QPen, QPolygonF)
from PyQt5.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLayout,
                             QVBoxLayout, QWidget)

from ui.theme import Th, alpha, app_font, draw_text, mix, rounded
from ui.prism_widgets import HoverWidget, Tween, draw_icon, make_label


def f_px(px, weight=QFont.Normal):
    """Reference sizes are px; Qt point sizes are px * 0.75 at 96 dpi."""
    return app_font(px * 0.75, weight)


def _label(text, px=13, weight=QFont.Normal, key="muted", wrap=False):
    return make_label(text, px * 0.75, weight, key, wrap)


# Provider card metadata (only engines verified to work from this machine).
PROVIDER_META = {
    "auto": ("Auto", "Recommended", "A", "#6366F1",
             "Tries Google first, then MyMemory. No key needed."),
    "google": ("Google Translate", "Online", "G", "#3B6FD8",
               "Free online engine. No key needed."),
    "mymemory": ("MyMemory", "Online", "M", "#1F6F8B",
                 "Free online engine. Best for short text."),
}


# ==========================================================================
#  Tabs: one track, equal widths, sliding accent pill
# ==========================================================================
class RefTabs(QWidget):
    valueChanged = pyqtSignal(str)

    PAD = 4
    GAP = 4
    TH = 36
    TRACK_R = 14
    PILL_R = 10

    def __init__(self, options, current, width=380, parent=None):
        super().__init__(parent)
        self._ids = [oid for oid, _lab in options]
        self._labels = [lab for _oid, lab in options]
        self._value = current if current in self._ids else self._ids[0]
        self._hover = -1
        self._width = width
        self._slide = Tween(self, self._index(), 220, QEasingCurve.OutCubic)
        self._font = f_px(13, QFont.Medium)
        self.setFixedSize(width, self.TH + 2 * self.PAD)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    # ---- geometry
    def _index(self):
        return self._ids.index(self._value)

    def _seg_w(self):
        n = len(self._ids)
        return (self._width - 2 * self.PAD - self.GAP * (n - 1)) / n

    def _seg_rect(self, i):
        r = QRectF(self.rect())
        x = r.left() + self.PAD + i * (self._seg_w() + self.GAP)
        return QRectF(x, r.top() + self.PAD, self._seg_w(), self.TH)

    def _index_at(self, x):
        step = self._seg_w() + self.GAP
        i = int((x - self.PAD) // max(1.0, step))
        return max(0, min(len(self._ids) - 1, i))

    # ---- state
    def select(self, oid, emit=False):
        if oid not in self._ids or oid == self._value:
            return False
        self._value = oid
        self._hover = -1
        self._slide.go(self._index())
        self.update()
        if emit:
            self.valueChanged.emit(oid)
        return True

    def value(self):
        return self._value

    # ---- painting
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        track = rounded(r, self.TRACK_R)
        p.fillPath(track, Th.c("surface"))

        seg_w = self._seg_w()
        thumb_r = QRectF(r.left() + self.PAD
                         + self._slide.val * (seg_w + self.GAP),
                         r.top() + self.PAD, seg_w, self.TH)
        p.save()
        p.setClipPath(track)
        p.fillPath(rounded(thumb_r, self.PILL_R), Th.c("indigo"))
        p.restore()

        for i, text in enumerate(self._labels):
            col = QColor("white") if i == self._index() else (
                Th.c("text") if i == self._hover else Th.c("muted"))
            draw_text(p, self._seg_rect(i), text, self._font, col,
                      Qt.AlignCenter)

    # ---- input
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.select(self._ids[self._index_at(e.x())], emit=True)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.x())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        if self._hover != -1:
            self._hover = -1
            self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Right, Qt.Key_Down):
            self.select(self._ids[min(len(self._ids) - 1,
                                      self._index() + 1)], emit=True)
        elif e.key() in (Qt.Key_Left, Qt.Key_Up):
            self.select(self._ids[max(0, self._index() - 1)], emit=True)
        else:
            super().keyPressEvent(e)


# ==========================================================================
#  Capture preview: framed page mock, 84 px tall
# ==========================================================================
class RefPreview(QWidget):
    LINES = ((14, 120), (26, 200), (38, 90), (50, 170), (62, 130))

    def __init__(self, fill="#6366F1", opacity=18, border=2, parent=None):
        super().__init__(parent)
        self.setFixedHeight(84)
        self._solid = QColor(fill)
        self._alpha = max(0, min(255, int(opacity * 255 / 100)))
        self._border = int(border)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Linear)
        self._anim.valueChanged.connect(self._on_anim)

    def set_state(self, fill, opacity, border):
        alpha_target = max(0, min(255, int(opacity * 255 / 100)))
        target = QColor(fill)
        if target == self._solid and alpha_target == self._alpha:
            self._border = int(border)
            self.update()
            return
        self._from = QColor(self._solid)
        self._to = target
        self._alpha_from = self._alpha
        self._alpha_to = alpha_target
        self._border = int(border)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _on_anim(self, v):
        t = float(v)
        self._solid = mix(self._from, self._to, t)
        self._alpha = int(self._alpha_from + (self._alpha_to - self._alpha_from) * t)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.fillPath(rounded(r, 12), Th.c("surface"))

        p.setPen(Qt.NoPen)
        p.setBrush(mix(Th.c("line"), Th.c("surface2"), .6))
        for top, width in self.LINES:
            p.drawRoundedRect(QRectF(16, top, width, 5), 3, 3)

        box = QRectF(92, 20, 190, 44)
        fill = QColor(self._solid)
        fill.setAlpha(self._alpha)
        p.setBrush(fill)
        if self._border > 0:
            p.setPen(QPen(self._solid, self._border))
        else:
            p.setPen(Qt.NoPen)
        p.drawRoundedRect(box.adjusted(self._border / 2, self._border / 2,
                                       -self._border / 2, -self._border / 2),
                          7, 7)


# ==========================================================================
#  Capture rows: colour swatches and sliders
# ==========================================================================
class RefColorRow(QWidget):
    colorChanged = pyqtSignal(QColor)

    LBL_W = 112
    GAP = 14
    SW = 22
    SW_GAP = 10

    def __init__(self, label, presets, current, parent=None):
        super().__init__(parent)
        self.presets = [QColor(c) for c in presets]
        self.current = QColor(current)
        self._hover = -1
        self._hover_t = Tween(self, 0, 150)
        self._pop = Tween(self, 1.0, 140, QEasingCurve.OutCubic)
        self.setFixedHeight(48)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._lbl = label
        self._font = f_px(13)
        self._hex_font = f_px(12)

    def set_color(self, c):
        self.current = QColor(c)
        self.update()

    def _centers(self):
        x0 = self.LBL_W + self.GAP + self.SW / 2
        return [QPointF(x0 + i * (self.SW + self.SW_GAP), self.height() / 2)
                for i in range(len(self.presets))]

    def _index_at(self, pos):
        for i, c in enumerate(self._centers()):
            if (QPointF(pos) - c).manhattanLength() <= self.SW:
                return i
        return -1

    def mousePressEvent(self, e):
        i = self._index_at(e.pos())
        if e.button() == Qt.LeftButton and i >= 0:
            self.current = self.presets[i]
            self._pop.val = 0.8
            self._pop.go(1.0)
            self.update()
            self.colorChanged.emit(self.current)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.pos())
        if i != self._hover:
            self._hover = i
            self._hover_t.val = 0.0
            self._hover_t.go(1.0 if i >= 0 else 0.0)
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self._hover_t.go(0.0)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        draw_text(p, QRectF(0, 0, self.LBL_W, self.height()), self._lbl,
                  self._font, Th.c("muted"))
        for i, c in enumerate(self._centers()):
            hovered = i == self._hover
            scale = 1.0 + 0.12 * self._hover_t.val if hovered else 1.0
            selected = self.presets[i].name() == self.current.name()
            if selected:
                scale *= self._pop.val
            p.setPen(Qt.NoPen)
            p.setBrush(self.presets[i])
            radius = self.SW / 2 * scale
            p.drawEllipse(c, radius, radius)
            if selected:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, 255), 2))
                p.drawEllipse(c, self.SW / 2 + 2, self.SW / 2 + 2)
        hex_text = self.current.name().upper()
        fm = QFontMetrics(self._hex_font)
        w = fm.horizontalAdvance(hex_text)
        draw_text(p, QRectF(self.width() - w, 0, w, self.height()),
                  hex_text, self._hex_font, Th.c("muted"))


class RefSliderRow(QWidget):
    """Reference slider: 44 px hit area, 6 px line, 16 px white thumb."""

    valueChanged = pyqtSignal(int)

    LBL_W = 112
    GAP = 14
    VAL_W = 44

    def __init__(self, label, lo, hi, val, suffix, parent=None):
        super().__init__(parent)
        self._lbl = label
        self.lo, self.hi = int(lo), int(hi)
        self.suffix = suffix
        self._v = int(val)
        self._disp = float(val)
        self._dragging = False
        self._hover = Tween(self, 0, 120)
        self._drag = Tween(self, 0, 120)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._font = f_px(13)
        self._val_font = f_px(13, QFont.DemiBold)
        self.setFixedHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    # ---- geometry
    def _track(self):
        left = self.LBL_W + self.GAP
        right = self.width() - self.VAL_W - self.GAP
        return QRectF(left, (self.height() - 6) / 2, max(1, right - left), 6)

    def _ratio(self):
        return (self._disp - self.lo) / max(1, self.hi - self.lo)

    def _thumb_x(self):
        tr = self._track()
        return tr.left() + self._ratio() * tr.width()

    # ---- value
    def value(self):
        return self._v

    def setValue(self, v, animate=False):
        v = max(self.lo, min(self.hi, int(v)))
        self._v = v
        if animate:
            self._anim.stop()
            self._anim.setStartValue(float(self._disp))
            self._anim.setEndValue(float(v))
            self._anim.start()
        else:
            self._anim.stop()
            self._disp = float(v)
        self.update()

    def _on_anim(self, v):
        self._disp = float(v)
        self.update()

    def _from_x(self, x):
        tr = self._track()
        f = max(0.0, min(1.0, (x - tr.left()) / tr.width()))
        v = int(round(self.lo + f * (self.hi - self.lo)))
        if v != self._v:
            self._v = v
            self._disp = float(v)
            self.update()
            self.valueChanged.emit(v)

    # ---- input
    def enterEvent(self, e):
        self._hover.go(1)
        self.setCursor(Qt.PointingHandCursor)

    def leaveEvent(self, e):
        self._hover.go(0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.x() >= self.LBL_W:
            self._anim.stop()
            self._dragging = True
            self._drag.go(1)
            self._from_x(e.x())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._from_x(e.x())

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self._drag.go(0)
        self.update()

    def keyPressEvent(self, e):
        d = {Qt.Key_Right: 1, Qt.Key_Up: 1,
             Qt.Key_Left: -1, Qt.Key_Down: -1}.get(e.key())
        if d:
            v = max(self.lo, min(self.hi, self._v + d))
            if v != self._v:
                self._v = v
                self._disp = float(v)
                self.update()
                self.valueChanged.emit(v)
        else:
            super().keyPressEvent(e)

    # ---- paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        draw_text(p, QRectF(0, 0, self.LBL_W, self.height()), self._lbl,
                  self._font, Th.c("muted"))
        tr = self._track()
        p.fillPath(rounded(tr, 3), Th.c("line"))
        x = self._thumb_x()
        if x - tr.left() > 0.5:
            p.fillPath(rounded(QRectF(tr.left(), tr.top(), x - tr.left(),
                                      tr.height()), 3), Th.c("indigo"))
        cy = self.height() / 2
        r = 8 * (1 + 0.1 * self._hover.val + 0.2 * self._drag.val)
        if self._drag.val > 0.01:
            p.setPen(Qt.NoPen)
            p.setBrush(alpha(Th.c("indigo"), int(68 * self._drag.val)))
            p.drawEllipse(QPointF(x, cy), r + 6 * self._drag.val,
                          r + 6 * self._drag.val)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(x, cy), r, r)
        val_text = f"{self._v}{self.suffix}"
        draw_text(p, QRectF(self.width() - self.VAL_W, 0, self.VAL_W,
                            self.height()), val_text, self._val_font,
                  Th.c("text"), Qt.AlignRight | Qt.AlignVCenter)


# ==========================================================================
#  Engine spec card + staggered meters
# ==========================================================================
class MeterBars(QWidget):
    def __init__(self, level=0, parent=None):
        super().__init__(parent)
        self.setFixedSize(92, 10)
        self._t = [Tween(self, 1.0 if i < level else 0.0, 250,
                         QEasingCurve.OutCubic) for i in range(3)]
        self.level = level

    def set_level(self, level):
        self.level = max(0, min(3, int(level)))
        for i in range(3):
            target = 1.0 if i < self.level else 0.0
            QTimer.singleShot(i * 40, lambda i=i, t=target: self._t[i].go(t))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i in range(3):
            col = mix(Th.c("line"), Th.c("indigo"), self._t[i].val)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(i * 32, 2, 28, 6), 3, 3)


class RefSpecCard(QWidget):
    def __init__(self, description, speed, cover, parent=None):
        super().__init__(parent)
        self._desc_font = f_px(13)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)
        self.desc = _label(description, 13, QFont.Normal, "muted", wrap=True)
        self.desc.setMinimumHeight(36)
        lay.addWidget(self.desc)
        self.speed = MeterBars(speed)
        self.cover = MeterBars(cover)
        for text, meter in (("Speed", self.speed),
                            ("Language coverage", self.cover)):
            row = QHBoxLayout()
            row.setSpacing(0)
            row.addWidget(_label(text, 13, QFont.Normal, "muted"))
            row.addStretch(1)
            row.addWidget(meter)
            lay.addLayout(row)
        self._fx = None
        self._flash_anim = None

    def _flash(self):
        """Reference ``.flash``: the description fades in when it changes.

        The effect is attached only for those 180 ms and detached on finish.
        A permanent QGraphicsOpacityEffect makes QWidget.render() paint the
        label outside the card (see debug/render_variants.py).
        """
        fx = QGraphicsOpacityEffect(self.desc)
        fx.setOpacity(0.0)
        self.desc.setGraphicsEffect(fx)
        a = QPropertyAnimation(fx, b"opacity", self)
        a.setDuration(180)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: self.desc.setGraphicsEffect(None))
        a.start()
        self._flash_anim = a

    def set_spec(self, description, speed, cover):
        if self.desc.text() != description:
            self.desc.setText(description)
            self._flash()
        self.speed.set_level(speed)
        self.cover.set_level(cover)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillPath(rounded(QRectF(self.rect()), 14), Th.c("surface"))


# ==========================================================================
#  Language chips
# ==========================================================================
class RefChip(HoverWidget):
    """Reference chip: 40 px tall, 20 px radius, accent when pressed."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.active = False
        f = f_px(13)
        w = QFontMetrics(f).horizontalAdvance(text) + 32
        self.setFixedSize(w, 40)

    def set_active(self, active):
        self.active = bool(active)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        p.setOpacity(1.0 if self.isEnabled() else 0.35)
        r = QRectF(self.rect())
        s = 1 - 0.04 * self.press.val
        p.translate(r.center())
        p.scale(s, s)
        p.translate(-r.center())
        if self.active:
            bg = Th.c("indigo")
            col = QColor("white")
        else:
            base = mix(Th.c("surface2"), QColor("#2D3163"), 0.0)
            if self.hover.val:
                base = mix(base, QColor("#2D3163"), self.hover.val)
            bg = base
            col = Th.c("text")
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 20, 20)
        draw_text(p, r, self.text, f_px(13), col, Qt.AlignCenter)


class FlowLayout(QLayout):
    """Left-to-right wrapping layout (used for the language chips)."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_h = 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.x() + rect.width() - m.right() and line_h:
                x = rect.x() + m.left()
                y += line_h + self.spacing()
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.spacing()
            line_h = max(line_h, hint.height())
        return y + line_h + m.bottom() - rect.y()


# ==========================================================================
#  Provider cards with an animated drawer
# ==========================================================================
class ProviderCard(QWidget):
    clicked = pyqtSignal(str)

    HEAD = 56

    def __init__(self, pid, name, tag, letter, color, hint,
                 selected=False, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.name = name
        self.tag = tag
        self.letter = letter
        self.color = QColor(color)
        self.hint = hint
        self._selected = bool(selected)
        self._drawer_full = 30
        self._open_v = 1.0 if selected else 0.0
        self._hover = False
        self._check = Tween(self, 1.0 if selected else 0.0, 180,
                            QEasingCurve.OutCubic)
        self._open = QVariantAnimation(self)
        self._open.setDuration(220)
        self._open.setEasingCurve(QEasingCurve.OutCubic)
        self._open.setStartValue(self._open_v)
        self._open.setEndValue(self._open_v)
        self._open.valueChanged.connect(self._on_open)
        self._open.finished.connect(self._on_open_done)
        self._label = _label(hint, 12, QFont.Normal, "muted", wrap=True)
        # A parentless QLabel is a top-level window: it would float over the
        # desktop instead of painting inside the drawer.
        self._label.setParent(self)
        self._label.setVisible(self._selected)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self.HEAD + int(self._drawer_full * self._open_v))

    # ---- drawer geometry
    def _measure_drawer(self):
        w = max(80, self.width() - 28)
        fm = QFontMetrics(f_px(12))
        h = fm.boundingRect(QRect(0, 0, w, 1000), Qt.TextWordWrap,
                            self.hint).height()
        return 14 + h

    def resizeEvent(self, e):
        self._drawer_full = self._measure_drawer()
        self._label.setGeometry(14, self.HEAD, max(80, self.width() - 28),
                                self._drawer_full - 14)
        self.setFixedHeight(self.HEAD
                            + int(self._drawer_full * self._open_v))
        super().resizeEvent(e)

    def _on_open(self, v):
        self._open_v = float(v)
        self.setFixedHeight(self.HEAD + int(self._drawer_full * self._open_v))
        self.update()

    def _on_open_done(self):
        if not self._selected:
            self._label.hide()

    def set_selected(self, selected):
        selected = bool(selected)
        if selected == self._selected:
            return
        self._selected = selected
        if selected:
            self._label.show()
        self._check.go(1.0 if selected else 0.0)
        self._open.stop()
        self._open.setStartValue(self._open_v)
        self._open.setEndValue(1.0 if selected else 0.0)
        self._open.start()
        self.update()

    # ---- input
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and e.y() <= self.HEAD:
            self.clicked.emit(self.pid)

    # ---- paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        path = rounded(r, 14)
        p.fillPath(path, Th.c("surface"))
        if self._selected:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(Th.c("indigo"), 2))
            p.drawPath(rounded(r.adjusted(1, 1, -1, -1), 13))

        # avatar
        av = QRectF(14, (self.HEAD - 32) / 2, 32, 32)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(av)
        draw_text(p, av, self.letter, f_px(13, QFont.DemiBold),
                  QColor("white"), Qt.AlignCenter)

        # radio (reserved on the right)
        radio = QRectF(self.width() - 14 - 20, (self.HEAD - 20) / 2, 20, 20)
        border = mix(Th.c("line"), Th.c("indigo"), 0.35)
        p.setBrush(Th.c("indigo") if self._selected else Qt.NoBrush)
        p.setPen(QPen(Th.c("indigo") if self._selected else border, 1.5))
        p.drawEllipse(radio)
        t = self._check.val
        if t > 0.01:
            c = radio.center()
            p.save()
            p.translate(c)
            p.scale(t, t)
            p.setPen(QPen(QColor("white"), 2.2, Qt.SolidLine,
                          Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(-3, 0), QPointF(-1, 2),
                                      QPointF(3.5, -2.5)]))
            p.restore()

        # tag pill
        tf = f_px(12)
        tw = QFontMetrics(tf).horizontalAdvance(self.tag) + 20
        tag = QRectF(radio.left() - 8 - tw, (self.HEAD - 18) / 2, tw, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(Th.c("surface2"))
        p.drawRoundedRect(tag, 9, 9)
        draw_text(p, tag, self.tag, tf, Th.c("muted"), Qt.AlignCenter)

        # name
        name_rect = QRectF(58, 0, max(10, tag.left() - 58 - 8), self.HEAD)
        draw_text(p, name_rect, self.name, f_px(14, QFont.DemiBold),
                  Th.c("text"))


class ProviderList(QWidget):
    valueChanged = pyqtSignal(str)

    def __init__(self, options, current, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._cards = {}
        ids = [pid for pid, _label in options]
        current = current if current in ids else ids[0]
        for pid, _label in options:
            name, tag, letter, color, hint = PROVIDER_META.get(
                pid, (pid.title(), "Online", pid[:1].upper(), "#6366F1", ""))
            card = ProviderCard(pid, name, tag, letter, color, hint,
                                selected=pid == current)
            card.clicked.connect(self._on_card)
            self._cards[pid] = card
            lay.addWidget(card)
        self._value = current

    def value(self):
        return self._value

    def set_value(self, pid):
        if pid not in self._cards:
            return
        self._value = pid
        for cid, card in self._cards.items():
            card.set_selected(cid == pid)

    def _on_card(self, pid):
        if pid == self._value:
            return
        self.set_value(pid)
        self.valueChanged.emit(pid)


# ==========================================================================
#  Small parts: footer buttons, flat swap, static key chip, fadeable body
# ==========================================================================
class RefButton(HoverWidget):
    def __init__(self, text, kind="primary", parent=None):
        super().__init__(parent)
        self.text, self.kind = text, kind
        f = f_px(14, QFont.DemiBold if kind == "primary" else QFont.Normal)
        pad = 44 if kind == "primary" else 36
        w = QFontMetrics(f).horizontalAdvance(text) + pad
        self.setFixedSize(w, 40)
        self._font = f

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        s = 1 - 0.03 * self.press.val
        p.translate(r.center())
        p.scale(s, s)
        p.translate(-r.center())
        path = rounded(r, 12)
        if self.kind == "primary":
            bg = mix(Th.c("indigo"), QColor("#7679F5"), self.hover.val)
            p.fillPath(path, bg)
            col = QColor("white")
            p.setPen(Qt.NoPen)
        else:
            p.fillPath(path, alpha(Th.c("rose"), int(24 * self.hover.val)))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(alpha(Th.c("rose"), 72), 1))
            p.drawPath(rounded(r.adjusted(.5, .5, -.5, -.5), 12))
            col = mix(QColor("#FDA4AF"), QColor("#FECDD3"), self.hover.val)
        draw_text(p, r, self.text, self._font, col, Qt.AlignCenter)


class RefSwap(HoverWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 44)
        self.rot = Tween(self, 0, 300, QEasingCurve.OutCubic)
        self.clicked.connect(lambda: self.rot.go(self.rot.val + 180))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        p.setOpacity(1.0 if self.isEnabled() else 0.35)
        r = QRectF(self.rect())
        base = mix(Th.c("surface2"), QColor("#2D3163"), self.hover.val)
        p.setPen(Qt.NoPen)
        p.setBrush(base)
        p.drawEllipse(r)
        p.rotate(self.rot.val)
        draw_icon(p, "swap", QRectF(13, 13, 18, 18), Th.c("text"), 1.8)


class KeyChip(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        f = f_px(12, QFont.DemiBold)
        self.setFixedSize(QFontMetrics(f).horizontalAdvance(text) + 24, 30)
        self._font = f

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(Th.c("surface2"))
        p.drawRoundedRect(r, 8, 8)
        draw_text(p, r, self.text, self._font, Th.c("text"), Qt.AlignCenter)


class _Veil(QWidget):
    """Dim overlay painted above a :class:`Fadeable`'s children.

    ``QGraphicsOpacityEffect`` is the direct translation of the reference's
    ``opacity: .4``, but keeping one attached makes ``QWidget.render()`` paint
    the children at the wrong offset: every offscreen screenshot then shows
    phantom overflow and a huge empty gap (debug/render_variants.py). Painting
    the window colour over the children is the same arithmetic,
    ``0.4 * C + 0.6 * bg``, with no effect object on the tree.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._a = 0.0
        self.hide()

    def set_alpha(self, a):
        self._a = a
        if a > 0.001:
            self.raise_()
        self.setVisible(a > 0.001)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), alpha(Th.c("bg_a"), round(self._a * 255)))


class Fadeable(QWidget):
    """Reference ``.fadeable.off``: 40 % opacity, pointer events off."""

    DIM = 0.6  # veil alpha; the children then read at 0.4 opacity

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dim = 0.0
        self._veil = _Veil(self)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_alpha)

    def _set_alpha(self, v):
        self._dim = float(v)
        self._veil.set_alpha(self._dim)

    def set_dimmed(self, dimmed):
        self.setEnabled(not dimmed)
        self._anim.stop()
        self._anim.setStartValue(self._dim)
        self._anim.setEndValue(self.DIM if dimmed else 0.0)
        self._anim.start()

    def resizeEvent(self, e):
        self._veil.setGeometry(self.rect())
        self._veil.raise_()
        super().resizeEvent(e)