"""LingoLens logo — code-generated asset (QPainter, no font dependency).

The logo is painted in code so it is reproducible and versioned: no
binary art tool needed, and any future tweak is a diff, not a redraw.
Regenerate the runtime files with:
    env -u PYTHONPATH .venv/Scripts/python.exe ui/logo.py [style]

Design: minimal lens mark on transparency (no tile, no gloss, no
bolt). One open ring in an accent sweep + one satellite dot.
Three elements max, reads cleanly from 16px (taskbar) to 512px.

Styles: "gap" (open ring + dot in the gap), "orbit" (full ring + dot
on the ring), "tile" (flat dark tile + bare ring for small sizes).
"""
import math
import os
import tempfile as _tf

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
except ImportError:  # pragma: no cover - generator only
    QtCore = QtGui = QtWidgets = None

ACCENT = "#4aa8ff"
ACCENT_2 = "#6a7bff"


def _ring_pen(cx, cy):
    sweep = QtGui.QConicalGradient(cx, cy, -35.0)
    sweep.setColorAt(0.00, QtGui.QColor(ACCENT))
    sweep.setColorAt(0.55, QtGui.QColor(ACCENT_2))
    sweep.setColorAt(1.00, QtGui.QColor(ACCENT))
    return sweep


def paint_logo(size=512, style="gap"):
    """Paint the LingoLens mark at any square size. Returns a QImage."""
    s = float(size)
    u = s / 512.0  # design unit: all geometry below is in 512-space
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)

    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)

    cx, cy, radius = s * 0.5, s * 0.5, s * 0.30
    stroke = s * 0.075

    if style == "tile":
        # Flat dark tile + bare ring (small-size fallback).
        tile = QtCore.QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 28),
                             max(1.0, 3.0 * u)))
        p.setBrush(QtGui.QColor("#181b28"))
        p.drawRoundedRect(tile, s * 0.24, s * 0.24)

    p.setPen(QtGui.QPen(_ring_pen(cx, cy), stroke,
                        QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
    p.setBrush(QtCore.Qt.NoBrush)
    if style == "orbit":
        p.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)
        ang = math.radians(-38.0)
        dx, dy = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
    else:  # "gap" + "tile": 300-degree open ring, gap at top-right
        rect = QtCore.QRectF(cx - radius, cy - radius,
                             radius * 2, radius * 2)
        p.drawArc(rect, int(50 * 16), int(300 * 16))
        ang = math.radians(-35.0)  # middle of the gap
        dx, dy = cx + radius * math.cos(ang), cy + radius * math.sin(ang)

    # Satellite dot: solid accent with a soft baked halo.
    halo = QtGui.QRadialGradient(dx, dy, s * 0.055)
    halo.setColorAt(0.0, QtGui.QColor(74, 168, 255, 120))
    halo.setColorAt(1.0, QtGui.QColor(74, 168, 255, 0))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(halo)
    p.drawEllipse(QtCore.QPointF(dx, dy), s * 0.055, s * 0.055)
    p.setBrush(QtGui.QColor(ACCENT))
    p.drawEllipse(QtCore.QPointF(dx, dy), s * 0.026, s * 0.026)
    p.setBrush(QtGui.QColor("#ffffff"))
    p.drawEllipse(QtCore.QPointF(dx - s * 0.007, dy - s * 0.007),
                  s * 0.009, s * 0.009)

    p.end()
    return img


def main(argv):
    if QtWidgets is None:
        print("PyQt5 not available — cannot render logo.")
        return 1
    _app = QtWidgets.QApplication(argv[:1])
    if len(argv) > 1 and argv[1] in ("gap", "orbit", "tile"):
        out = Path(_tf.gettempdir()) / f"logo-{argv[1]}.png"
        paint_logo(256, argv[1]).save(str(out))
        print(f"Wrote preview to {out}")
        return 0
    style = "gap"
    full = paint_logo(512, style)
    if not full.save(str(ROOT / "logo.png")):
        print("Failed to write logo.png")
        return 1
    icon = full.scaled(256, 256, QtCore.Qt.KeepAspectRatio,
                       QtCore.Qt.SmoothTransformation)
    if not icon.save(str(ROOT / "icon.png")):
        print("Failed to write icon.png")
        return 1
    print(f"Wrote logo.png (512) + icon.png (256), style={style} to {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
