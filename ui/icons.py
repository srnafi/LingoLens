"""Icons painted with QPainter — no font/emoji dependency.

Emoji/symbol glyphs (bolt, gear) do not exist in Segoe UI and render as
blank buttons on systems without a color-emoji font fallback for Qt.
Painted paths always render. Text-only glyphs used elsewhere (⇄ – × →)
DO exist in Segoe UI and stay as text.
"""
from PyQt5 import QtCore, QtGui


def paint_icon(kind, size=18, color="#e8eaf2"):
    """Paint a small icon and return it as a QIcon."""
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
