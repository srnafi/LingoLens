"""LingoLens logo — code-generated asset (QPainter, no font dependency).

The logo is painted in code so it is reproducible and versioned: no
binary art tool needed, and any future tweak is a diff, not a redraw.
Regenerate the runtime files with:
    env -u PYTHONPATH .venv/Scripts/python.exe ui/logo.py

Design: a dark glass tile (matches the Control Center card) holding a
lens ring with a cyan→indigo sweep (the "lens" that reads the screen)
and a white instant-bolt (translation, instant). A small orbit dot
suggests world languages circling the lens. Three elements, no text —
reads cleanly from 16px (taskbar) to 512px (README/store art).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
except ImportError:  # pragma: no cover - generator only
    QtCore = QtGui = QtWidgets = None


def paint_logo(size=512):
    """Paint the LingoLens mark at any square size. Returns a QImage."""
    s = float(size)
    u = s / 512.0  # design unit: all geometry below is in 512-space
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)

    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)

    # ---- dark glass tile ----
    tile = QtCore.QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
    tile_grad = QtGui.QLinearGradient(tile.topLeft(), tile.bottomLeft())
    tile_grad.setColorAt(0.0, QtGui.QColor("#26314f"))
    tile_grad.setColorAt(0.5, QtGui.QColor("#141a2e"))
    tile_grad.setColorAt(1.0, QtGui.QColor("#0a0e1a"))
    p.setPen(QtGui.QPen(QtGui.QColor(130, 140, 234, 150), max(1.0, 4.0 * u)))
    p.setBrush(tile_grad)
    p.drawRoundedRect(tile, s * 0.20, s * 0.20)

    # top gloss: thin light shelf so the tile reads as glass
    gloss = QtGui.QLinearGradient(0, tile.top(), 0, tile.top() + s * 0.30)
    gloss.setColorAt(0.0, QtGui.QColor(255, 255, 255, 52))
    gloss.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(gloss)
    p.drawRoundedRect(
        QtCore.QRectF(tile.left() + s * 0.06, tile.top() + s * 0.035,
                      tile.width() - s * 0.12, s * 0.24),
        s * 0.10, s * 0.10)

    # ---- lens ring: conical cyan -> indigo sweep ----
    cx, cy, radius = s * 0.5, s * 0.465, s * 0.222
    sweep = QtGui.QConicalGradient(cx, cy, -35.0)
    sweep.setColorAt(0.00, QtGui.QColor("#22b8cf"))
    sweep.setColorAt(0.35, QtGui.QColor("#8b95f2"))
    sweep.setColorAt(0.62, QtGui.QColor("#5e6ad2"))
    sweep.setColorAt(1.00, QtGui.QColor("#22b8cf"))
    p.setPen(QtGui.QPen(sweep, s * 0.082,
                        QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)

    # inner hairline: faint full circle to seat the ring optically
    p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 26), max(1.0, 2.0 * u)))
    p.drawEllipse(QtCore.QPointF(cx, cy),
                  radius - s * 0.052, radius - s * 0.052)

    # ---- instant bolt (white -> ice cyan) ----
    bolt = QtGui.QPolygonF([
        QtCore.QPointF(cx + 30 * u, cy - 74 * u),
        QtCore.QPointF(cx - 44 * u, cy + 26 * u),
        QtCore.QPointF(cx - 6 * u, cy + 26 * u),
        QtCore.QPointF(cx - 24 * u, cy + 88 * u),
        QtCore.QPointF(cx + 44 * u, cy - 6 * u),
        QtCore.QPointF(cx + 6 * u, cy - 6 * u),
    ])
    bolt_grad = QtGui.QLinearGradient(
        cx - 44 * u, cy - 74 * u, cx + 44 * u, cy + 88 * u)
    bolt_grad.setColorAt(0.0, QtGui.QColor("#ffffff"))
    bolt_grad.setColorAt(1.0, QtGui.QColor("#a5e8f5"))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(bolt_grad)
    p.drawPolygon(bolt)

    # ---- orbit dot: cyan satellite with baked glow ----
    import math
    ang = math.radians(-38.0)
    orbit_r = radius + s * 0.062
    dx, dy = cx + orbit_r * math.cos(ang), cy + orbit_r * math.sin(ang)
    halo = QtGui.QRadialGradient(dx, dy, s * 0.045)
    halo.setColorAt(0.0, QtGui.QColor(34, 184, 207, 110))
    halo.setColorAt(1.0, QtGui.QColor(34, 184, 207, 0))
    p.setBrush(halo)
    p.drawEllipse(QtCore.QPointF(dx, dy), s * 0.045, s * 0.045)
    p.setBrush(QtGui.QColor("#35d3e8"))
    p.drawEllipse(QtCore.QPointF(dx, dy), s * 0.020, s * 0.020)
    p.setBrush(QtGui.QColor("#e8fdff"))
    p.drawEllipse(QtCore.QPointF(dx - s * 0.005, dy - s * 0.005),
                  s * 0.008, s * 0.008)

    p.end()
    return img


def main():
    if QtWidgets is None:
        print("PyQt5 not available — cannot render logo.")
        return 1
    _app = QtWidgets.QApplication(sys.argv[:1])
    full = paint_logo(512)
    if not full.save(str(ROOT / "logo.png")):
        print("Failed to write logo.png")
        return 1
    icon = full.scaled(256, 256, QtCore.Qt.KeepAspectRatio,
                       QtCore.Qt.SmoothTransformation)
    if not icon.save(str(ROOT / "icon.png")):
        print("Failed to write icon.png")
        return 1
    print(f"Wrote logo.png (512) + icon.png (256) to {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
