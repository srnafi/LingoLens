import sys
import os
import ctypes
import logging
import logging.handlers
from pathlib import Path

# Set DPI awareness BEFORE any Qt or PIL imports.
# On Windows with display scaling, coordinates from Qt widgets,
# PIL ImageGrab, and Tk windows must all be in the same coordinate space.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
import pyautogui
from PIL import Image, ImageGrab, ImageFilter
from PyQt5 import QtWidgets, QtCore, QtGui

_this_dir = Path(__file__).parent

# Rotating file logging so headless runs (launched from the Control Center)
# still leave a traceable record. Console logging is invisible in that mode.
_logs_dir = _this_dir / "logs"
_logs_dir.mkdir(parents=True, exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    _logs_dir / "lingolens.log", maxBytes=1_000_000, backupCount=3)
_file_handler.setFormatter(
    logging.Formatter('[%(name)s] %(levelname)s: %(message)s'))

logger = logging.getLogger('capture')
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)

import detector


class CaptureWidget(QtWidgets.QWidget):
    """Full-screen transparent overlay for region selection."""
    num_snip = 0
    is_snipping = False

    def __init__(self, parent=None, destination=None, fill_color=None,
                 opacity=None, line_width=None, alpha=None, font_size=None,
                 text_color=None):
        super().__init__()
        self.parent = parent
        self.destination = destination
        self.alpha = alpha
        self.font_size = font_size
        self.text_color = text_color or "#000000"

        self.fill_color_rgb = (255, 0, 0, 100)
        self.opacity_val = 0.3
        self.line_width_val = 3

        if fill_color:
            hex_c = fill_color.lstrip('#')
            if len(hex_c) == 6:
                r = int(hex_c[0:2], 16)
                g = int(hex_c[2:4], 16)
                b = int(hex_c[4:6], 16)
                self.fill_color_rgb = (r, g, b, 100)
        if opacity is not None:
            try:
                self.opacity_val = float(opacity)
            except (ValueError, TypeError):
                pass
        if line_width is not None:
            try:
                self.line_width_val = float(line_width)
            except (ValueError, TypeError):
                pass

        screen_width, screen_height = pyautogui.size()
        logger.info(f"Screen size (pyautogui): {screen_width}x{screen_height}")
        self.setGeometry(0, 0, screen_width, screen_height)
        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()

    def start(self):
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Window |
            Qt.WindowStaysOnTopHint
        )
        CaptureWidget.is_snipping = True
        self.setWindowOpacity(self.opacity_val)
        QtWidgets.QApplication.setOverrideCursor(
            QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.show()
        self.activateWindow()

    def paintEvent(self, event):
        if CaptureWidget.is_snipping:
            fill_color = self.fill_color_rgb
            opacity = self.opacity_val
            line_width = self.line_width_val
        else:
            self.begin = QtCore.QPoint()
            self.end = QtCore.QPoint()
            fill_color = (0, 0, 0, 0)
            line_width = 0
            opacity = 0

        self.setWindowOpacity(opacity)
        qp = QtGui.QPainter(self)
        qp.setPen(QtGui.QPen(QtGui.QColor('black'), line_width))
        qp.setBrush(QtGui.QColor(*fill_color))
        qp.drawRect(QtCore.QRectF(self.begin, self.end))

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Q, QtCore.Qt.Key_Escape):
            CaptureWidget.is_snipping = False
            self.close()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.begin = event.pos()
            self.end = self.begin
            self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        CaptureWidget.num_snip += 1
        CaptureWidget.is_snipping = False
        QtWidgets.QApplication.restoreOverrideCursor()

        x1 = min(self.begin.x(), self.end.x())
        y1 = min(self.begin.y(), self.end.y())
        x2 = max(self.begin.x(), self.end.x())
        y2 = max(self.begin.y(), self.end.y())

        if (x2 - x1) < 10 or (y2 - y1) < 10:
            self.close()
            return

        self.repaint()
        QtWidgets.QApplication.processEvents()
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))

        logger.info(f"Snip region: ({x1},{y1}) -> ({x2},{y2}), "
                     f"image size: {img.width}x{img.height}")

        # Save the full-quality screenshot for OCR
        save_path = Path(__file__).parent / "image1.png"
        img.save(str(save_path), format="png")

        self.close()

        # Hand off to detector -> OCR -> overlay pipeline
        detector.main(
            image_path=str(save_path),
            x1=x1, y1=y1, destination=self.destination,
            alpha=self.alpha, font_size=self.font_size,
            text_color=self.text_color,
        )


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setAttribute(Qt.AA_DisableHighDpiScaling, True)

    destination = sys.argv[1] if len(sys.argv) > 1 else "en"
    fill_color_hex = sys.argv[2] if len(sys.argv) > 2 else "#ff0000"
    opacity = float(sys.argv[3]) if len(sys.argv) > 3 else 0.3
    line_width = float(sys.argv[4]) if len(sys.argv) > 4 else 3
    alpha = float(sys.argv[5]) if len(sys.argv) > 5 else 0.7
    font_size = int(sys.argv[6]) if len(sys.argv) > 6 else 12
    text_color = sys.argv[7] if len(sys.argv) > 7 else "#000000"

    logger.info(f"capture.py starting: dest={destination}, "
                f"alpha={alpha}, font_size={font_size}, text_color={text_color}")

    widget = CaptureWidget(
        destination=destination, fill_color=fill_color_hex,
        opacity=opacity, line_width=line_width, alpha=alpha,
        font_size=font_size, text_color=text_color,
    )
    widget.start()
    sys.exit(app.exec_())
