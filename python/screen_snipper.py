import sys
import os
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
import pyautogui
from PIL import Image, ImageGrab, ImageFilter
from PyQt5 import QtWidgets, QtCore, QtGui
from pathlib import Path
import text_detector_text


class SnippingWidget(QtWidgets.QWidget):
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

        # Parse fill color from hex string
        self.fill_color_rgb = (255, 0, 0, 100)  # default red
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
        self.setGeometry(0, 0, screen_width, screen_height)
        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()

    def start(self):
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Window |
            Qt.WindowStaysOnTopHint
        )
        SnippingWidget.is_snipping = True
        self.setWindowOpacity(self.opacity_val)
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.show()
        self.activateWindow()

    def paintEvent(self, event):
        if SnippingWidget.is_snipping:
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
        rect = QtCore.QRectF(self.begin, self.end)
        qp.drawRect(rect)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Q, QtCore.Qt.Key_Escape):
            print('Snipping cancelled')
            SnippingWidget.is_snipping = False
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
        SnippingWidget.num_snip += 1
        SnippingWidget.is_snipping = False
        QtWidgets.QApplication.restoreOverrideCursor()

        x1 = min(self.begin.x(), self.end.x())
        y1 = min(self.begin.y(), self.end.y())
        x2 = max(self.begin.x(), self.end.x())
        y2 = max(self.begin.y(), self.end.y())

        # Ignore tiny selections (accidental clicks)
        if (x2 - x1) < 10 or (y2 - y1) < 10:
            print("Selection too small, ignoring")
            self.close()
            return

        self.repaint()
        QtWidgets.QApplication.processEvents()
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))

        # Upscale for better OCR quality
        dpi = 300
        scale_factor = dpi / 96
        new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
        try:
            resample = Image.Resampling.NEAREST
        except AttributeError:
            resample = Image.NEAREST
        img2 = img.resize(new_size, resample)
        img2 = img2.filter(ImageFilter.SHARPEN)

        print(f"Snip captured at ({x1}, {y1})")
        QtWidgets.QApplication.processEvents()
        self.close()

        selected_directory = Path(__file__).parent
        save_path = os.path.join(selected_directory, "image1.png")
        img.save(save_path, format="png")

        text_detector_text.main(
            x1=x1, y1=y1, destination=self.destination,
            alpha=self.alpha, font_size=self.font_size,
            text_color=self.text_color,
        )


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Args: destination, fill_color_hex, opacity, line_width, alpha, font_size, [text_color]
    destination = sys.argv[1] if len(sys.argv) > 1 else "en"
    fill_color_hex = sys.argv[2] if len(sys.argv) > 2 else "#ff0000"
    opacity = sys.argv[3] if len(sys.argv) > 3 else "0.3"
    line_width = sys.argv[4] if len(sys.argv) > 4 else "3"
    alpha = sys.argv[5] if len(sys.argv) > 5 else "0.7"
    font_size = sys.argv[6] if len(sys.argv) > 6 else "12"
    text_color = sys.argv[7] if len(sys.argv) > 7 else "#000000"

    snipping_widget = SnippingWidget(
        destination=destination,
        fill_color=fill_color_hex,
        opacity=opacity,
        line_width=line_width,
        alpha=alpha,
        font_size=font_size,
        text_color=text_color,
    )
    snipping_widget.start()
    sys.exit(app.exec_())
