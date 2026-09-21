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

import cv2
import numpy as np

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


# ---------------------------------------------------------------------------
# Pure crop-maths helper (spec section 10, P4 gate: unit test for cropping).
#
# The snip rectangle is (x1, y1) -> (x2, y2) in screen coordinates. The frozen
# full-screen image is a PIL.Image in screen coordinates. Cropping must yield
# an image whose width == x2 - x1 and height == y2 - y1.
# ---------------------------------------------------------------------------
def crop_from_frozen(frozen_img, x1, y1, x2, y2):
    """Crop a region from the freeze-frame image.

    Parameters
    ----------
    frozen_img : PIL.Image
        The full-screen frozen capture, in screen coordinates.
    x1, y1, x2, y2 : int
        Screen-coordinate rectangle (left, top, right, bottom).

    Returns
    -------
    PIL.Image
        The cropped region, guaranteed to have width == x2 - x1 and
        height == y2 - y1.
    """
    snip_w = x2 - x1
    snip_h = y2 - y1
    # PIL.Image.crop takes (left, top, right, bottom) and clamps to image bounds.
    img = frozen_img.crop((x1, y1, x2, y2))
    return img


def compute_snip_dims(x1, y1, x2, y2):
    """Return (width, height) of a snip rectangle in physical pixels.

    Used by the P4 crop-maths unit test. Pure function, no Qt/PIL needed.
    """
    return (x2 - x1, y2 - y1)


class CaptureWidget(QtWidgets.QWidget):
    """Full-screen transparent overlay for region selection.

    Freeze-frame capture (defect 8 fix): the screen is grabbed ONCE before the
    selection UI is shown. The frozen image is painted as a dimmed background
    so the user sees what they are selecting, and the final snip is cropped
    from the frozen image -- never from a fresh ImageGrab that might catch the
    tinted selection window itself.
    """
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

        # Freeze-frame: grab the screen NOW, before showing the selection UI,
        # so the tinted selection overlay can never contaminate the capture.
        self._frozen_img = None  # PIL.Image, full screen, in screen coordinates
        self._frozen_cv = None   # numpy BGR array of the frozen frame (for regrab diagnostic)

    def start(self):
        """Freeze the screen, then show the selection widget over it."""
        # AA_DisableHighDpiScaling must be set on the QApplication before any
        # widget is shown so Qt logical pixels == ImageGrab physical pixels.
        app = QApplication.instance()
        if app is not None:
            app.setAttribute(Qt.AA_DisableHighDpiScaling, True)

        # Freeze-frame capture: grab the screen BEFORE the selection UI is
        # visible, so the tinted overlay cannot tint the sampled background.
        try:
            self._frozen_img = ImageGrab.grab(bbox=(0, 0, self.width(), self.height()))
            self._frozen_cv = cv2.cvtColor(np.array(self._frozen_img), cv2.COLOR_RGB2BGR)
            logger.info(f"Freeze-frame capture: {self._frozen_img.width}x{self._frozen_img.height}")
        except Exception as e:
            logger.error(f"Freeze-frame grab failed: {e}")
            # Fall back to a solid image so the pipeline doesn't crash
            self._frozen_img = Image.new("RGB", (self.width(), self.height()), (0, 0, 0))
            self._frozen_cv = np.array(self._frozen_img)[:, :, ::-1]

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

        # Paint the frozen (dimmed) screen as the background so the user sees
        # what they are selecting, without the tinted overlay contaminating it.
        if self._frozen_img is not None:
            arr = np.array(self._frozen_img)  # RGB uint8
            h_img, w_img, _ = arr.shape
            qimg = QtGui.QImage(arr.data, w_img, h_img, w_img * 3,
                                QtGui.QImage.Format_RGB888).copy()
            qp.drawPixmap(0, 0, self.width(), self.height(), QtGui.QPixmap.fromImage(qimg))
            # Dim overlay: semi-transparent black brush over the frozen image
            dim = QtGui.QColor(0, 0, 0, 80)
            qp.setBrush(dim)
            qp.drawRect(0, 0, self.width() - 1, self.height() - 1)
            qp.setBrush(QtGui.QColor(*fill_color))

        qp.setPen(QtGui.QPen(QtGui.QColor('black'), line_width))
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

        # Crop the snip from the FREEZE-FRAME image (grabbed before the
        # selection UI was shown), NOT from a fresh ImageGrab that could
        # catch the tinted selection window. (defect 8 fix)
        if self._frozen_img is not None:
            img = self._frozen_img.crop((x1, y1, x2, y2))
            cropped_from_frozen = True
        else:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            cropped_from_frozen = False

        # Spec section 3: assert captured image dimensions == snip dimensions.
        # In physical pixels (DPR 1.0), width == x2 - x1 and height == y2 - y1.
        snip_w = x2 - x1
        snip_h = y2 - y1
        if img.width != snip_w or img.height != snip_h:
            logger.warning(
                f"Dimension mismatch: snip=({snip_w},{snip_h}), "
                f"capture=({img.width},{img.height}) -- DPI scaling issue?")

        logger.info(f"Snip region: ({x1},{y1}) -> ({x2},{y2}), "
                     f"image size: {img.width}x{img.height}, "
                     f"frozen={cropped_from_frozen}")

        # Diagnostic: in debug mode, 300ms after closing the selection window,
        # re-grab the same bbox and log the mean absolute difference per channel.
        # Must be < 2.0 per channel unless the screen actually changed.
        do_regab = os.environ.get("LINGOLENS_DEBUG", "") == "1"
        self.close()

        if do_regab and self._frozen_cv is not None:
            QtCore.QTimer.singleShot(300, lambda: self._regab_diagnostic(
                x1, y1, x2, y2))

        # Save the full-quality screenshot for OCR
        save_path = Path(__file__).parent / "image1.png"
        img.save(str(save_path), format="png")

        # Hand off to detector -> OCR -> overlay pipeline
        detector.main(
            image_path=str(save_path),
            x1=x1, y1=y1, destination=self.destination,
            alpha=self.alpha, font_size=self.font_size,
            text_color=self.text_color,
        )

    def _regab_diagnostic(self, x1, y1, x2, y2):
        """Re-grab the same bbox 300ms after selection and compare to the
        frozen frame. If the screen didn't change, the mean absolute per-channel
        difference should be < 2.0 (spec section 10, P4 gate).

        This catches: tinted selection window still composited, DPI scaling
        mismatches, or screen content changed during capture.
        """
        try:
            regrab = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            regrab_arr = cv2.cvtColor(np.array(regrab), cv2.COLOR_RGB2BGR)
            frozen_crop = self._frozen_cv[y1:y2, x1:x2]
            # Align sizes (can differ by 1px due to rounding)
            h = min(regrab_arr.shape[0], frozen_crop.shape[0])
            w = min(regrab_arr.shape[1], frozen_crop.shape[1])
            if h > 0 and w > 0:
                diff = np.abs(
                    regrab_arr[:h, :w].astype(np.int32) -
                    frozen_crop[:h, :w].astype(np.int32)
                )
                per_channel = diff.reshape(-1, 3).mean(axis=0)
                overall = float(diff.mean())
                logger.info(
                    f"Regrab diagnostic: region=({x1},{y1})->({x2},{y2}) "
                    f"mean_abs_diff={overall:.2f} per_channel={per_channel.round(2).tolist()} "
                    f"(threshold < 2.0 per channel)")
        except Exception as e:
            logger.warning(f"Regrab diagnostic failed: {e}")


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
