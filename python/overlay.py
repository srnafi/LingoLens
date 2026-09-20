import tkinter as tk
import ctypes
import requests
import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from translator import translate_text

logger = logging.getLogger(__name__)

_tk_root = None
FLASK_URL = "http://localhost:5000"
FLASK_HEALTH_TIMEOUT = 30


def _get_tk_root():
    global _tk_root
    if _tk_root is None:
        _tk_root = tk.Tk()
        _tk_root.withdraw()
    return _tk_root


# ---------------------------------------------------------------------------
# Grouping: OCR words -> lines
# ---------------------------------------------------------------------------

def _parse_ocr_results(ocr_results):
    """Parse OCR {coords_str: text} into a list of region dicts."""
    regions = []
    for coords_str, text in ocr_results.items():
        parts = coords_str.split(',')
        if len(parts) != 4:
            continue
        x_min, x_max, y_min, y_max = map(int, parts)
        regions.append({
            'x_min': x_min, 'x_max': x_max,
            'y_min': y_min, 'y_max': y_max,
            'text': text.strip(),
        })
    return [r for r in regions if r['text']]


def group_into_lines(regions):
    """Group word regions into lines by vertical overlap/proximity.

    Two words belong to the same line if their vertical centers are within
    60% of the average word height. Words in each line are sorted left-to-right.
    """
    if not regions:
        return []

    regions.sort(key=lambda r: (r['y_min'], r['x_min']))
    lines = [[regions[0]]]

    for region in regions[1:]:
        prev = lines[-1]
        prev_cy = (prev[0]['y_min'] + prev[0]['y_max']) / 2
        this_cy = (region['y_min'] + region['y_max']) / 2
        avg_h = ((prev[0]['y_max'] - prev[0]['y_min']) +
                 (region['y_max'] - region['y_min'])) / 2

        if abs(prev_cy - this_cy) < avg_h * 0.6:
            lines[-1].append(region)
        else:
            lines.append([region])

    for line in lines:
        line.sort(key=lambda r: r['x_min'])

    return lines


def _line_bbox(line):
    """Get bounding box covering all words in a line."""
    x_min = min(r['x_min'] for r in line)
    y_min = min(r['y_min'] for r in line)
    x_max = max(r['x_max'] for r in line)
    y_max = max(r['y_max'] for r in line)
    return x_min, y_min, x_max, y_max


def _line_text(line):
    """Join words in a line into a single string."""
    return ' '.join(r['text'] for r in line)


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
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
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
# Text measurement
# ---------------------------------------------------------------------------

def _measure_text(text, font_size):
    root = _get_tk_root()
    label = tk.Label(root, text=text, font=("fixedsys", font_size))
    label.pack()
    root.update_idletasks()
    w = label.winfo_reqwidth()
    h = label.winfo_reqheight()
    label.destroy()
    return w, h


# ---------------------------------------------------------------------------
# Overlay display - LINE-LEVEL with spatial alignment
# ---------------------------------------------------------------------------

def _create_line_overlay(text, x, y, source_width, source_height,
                         font_size, alpha, text_color):
    """Create a transparent overlay for one translated line.

    Positioned at (x, y) which is the source line's top-left + screen offset.
    The overlay spans the source region's width and height.
    """
    tw, th = _measure_text(text, font_size)

    # Use source region dimensions as the overlay size
    win_w = max(source_width, tw + 8)
    win_h = max(source_height, th + 4)

    win = tk.Toplevel()
    win.geometry(f'{win_w}x{win_h}+{x}+{y}')
    win.overrideredirect(True)
    win.attributes('-alpha', alpha)
    win.attributes('-topmost', True)
    win.wm_attributes('-transparentcolor', 'white')

    canvas = tk.Canvas(win, width=win_w, height=win_h,
                       highlightthickness=0, bg='white')
    canvas.pack()

    # Vertically center the text within the source region height
    y_offset = max(0, (win_h - th) // 2)
    canvas.create_text(4, y_offset, anchor='nw', text=text,
                       font=("fixedsys", font_size), fill=text_color)

    return win


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def show_translations(screen_x, screen_y, dest, alpha, font_size,
                      text_color="#000000"):
    """OCR -> group words into lines -> translate each line -> overlay.

    Each translated line is placed at the source line's exact position,
    preserving spatial alignment. Translation uses line-level context
    (full sentence/phrase) rather than individual words.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    crops_folder = _this_dir / "crops"

    if not _wait_for_flask():
        logger.error("Flask OCR server not ready")
        return

    ocr_results = _run_ocr(str(crops_folder))
    if not ocr_results:
        logger.warning("No OCR results")
        return

    logger.info(f"OCR: {len(ocr_results)} word regions")

    # Parse and group into lines
    regions = _parse_ocr_results(ocr_results)
    lines = group_into_lines(regions)

    logger.info(f"Grouped into {len(lines)} lines")

    # Translate each line as a unit (parallel)
    translated = {}

    def translate_line(idx, line):
        text = _line_text(line)
        return idx, translate_text(text, dest)

    with ThreadPoolExecutor(max_workers=min(8, len(lines) + 1)) as pool:
        futures = [pool.submit(translate_line, i, line)
                   for i, line in enumerate(lines)]
        for f in as_completed(futures):
            idx, text = f.result()
            translated[idx] = text

    # Display overlays - one per line, positioned at source coordinates
    overlay_windows = []
    for i, line in enumerate(lines):
        bbox = _line_bbox(line)
        x_min, y_min, x_max, y_max = bbox

        # Position at source line's top-left + screen offset
        ox = x_min + screen_x
        oy = y_min + screen_y

        # Source region dimensions
        src_w = x_max - x_min
        src_h = y_max - y_min

        text = translated.get(i, _line_text(line))
        win = _create_line_overlay(text, ox, oy, src_w, src_h,
                                   font_size, alpha, text_color)
        overlay_windows.append(win)

    logger.info(f"Displayed {len(overlay_windows)} line overlays")

    # Dismiss on Escape / Q
    def dismiss_all(event=None):
        for w in overlay_windows:
            try:
                w.destroy()
            except tk.TclError:
                pass
        root = _get_tk_root()
        try:
            root.destroy()
        except tk.TclError:
            pass
        global _tk_root
        _tk_root = None

    root = _get_tk_root()
    root.bind('<Escape>', dismiss_all)
    root.bind('<Key-q>', dismiss_all)
    root.deiconify()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    show_translations(0, 0, "es", 0.8, 12)
