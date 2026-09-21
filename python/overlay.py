import sys
import os
import ctypes
import logging
import logging.handlers
import requests
import time
import cv2
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

from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget

# Ensure path is set for imports
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from translator import translate_text
import blocks as _blocks
from blocks import (
    group_words_into_lines,
    group_lines_into_blocks,
    build_blocks,
    BlockRecord,
    MIN_WORD_PIXELS,
)

logger = logging.getLogger('lingolens')

# Debug dump support (writes artifacts when LINGOLENS_DEBUG=1)
import debug_dump

# ---------------------------------------------------------------------------
# Module-level registry of live overlays (defect 1 fix).
# The overlay is kept alive here until the user dismisses it, preventing
# Python garbage-collection of the parentless top-level widget.
# ---------------------------------------------------------------------------
_OVERLAYS = []

# ---------------------------------------------------------------------------
# Debug helpers (defect: add debug outline mode + file logging)
# ---------------------------------------------------------------------------
LOGS_DIR = _this_dir / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

_DEBUG_OUTLINE = os.environ.get("LINGOLENS_DEBUG_OUTLINE", "") == "1"

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
#
# Grouping logic now lives in python/blocks.py (pure, headless-testable).
# The wrappers below are kept so existing imports from overlay (e.g.
# python/test_overlay.py) continue to work.  New code should call blocks.*
# directly.
# ---------------------------------------------------------------------------
def _parse_ocr_results(ocr_results):
    """Parse OCR {coords_str: text} into structured word dicts.

    Flask contract: key = "x_min,x_max,y_min,y_max", value = recognised text.
    """
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
    # Filter: drop words whose text has no letters or digits (spec 5.1:
    # icons recognised as |, O, ~, etc. are not repainted or removed.)
    import re
    _has_alnum = re.compile(r'[A-Za-z0-9]')
    return [w for w in words if w['text'] and _has_alnum.search(w['text'])]


# Backward-compatible wrappers -- delegate to blocks.py (spec section 5)
def _group_words_into_lines(words):
    """Back-compat: delegate to blocks.group_words_into_lines."""
    return _blocks.group_words_into_lines(words)


def _group_lines_into_paragraphs(lines):
    """Back-compat: delegate to blocks.group_lines_into_blocks."""
    return _blocks.group_lines_into_blocks(lines)


def _line_bbox(line_words):
    return _blocks._bbox_of(line_words)


def _paragraph_bbox(para_lines):
    all_w = [w for ln in para_lines for w in ln]
    return _blocks._bbox_of(all_w)


def _estimate_font_size(words):
    """Back-compat: estimate font size from word heights (floor 9)."""
    return _blocks._estimate_font_size(words)


# ---------------------------------------------------------------------------
# Text color extraction: derive foreground colour from source glyph pixels
# with a WCAG contrast guard so text is always readable on any background
# (fixes defect 3: black text on black backgrounds).
# ---------------------------------------------------------------------------
def _luminance(bgr):
    """Relative luminance of a BGR pixel (0.0 = black, 1.0 = white).

    Uses the standard sRGB luminance formula. Input is a BGR triple (0-255).
    """
    b, g, r = bgr[0] / 255.0, bgr[1] / 255.0, bgr[2] / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg_bgr, bg_bgr):
    """WCAG contrast ratio between two BGR colors (1.0 = no contrast, 21 = max)."""
    l1 = _luminance(fg_bgr)
    l2 = _luminance(bg_bgr)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    if lighter == 0 and darker == 0:
        return 1.0
    return (lighter + 0.05) / (darker + 0.05)


def _bgr_to_qcolor(bgr):
    """Convert a BGR tuple (0-255) to a PyQt5 QColor."""
    from PyQt5.QtGui import QColor
    return QColor(int(bgr[2]), int(bgr[1]), int(bgr[0]))  # Qt uses RGB order


def _sample_text_color(capture_bgr, words):
    """Derive the text color from source glyph pixels.

    Per spec section 7.2: sample a 4px ring OUTSIDE the text region for the
    background, then sample glyph pixels (those deviating from the background
    by more than 28) inside the region for the foreground. Enforce WCAG
    contrast >= 4.5; if not met or if no glyphs are detectable, use black on
    light bg or white on dark bg.
    """
    import numpy as np
    if not words:
        from PyQt5.QtGui import QColor
        return QColor(0, 0, 0)

    h_img, w_img = capture_bgr.shape[:2]

    # Union of all word boxes for this region.
    xs0 = [w['x_min'] for w in words]
    ys0 = [w['y_min'] for w in words]
    xs1 = [w['x_max'] for w in words]
    ys1 = [w['y_max'] for w in words]
    x0 = max(0, min(xs0))
    y0 = max(0, min(ys0))
    x1 = min(w_img, max(xs1))
    y1 = min(h_img, max(ys1))
    if x1 <= x0 or y1 <= y0:
        from PyQt5.QtGui import QColor
        return QColor(0, 0, 0)

    # Sample the 4px ring outside the box for the background.
    RING = 4
    rx0 = max(0, x0 - RING)
    ry0 = max(0, y0 - RING)
    rx1 = min(w_img, x1 + RING)
    ry1 = min(h_img, y1 + RING)
    if rx1 > rx0 and ry1 > ry0:
        ring = capture_bgr[ry0:ry1, rx0:rx1]
        bg_median = np.median(ring.reshape(-1, 3), axis=0)
    else:
        bg_median = np.array([128, 128, 128], dtype=np.float64)

    # Glyph pixels: those that deviate from the background by more than 28.
    region = capture_bgr[y0:y1, x0:x1].astype(np.float32)
    flat = region.reshape(-1, 3)
    dist = np.linalg.norm(flat - bg_median, axis=1)
    glyph = flat[dist > 28]

    bg_lum = _luminance(bg_median.astype(np.uint8))

    if glyph.size == 0:
        # No detectable glyphs via the ring-based background. The ring may be
        # contaminated by adjacent text, so fall back to the global image
        # median as a more robust background estimate.
        global_median = np.median(capture_bgr.reshape(-1, 3), axis=0)
        global_lum = _luminance(global_median.astype(np.uint8))
        if global_lum > 0.4:
            # Light background: use dark text.
            return _bgr_to_qcolor(np.array([30, 30, 30]))
        else:
            # Dark background: use light text.
            return _bgr_to_qcolor(np.array([225, 225, 225]))

    fg_median = np.median(glyph, axis=0)
    fg_bgr = fg_median.astype(np.uint8)
    bg_bgr = bg_median.astype(np.uint8)

    contrast = _contrast_ratio(fg_bgr, bg_bgr)
    if contrast < 4.5:
        # Not readable: use black on light bg, white on dark bg.
        if bg_lum > 0.4:
            fg_bgr = np.array([0, 0, 0])
        else:
            fg_bgr = np.array([255, 255, 255])

    return _bgr_to_qcolor(fg_bgr)


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Background reconstruction using OpenCV
# ---------------------------------------------------------------------------

def _reconstruct_background(capture_img, text_regions):
    """Remove source text from captured image by inpainting.

    Delegates to blend.py: ring-median fill for flat backgrounds, ONE inpaint
    call over all textured glyph masks (spec section 7.1).

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
    import blend

    # Convert BGR to RGB (blend.py works in RGB to match Qt)
    capture_rgb = capture_img[:, :, ::-1].copy()
    boxes = [(r['x_min'], r['y_min'], r['x_max'], r['y_max']) for r in text_regions]
    removed_rgb, _infos = blend.remove_text(capture_rgb, boxes)
    # Convert back to BGR for callers that expect BGR
    return removed_rgb[:, :, ::-1].copy()


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

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self.resize(self.snip_width, self.snip_height)
        self.move(self.screen_x, self.screen_y)

        self._pixmap = QPixmap(self.snip_width, self.snip_height)
        self._pixmap.fill(Qt.transparent)

    def set_overlay_rgba(self, rgba_img):
        """Set the overlay pixmap from a pre-computed RGBA image.

        The RGBA image (HxWx4, uint8) is fully transparent except over patches
        (spec section 7.7). The pixmap is set to snip dimensions.
        """
        from PyQt5.QtGui import QPixmap
        h, w = rgba_img.shape[:2]
        bytes_per_line = w * 4
        qimg = QImage(rgba_img.data, w, h, bytes_per_line,
                      QImage.Format_RGBA8888).copy()
        pm = QPixmap.fromImage(qimg)
        self._pixmap = pm
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        # SourceOver blends the RGBA image onto the widget, respecting the
        # alpha channel. Pixels with alpha=0 (outside patches) stay transparent
        # and the live screen shows through. Pixels with alpha>255 show the
        # patch content (text-removed bg + translation).
        # (spec section 7.2: outside patches the live screen shows through)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.end()

        if _DEBUG_OUTLINE:
            p = QPainter(self)
            p.setPen(QColor(0, 255, 255))
            p.drawRect(0, 0, self.snip_width - 1, self.snip_height - 1)
            p.end()

    def mousePressEvent(self, event):
        """Any mouse button dismisses the overlay (defect 6 fix)."""
        self._dismiss()

    def keyPressEvent(self, event):
        """Esc or Q dismisses the overlay (defect 6 fix)."""
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self._dismiss()

    def _dismiss(self):
        if self in _OVERLAYS:
            _OVERLAYS.remove(self)
        self.close()


# ---------------------------------------------------------------------------
# Debug artifact writer (called when LINGOLENS_DEBUG=1)
# ---------------------------------------------------------------------------

def _write_debug_artifacts(dbg, overlay, capture_bgr, words, block_records,
                           translated, screen_x, screen_y, snip_w, snip_h,
                           rgba_overlay=None, placements=None, blend_metrics=None):
    """Write all debug artifacts to the dump directory."""
    import numpy as np
    import cv2

    # capture.png
    dbg.write_capture(capture_bgr)

    # boxes.png -- detections drawn on capture
    dbg.write_boxes_png(capture_bgr,
                        [[w['x_min'], w['y_min'], w['x_max'], w['y_max']] for w in words])

    # blocks.json + blocks.png
    blocks_data = []
    for blk in block_records:
        x1, y1, x2, y2 = blk.bbox
        blocks_data.append({
            "index": block_records.index(blk),
            "text": blk.text,
            "bbox": [x1, y1, x2, y2],
            "n_lines": blk.n_lines,
            "n_words": blk.n_words,
            "src_px": blk.src_px,
        })
    # Build the paragraphs-like structure for write_blocks/write_blocks_png
    # which expect list[list[list[dict]]]
    para_lines_list = [blk.lines for blk in block_records]
    dbg.write_blocks(para_lines_list, words)
    dbg.write_blocks_png(capture_bgr, para_lines_list, words)

    # removed.png -- capture with text removed
    regions = [{'x_min': w['x_min'], 'y_min': w['y_min'],
                'x_max': w['x_max'], 'y_max': w['y_max'],
                'width': w['width'], 'height': w['height']} for w in words]
    removed = _reconstruct_background(capture_bgr, regions)
    dbg.write_removed(removed)

    # overlay_rgba.png -- extract from the QPixmap
    pixmap = overlay._pixmap
    rgba_img = _pixmap_to_rgba(pixmap)
    dbg.write_overlay(rgba_img)

    # composite.png
    dbg.write_composite(capture_bgr, rgba_img)

    # Write overlay_rgba.png and removed.png if blend rendered them
    import numpy as np
    import cv2
    import blend
    if rgba_overlay is not None:
        from PIL import Image
        rgba_path = dbg.dir / "overlay_rgba.png"
        Image.fromarray(rgba_overlay, "RGBA").save(str(rgba_path))

    # removed.png: source text removed (reconstructed background)
    removed_path = dbg.dir / "removed.png"
    try:
        removed, _ = blend.remove_text(
            capture_bgr[:, :, ::-1].copy(),
            [tuple(int(v) for v in blk.bbox) for blk in block_records])
        cv2.imwrite(str(removed_path), removed[:, :, ::-1])
    except Exception as e:
        logger.debug(f"Could not write removed.png: {e}")

    # Also write composite.png: capture with translated overlay blended on
    composite_path = dbg.dir / "composite.png"
    try:
        if rgba_overlay is not None:
            comp = blend.composite(capture_bgr[:, :, ::-1].copy(), rgba_overlay)
            cv2.imwrite(str(composite_path), comp[:, :, ::-1])
    except Exception as e:
        logger.debug(f"Could not write composite.png: {e}")

    # metrics.json
    metrics = {
        "counts": {
            "words": len(words),
            "lines": sum(len(blk.lines) for blk in block_records),
            "blocks": len(block_records),
        },
        "blocks": blocks_data,
        "pixels_changed_outside_patches": (
            blend_metrics["pixels_changed_outside_patches"]
            if blend_metrics else 0
        ),
        "placements": (
            [
                {
                    "block_index": p.block_index,
                    "font_px": p.font_px,
                    "src_px": p.src_px,
                    "contrast": p.contrast,
                    "fits": p.fits,
                    "busy": p.busy,
                    "p99_bg_dist": p.p99_bg_dist,
                    "alignment": p.alignment,
                    "rtl": p.rtl,
                }
                for p in placements
            ]
            if placements else []
        ),
        "window_geometry": {"x": screen_x, "y": screen_y,
                            "width": snip_w, "height": snip_h},
    }
    dbg.write_metrics(metrics)

    # env.json
    try:
        from PyQt5.QtWidgets import QApplication
        dpr = QApplication.primaryScreen().devicePixelRatio()
        try:
            screen = QApplication.primaryScreen()
            screen_size = screen.size()
            screen_size = (screen_size.width(), screen_size.height())
        except Exception:
            screen_size = None
    except Exception:
        dpr = None
        screen_size = None
    dbg.write_env(screen_size=screen_size, device_pixel_ratio=dpr)


def _pixmap_to_rgba(pixmap):
    """Convert a QPixmap to an HxWx4 uint8 RGBA numpy array."""
    import numpy as np
    qimg = pixmap.toImage()
    # Convert to ARGB32
    qimg = qimg.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    h, w = qimg.height(), qimg.width()
    ptr = qimg.bits()
    ptr.setsize(h * w * 4)
    arr = np.array(ptr).reshape(h, w, 4)
    # Qt stores as BGRA, convert to RGBA
    return arr[:, :, [2, 1, 0, 3]].copy()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def show_translations(screen_x, screen_y, dest, alpha, font_size,
                      text_color="#000000", image_path=None):
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

    dbg = debug_dump.DebugDump() if debug_dump.is_debug() else None
    if dbg:
        dbg.stage("wait_for_flask")

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if not _wait_for_flask():
        logger.error("Flask OCR server not ready")
        _quit_and_return()
        return

    crops_folder = _this_dir / "crops"
    if not crops_folder.exists():
        logger.error("Crops folder not found")
        _quit_and_return()
        return

    ocr_results = _run_ocr(str(crops_folder))
    if not ocr_results:
        logger.warning("No OCR results from Flask")
        _quit_and_return()
        return

    words = _parse_ocr_results(ocr_results)
    if not words:
        logger.warning("No valid OCR words")
        _quit_and_return()
        return

    # Group into blocks (translation units) via blocks.py (spec section 6).
    block_records = _blocks.build_blocks(words)
    est_font = _blocks._estimate_src_px(words)

    lines = _group_words_into_lines(words)
    logger.info(f"Grouped: {len(words)} words -> {len(lines)} lines -> "
                f"{len(block_records)} blocks")

    # Translate each block (parallel).  Use the space-joined text from the
    # block record; fall back to CJK-aware joining if text is empty.
    def translate_block(idx, block):
        text = block.text if block.text else ' '.join(w['text'] for ln in block.lines for w in ln)
        return idx, translate_text(text, dest)

    translated = {}
    n_workers = min(8, len(block_records) + 1)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(translate_block, i, blk)
                   for i, blk in enumerate(block_records)]
        for f in as_completed(futures):
            idx, text = f.result()
            translated[idx] = text

    if dbg:
        dbg.stage("translate")
        dbg.write_translations(translated)

    # Load captured image -- use actual image dimensions for window geometry
    # (NOT OCR box extents + 40). (defect 2 fix)
    import numpy as np
    from PIL import Image
    import blend
    capture_path = image_path or str(_this_dir / "image1.png")
    if not os.path.exists(capture_path):
        logger.error("No captured image (image1.png not found). Run a snip first.")
        _quit_and_return()
        return

    capture_pil = Image.open(capture_path).convert("RGB")
    capture_np = np.array(capture_pil)  # RGB
    capture_bgr = cv2.cvtColor(capture_np, cv2.COLOR_RGB2BGR)

    snip_h_img, snip_w_img = capture_bgr.shape[:2]

    if snip_w_img <= 0 or snip_h_img <= 0:
        logger.error(f"Invalid snip dimensions: {snip_w_img}x{snip_h_img}")
        _quit_and_return()
        return

    logger.info(f"Window geometry: {snip_w_img}x{snip_h_img} at "
                f"({screen_x},{screen_y})")

    # Render via blend.py: text removal + colour + container + fit + RTL
    # Returns RGBA overlay image (HxWx4 uint8), placements, metrics.
    translation_list = [translated.get(i, "") for i in range(len(block_records))]
    rgba_overlay, placements, blend_metrics = blend.render_overlay(
        capture_np, block_records, translation_list, dest_lang=dest)

    overlay = OverlayWindow(screen_x, screen_y, snip_w_img, snip_h_img,
                            alpha=alpha, text_color=text_color)
    overlay.set_overlay_rgba(rgba_overlay)

    # Register the overlay so it is not garbage-collected (defect 1 fix).
    _OVERLAYS.append(overlay)
    overlay.destroyed.connect(lambda *_: _on_overlay_closed(overlay))

    overlay.show()
    overlay.raise_()
    overlay.activateWindow()

    if dbg:
        dbg.stage("render")
        _write_debug_artifacts(dbg, overlay, capture_bgr, words, block_records,
                               translated, screen_x, screen_y, snip_w_img, snip_h_img,
                               rgba_overlay=rgba_overlay, placements=placements,
                               blend_metrics=blend_metrics)
        dbg.finish()


# ---------------------------------------------------------------------------
# Lifecycle helpers (defined after show_translations for readability;
# Python resolves them at call time so the forward reference above is safe)
# ---------------------------------------------------------------------------

def _on_overlay_closed(overlay):
    """Remove overlay from registry; quit app when the last one closes."""
    if overlay in _OVERLAYS:
        _OVERLAYS.remove(overlay)
    _maybe_quit()


def _maybe_quit():
    """Quit the Qt event loop when no overlays remain."""
    if not _OVERLAYS:
        QTimer.singleShot(0, QApplication.instance().quit)


def _quit_and_return():
    """Helper for early-exit paths: ensure the process can terminate."""
    _maybe_quit()


# ---------------------------------------------------------------------------
# Dead-code removal (spec section 4.3):
#   _DismissFilter class -- deleted (was checking QEvent.Show == type 17,
#     not a mouse press; instance had no parent so it was GC'd).
#   _init_timer / _ensure_paint -- deleted (unreliable, not in spec).
#   dismiss closure + installEventFilter call -- deleted (replaced by
#     mousePressEvent / keyPressEvent on OverlayWindow).
# Dismissal is now via mousePressEvent (any button) and keyPressEvent
# (Esc or Q) on OverlayWindow itself.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setAttribute(Qt.AA_DisableHighDpiScaling, True)
    w = OverlayWindow(100, 100, 800, 600, alpha=0.9, text_color="#ffffff")
    _OVERLAYS.append(w)
    w.destroyed.connect(lambda *_: _on_overlay_closed(w))
    w.show()
    w.raise_()
    w.activateWindow()
    sys.exit(app.exec_())