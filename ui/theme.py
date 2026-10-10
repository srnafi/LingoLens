"""Prism theme — palettes, runtime morph, paint helpers.

Two palettes (Dark/Light); :data:`Th` is the process-wide
morphing singleton. Every painted widget reads its colours through
``Th.c(key)`` at paint time, so a theme change cross-fades the whole
window with one animation — no stylesheets to swap.

Key set (every palette must define all of these): ``bg_a``, ``text``,
``soft``, ``muted``, ``cyan``, ``indigo``, ``fuchsia``, ``green``,
``amber``, ``rose``, ``edge``, ``glass``, ``card_a``, ``card_edge_a``.
"""

from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainterPath
from PyQt5.QtCore import QRectF, Qt


def C(s, a=255):
    c = QColor(s)
    c.setAlpha(a)
    return c


class Palette:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


PALETTES = {
    "aurora": Palette(
        bg_a=C("#0E1230"),
        text=C("#F4F6FF"), soft=C("#C5CBE8"), muted=C("#7F88B0"),
        cyan=C("#22D3EE"), indigo=C("#6366F1"), fuchsia=C("#D946EF"),
        green=C("#34D399"), amber=C("#FBBF24"), rose=C("#FB7185"),
        edge=C("#FFFFFF"), glass=C("#FFFFFF"),
        card_a=C("#FFFFFF", 17),
        card_edge_a=C("#FFFFFF", 46)),
    "day": Palette(
        bg_a=C("#F8F9FD"),
        text=C("#131726"), soft=C("#3B4256"), muted=C("#7A839B"),
        cyan=C("#0EA5E9"), indigo=C("#4F46E5"), fuchsia=C("#C026D3"),
        green=C("#0FA97A"), amber=C("#C77D0A"), rose=C("#E11D48"),
        edge=C("#0B1020"), glass=C("#0B1020"),
        card_a=C("#FFFFFF", 235),
        card_edge_a=C("#0B1020", 28)),
}

THEME_ORDER = ["aurora", "day"]
THEME_LABELS = {"aurora": "Dark", "day": "Light"}


def alpha(c, a):
    c = QColor(c)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    c1, c2 = QColor(c1), QColor(c2)
    return QColor(int(lerp(c1.red(), c2.red(), t)),
                  int(lerp(c1.green(), c2.green(), t)),
                  int(lerp(c1.blue(), c2.blue(), t)),
                  int(lerp(c1.alpha(), c2.alpha(), t)))


def rounded(rect, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(rect), r, r)
    return p


def css(c):
    c = QColor(c)
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"


class Theme:
    """Global palette with an animatable cross-fade between two palettes."""

    def __init__(self, name="aurora"):
        self.a = PALETTES[name]
        self.b = PALETTES[name]
        self.t = 1.0

    def c(self, key):
        return mix(getattr(self.a, key), getattr(self.b, key), self.t)

    def snapshot(self):
        p = Palette()
        for k in vars(self.b):
            setattr(p, k, self.c(k))
        return p


Th = Theme()

FAMILIES = ["Inter", "Segoe UI Variable Display", "Segoe UI", "SF Pro Display",
            "Helvetica Neue", "Arial"]
SHADOW = 0
RADIUS = 26
WIN_W = 480
# No WIN_H: the window hugs each page's sizeHint (see _hug()).


def app_font(pt, weight=QFont.Normal, spacing=0.0):
    f = QFont()
    try:
        f.setFamilies(FAMILIES)
    except AttributeError:
        f.setFamily(FAMILIES[2])
    f.setPointSizeF(pt)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def draw_text(p, rect, text, font, color, flags=Qt.AlignVCenter | Qt.AlignLeft):
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(QRectF(rect), int(flags), text)


def text_width(font, text):
    return QFontMetrics(font).horizontalAdvance(text)
