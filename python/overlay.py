import sys
import os
import ctypes
import logging
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Set DPI awareness BEFORE any Qt imports
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel,
        QSizePolicy, QFrame)
from PyQt5.QtCore import (Qt, QPoint, QRect, QSize, QTimer, pyqtSignal,
        pyqtSlot)
from PyQt5.QtGui import (QPixmap, QPainter, QColor, QFont, QPen,
        QBrush, QImage, QPalette)

# Ensure path is set for imports
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from translator import translate_text

logger = logging.getLogger('overlay_qt')

FLASK_URL = "http://localhost:5000"
FLASK_HEALTH_TIMEOUT = 30


# ---------------------------------------------------------------------------
# OCR via Flask
# ---------------------------------------------------------------------------

def _wait_for_flask(timeout=FLASK_HEALTH_TIMEOUT):
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{FLASK_URL}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _run_ocr(folder_location):
    try:
        resp = requests.post(f"{FLASK_URL}/ocr",
                             json={'folder_location': folder_location},
                             timeout=120)
        if resp.status_code == 200:
            return resp.json()
        logger.error(f"OCR returned status {resp.status_code}")
        return {}
    except Exception as e:
        logger.error(f"OCR request failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# OCR result parsing & grouping
# ---------------------------------------------------------------------------

def _parse_ocr_results(ocr_results):
    """Parse OCR {coords_str: text} into structured word dicts."""
    words = []
    for coords_str, text in ocr_results.items():
        parts = coords_str.split(',')
        if len(parts) != 4:
            continue
        x_min, x_max, y_min, y_max = map(int, parts)
        words.append({
            'text': text.strip(),
            'x_min': x_min, 'x_max': x_max,
            'y_min': y_min, 'y_max': y_max,
            'cx': (x_min + x_max) / 2,
            'cy': (y_min + y_max) / 2,
            'width': x_max - x_min,
            'height': y_max - y_min,
        })
    return [w for w in words if w['text']]


def _group_words_into_lines(words):
    if not words:
        return []
    words.sort(key=lambda w: (w['cy'], w['cx']))
    lines = [[words[0]]]
    for word in words[1:]:
        line = lines[-1]
        avg_cy = sum(w['cy'] for w in line) / len(line)
        avg_h = sum(w['height'] for w in line) / len(line)
        if abs(word['cy'] - avg_cy) < avg_h * 0.5:
            lines[-1].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda w: w['cx'])
    return lines


def _group_lines_into_paragraphs(lines):
    if not lines:
        return []
    paragraphs = [[lines[0]]]
    for i in range(1, len(lines)):
        prev = lines[i - 1]
        curr = lines[i]
        prev_y_max = max(w['y_max'] for w in prev)
        curr_y_min = min(w['y_min'] for w in curr)
        prev_h = max(w['y_max'] for w in prev) - min(w['y_min'] for w in prev)
        curr_h = max(w['y_max'] for w in curr) - min(w['y_min'] for w in curr)
        avg_h = (prev_h + curr_h) / 2
        gap = curr_y_min - prev_y_max
        if gap < avg_h * 1.2:
            paragraphs[-1].append(curr)
        else:
            paragraphs.append([curr])
    return paragraphs


def _line_bbox(line_words):
    return (min(w['x_min'] for w in line_words),
            min(w['y_min'] for w in line_words),
            max(w['x_max'] for w in line_words),
            max(w['y_max'] for w in line_words))


def _estimate_font_size(words):
    if not words:
        return 12
    heights = sorted(w['height'] for w in words)
    median_h = heights[len(heights) // 2]
    return max(8, int(median_h * 0.75))


# ---------------------------------------------------------------------------
# Background reconstruction using OpenCV
# ---------------------------------------------------------------------------

def _reconstruct_background(capture_img, text_regions):
    """Remove source text from captured image by inpainting.

    Parameters
    ----------
    capture_img : np.ndarray
        BGR image from the snipped region.
    text_regions : list of dict
        Each dict has 'x_min', 'x_max', 'y_min', 'y_max' in capture-relative coords.

    Returns
    -------
    np.ndarray
        Image with source text regions replaced by reconstructed background.
    """
    import numpy as np
    import cv2
    img = capture_img.copy()
    for reg in text_regions:
        x1, y1, x2, y2 = reg['x_min'], reg['y_min'], reg['x_max'], reg['y_max']
        exp = max(1, int(min(reg['width'], reg['height']) * 0.15))
        x1e, y1e = max(0, x1 - exp), max(0, y1 - exp)
        x2e, y2e = min(capture_img.shape[1], x2 + exp), min(capture_img.shape[0], y2 + exp)
        if x2e > x1e and y2e > y1e:
            mask = np.zeros(img.shape[:2], dtype=np.uint8)
            cv2.rectangle(mask, (x1e, y1e), (x2e, y2e), 255, -1)
            img = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
    return img


# ---------------------------------------------------------------------------
# Main overlay window using PyQt5 image compositing
# ---------------------------------------------------------------------------

class OverlayWindow(QWidget):
    """Single transparent overlay window displaying translated screen region.

    The window exactly matches the snipped region's position and dimensions.
    Inside, a composite image is shown: original background with source text
    regions removed (via OpenCV inpainting), and translated text drawn at
    source-relative positions.
    """

    def __init__(self, screen_x, screen_y, snip_width, snip_height,
                 alpha=0.9, text_color="#000000"):
        super().__init__()

        self.screen_x = int(screen_x)
        self.screen_y = int(screen_y)
        self.snip_width = max(1, int(snip_width))
        self.snip_height = max(1, int(snip_height))
        self.alpha = float(alpha)
        self.text_color = QColor(text_color)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.resize(self.snip_width, self.snip_height)
        self.move(self.screen_x, self.screen_y)

        self._pixmap = QPixmap(self.snip_width, self.snip_height)
        self._pixmap.fill(Qt.transparent)

        self.setPalette(Qt.black)
        self.setAutoFillBackground(False)

        self._init_timer = QTimer()
        self._init_timer.timeout.connect(self._ensure_paint)
        self._init_timer.start(50)

    def _ensure_paint(self):
        self._init_timer.stop()
        self.update()

    def update_overlay(self, screen_x, screen_y, capture_img,
                       ocr_words, paragraphs, translated,
                       est_font_size, font_size_override):
        """Update the overlay with new translation data.

        Parameters
        ----------
        screen_x, screen_y : int
            Top-left of snipped region on screen.
        capture_img : np.ndarray
            BGR image from the snipped region (height x width x 3).
        ocr_words : list[dict]
            Parsed OCR words with 'x_min','y_min','x_max','y_max','text'.
        paragraphs : list[list[dict]]
            Grouped paragraphs, each a list of word dicts.
        translated : dict
            {para_idx: translated_text}
        est_font_size : int
            Estimated source font size from OCR geometry.
        font_size_override : int
            User-specified font size (preferred over est).
        """
        self.screen_x = int(screen_x)
        self.screen_y = int(screen_y)
        self.resize(max(1, self.snip_width), max(1, self.snip_height))
        self.move(self.screen_x, self.screen_y)

        # ---- 1. Reconstruct background: remove source text ----
        try:
            import numpy as np
            import cv2
        except Exception as e:
            logger.error(f"OpenCV not available: {e}")
            painter = QPainter(self._pixmap)
            painter.setPen(self.text_color)
            painter.setFont(QFont("fixedsys", max(est_font_size, font_size_override)))
            painter.drawText(self._pixmap.rect(), Qt.AlignLeft, "OCR unavailable")
            painter.end()
            self.update()
            return

        img_bgr = capture_img.copy()
        regions = []
        for w in ocr_words:
            regions.append({
                'x_min': w['x_min'], 'y_min': w['y_min'],
                'x_max': w['x_max'], 'y_max': w['y_max'],
            })

        img_recon = _reconstruct_background(img_bgr, regions)

        img_rgb = cv2.cvtColor(img_recon, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        bytes_per_line = ch * w

        qimg = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pm = QPixmap.fromImage(qimg)

        # ---- 2. Render translated text onto the pixmap ----
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        use_font_size = max(int(est_font_size), int(font_size_override))

        for p_idx, para_lines in enumerate(paragraphs):
            all_w = [w for line in para_lines for w in line]
            if not all_w:
                continue
            px_min = min(w['x_min'] for w in all_w)
            py_min = min(w['y_min'] for w in all_w)
            px_max = max(w['x_max'] for w in all_w)
            py_max = max(w['y_max'] for w in all_w)

            t_text = translated.get(p_idx, "")
            if not t_text:
                t_text = ' '.join(w['text'] for w in all_w)

            dx = px_min
            dy = py_min

            font = QFont("fixedsys", use_font_size)

            outline_pen = QPen(self.text_color.darker(150), 2)
            painter.setPen(outline_pen)
            painter.setFont(font)
            painter.drawText(dx, dy, t_text)

            painter.setPen(self.text_color)
            painter.drawText(dx + 1, dy + 1, t_text)

        painter.end()

        self._pixmap = pm
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.end()

    def mousePressEvent(self, event):
        pass

    def mouseDoubleClickEvent(self, event):
        self.close()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def show_translations(screen_x, screen_y, dest, alpha, font_size,
                      text_color="#000000"):
    """Full pipeline: capture → OCR → group → translate → composite overlay.

    Creates ONE transparent overlay window exactly matching the snipped region.
    All translated text is drawn at source-relative positions on a reconstructed
    background (source text removed via OpenCV inpainting, background preserved).
    """
    screen_x = int(screen_x)
    screen_y = int(screen_y)
    alpha = float(alpha)
    font_size = int(font_size)

    logger.info(f"show_translations: screen=({screen_x},{screen_y}), "
                f"dest={dest}, alpha={alpha}, font_size={font_size}")

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if not _wait_for_flask():
        logger.error("Flask OCR server not ready")
        return

    crops_folder = _this_dir / "crops"
    if not crops_folder.exists():
        logger.error("Crops folder not found")
        return

    ocr_results = _run_ocr(str(crops_folder))
    if not ocr_results:
        logger.warning("No OCR results from Flask")
        return

    words = _parse_ocr_results(ocr_results)
    if not words:
        logger.warning("No valid OCR words")
        return

    lines = _group_words_into_lines(words)
    paragraphs = _group_lines_into_paragraphs(lines)
    est_font = _estimate_font_size(words)

    logger.info(f"Grouped: {len(words)} words → {len(lines)} lines → {len(paragraphs)} paragraphs")

    # Translate each paragraph (parallel)
    def translate_para(idx, para):
        text = ' '.join(w['text'] for w in para)
        return idx, translate_text(text, dest)

    translated = {}
    n_workers = min(8, len(paragraphs) + 1)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(translate_para, i, para)
                   for i, para in enumerate(paragraphs)]
        for f in as_completed(futures):
            idx, text = f.result()
            translated[idx] = text

    # Determine snip image for background reconstruction
    import numpy as np
    from PIL import Image
    capture_path = str(_this_dir / "image1.png")
    if not os.path.exists(capture_path):
        logger.error("No captured image (image1.png not found). Run a snip first.")
        return

    capture_pil = Image.open(capture_path).convert("RGB")
    capture_np = np.array(capture_pil)  # RGB
    capture_bgr = cv2.cvtColor(capture_np, cv2.COLOR_RGB2BGR)

    # Determine snip dimensions from OCR word bounding boxes
    all_x_min = min(w['x_min'] for w in words)
    all_y_min = min(w['y_min'] for w in words)
    all_x_max = max(w['x_max'] for w in words)
    all_y_max = max(w['y_max'] for w in words)

    snip_w = max(1, all_x_max - all_x_min + 40)
    snip_h = max(1, all_y_max - all_y_min + 40)

    overlay = OverlayWindow(screen_x, screen_y, snip_w, snip_h,
                            alpha=alpha, text_color=text_color)

    use_font = max(est_font, font_size)

    overlay.update_overlay(
        screen_x=screen_x,
        screen_y=screen_y,
        capture_img=capture_bgr,
        ocr_words=words,
        paragraphs=paragraphs,
        translated=translated,
        est_font_size=est_font,
        font_size_override=font_size,
    )

    overlay.show()

    def dismiss(event=None):
        try:
            overlay.close()
        except Exception:
            pass
    overlay.installEventFilter(_DismissFilter(overlay))


class _DismissFilter:
    def __init__(self, widget):
        self.widget = widget

    def eventFilter(self, obj, event):
        if event.type() == 17:
            if event.button() == Qt.LeftButton:
                self.widget.close()
        return False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = OverlayWindow(100, 100, 800, 600, alpha=0.9, text_color="#ffffff")
    w.show()
    sys.exit(app.exec_())