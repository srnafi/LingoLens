import sys,os
from dotenv import load_dotenv, set_key
from io import BytesIO
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
import tkinter as tk
import pyautogui
from tkinter import filedialog
from PIL import ImageGrab
from PyQt5 import QtWidgets, QtCore, QtGui
from PIL import Image, ImageFilter
import text_detector_text
from pathlib import Path

class SnippingWidget(QtWidgets.QWidget):
    num_snip = 0
    is_snipping = False
    background = True

    def __init__(self, parent=None, callback=None, destination = None, alpha = None, font_size = None):
        super(SnippingWidget, self).__init__()
        self.parent = parent
        self.destination = destination
        self.alpha = alpha
        self.font_size = font_size
        self.callback = callback
        screen_width, screen_height = pyautogui.size()
        self.setGeometry(0, 0, screen_width, screen_height)
        self.begin = QtCore.QPoint()
        self.end = QtCore.QPoint()

    def start(self):
        # self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Window | Qt.WindowStaysOnTopHint)
        SnippingWidget.background = False
        SnippingWidget.is_snipping = True
        self.setWindowOpacity(0.3)
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.show()


    def paintEvent(self, event):
        if SnippingWidget.is_snipping:
            fill_color = (r, g, b, 100)
            opacity = float(op)
            line_width = float(lw)
        else:
            # reset points, so the rectangle won't show up again.
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
        if event.key() == QtCore.Qt.Key_Q:
            print('Quit')
            self.close()
        event.accept()

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        SnippingWidget.num_snip += 1
        SnippingWidget.is_snipping = False
        QtWidgets.QApplication.restoreOverrideCursor()
        x1 = min(self.begin.x(), self.end.x())
        y1 = min(self.begin.y(), self.end.y())
        x2 = max(self.begin.x(), self.end.x())
        y2 = max(self.begin.y(), self.end.y())

        self.repaint()
        QtWidgets.QApplication.processEvents()
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))

        dpi = 300  # Desired DPI
        scale_factor = dpi / 96  # Standard DPI (96) used by most screens
        new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
        img2 = img.resize(new_size, Image.NEAREST)

        # Apply a sharpening filter to enhance edges
        img2 = img2.filter(ImageFilter.SHARPEN)

        print(x1,y1)
        QtWidgets.QApplication.processEvents()
        self.close()

        selected_directory = Path(__file__).parent
        # save the image for text detection
        save_path = os.path.join(selected_directory, "image1.png")
        img.save(save_path,format="png")

        # directly call the text dector class after the snipping is done with the parameters
        text_detector_text.main(x1=x1, y1=y1, destination=self.destination, alpha=self.alpha, font_size = self.font_size)
        

def get_coordinates():
    global x1, y1
    return x1, y1

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # the source language, opacity of the window, border width, window fill color is provided as a commandline arugment

    destination = sys.argv[1]

    fill_color_hex = sys.argv[2]
    op = sys.argv[3]
    lw = sys.argv[4]

    alpha = sys.argv[5]
    font_size = sys.argv[6]

    # Convert the hex color directly to RGB using string slicing
    fill_color = fill_color_hex.lstrip('#')  # Remove the '#' if it exists
    r = int(fill_color[0:2], 16)  # First two characters (Red)
    g = int(fill_color[2:4], 16)  # Middle two characters (Green)
    b = int(fill_color[4:6], 16)  # Last two characters (Blue)
    #print(destination)
    snipping_widget = SnippingWidget(destination=destination,alpha=alpha,font_size=font_size)
    snipping_widget.start()
    sys.exit(app.exec_())

