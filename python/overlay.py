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
# Grouping: OCR words -> lines -> paragraphs
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
    60% of the average word height.
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

    # Sort words left-to-right within each line
    for line in lines:
        line.sort(key=lambda r: r['x_min'])

    return lines


def group_into_paragraphs(lines):
    """Group lines into paragraphs by vertical gap.

    Lines with a gap smaller than 1.5x their combined height are in the
    same paragraph.
    """
    if not lines:
        return []

    paragraphs = [[lines[0]]]

    for i in range(1, len(lines)):
        prev = lines[i - 1]
        curr = lines[i]

        prev_y_max = max(r['y_max'] for r in prev)
        curr_y_min = min(r['y_min'] for r in curr)

        prev_h = max(r['y_max'] for r in prev) - min(r['y_min'] for r in prev)
        curr_h = max(r['y_max'] for r in curr) - min(r['y_min'] for r in curr)
        avg_h = (prev_h + curr_h) / 2

        gap = curr_y_min - prev_y_max
        if gap < avg_h * 1.5:
            paragraphs[-1].append(curr)
        else:
            paragraphs.append([curr])

    return paragraphs


def _paragraph_bbox(para_lines):
    """Get the bounding box covering all lines in a paragraph."""
    x_min = min(r['x_min'] for line in para_lines for r in line)
    y_min = min(r['y_min'] for line in para_lines for r in line)
    x_max = max(r['x_max'] for line in para_lines for r in line)
    y_max = max(r['y_max'] for line in para_lines for r in line)
    return x_min, y_min, x_max, y_max


def _line_text(line):
    """Join words in a line into a single string."""
    return ' '.join(r['text'] for r in line)


def _paragraph_text(para_lines):
    """Join all lines in a paragraph."""
    return '\n'.join(_line_text(line) for line in para_lines)


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
    """Measure text dimensions using a shared hidden Tk root."""
    root = _get_tk_root()
    label = tk.Label(root, text=text, font=("fixedsys", font_size))
    label.pack()
    root.update_idletasks()
    w = label.winfo_reqwidth()
    h = label.winfo_reqheight()
    label.destroy()
    return w, h


def _wrap_text(text, max_width, font_size):
    """Word-wrap text to fit within max_width pixels.

    Returns a list of lines (strings), each fitting within max_width.
    """
    root = _get_tk_root()
    words = text.replace('\n', ' ').split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        tw, _ = _measure_text(test, font_size)
        if tw <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Overlay display
# ---------------------------------------------------------------------------

def _create_overlay(text, x, y, max_width, font_size, alpha, text_color):
    """Create a single transparent overlay window displaying text."""
    wrapped = _wrap_text(text, max_width, font_size)

    # Calculate total size
    total_w = 0
    total_h = 0
    for line in wrapped:
        lw, lh = _measure_text(line, font_size)
        total_w = max(total_w, lw)
        total_h += lh

    # Add padding
    total_w += 8
    total_h += 4

    win = tk.Toplevel()
    win.geometry(f'{total_w}x{total_h}+{x}+{y}')
    win.overrideredirect(True)
    win.attributes('-alpha', alpha)
    win.attributes('-topmost', True)
    win.wm_attributes('-transparentcolor', 'white')

    canvas = tk.Canvas(win, width=total_w, height=total_h,
                       highlightthickness=0, bg='white')
    canvas.pack()

    # Draw each wrapped line
    y_offset = 0
    for line in wrapped:
        lw, lh = _measure_text(line, font_size)
        canvas.create_text(4, y_offset, anchor='nw', text=line,
                           font=("fixedsys", font_size), fill=text_color)
        y_offset += lh

    return win


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def show_translations(screen_x, screen_y, dest, alpha, font_size,
                      text_color="#000000"):
    """Run full pipeline: OCR -> group -> translate -> display overlays.

    Instead of translating each word individually, this groups OCR results
    into lines, then paragraphs, and translates each paragraph as a complete
    unit. This gives the translation engine full context for natural output.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    crops_folder = _this_dir / "crops"

    # 1. Wait for Flask OCR server
    if not _wait_for_flask():
        logger.error("Flask OCR server not ready")
        return

    # 2. Run OCR
    ocr_results = _run_ocr(str(crops_folder))
    if not ocr_results:
        logger.warning("No OCR results")
        return

    logger.info(f"OCR: {len(ocr_results)} word regions")

    # 3. Parse and group into lines -> paragraphs
    regions = _parse_ocr_results(ocr_results)
    lines = group_into_lines(regions)
    paragraphs = group_into_paragraphs(lines)

    logger.info(f"Grouped into {len(lines)} lines, {len(paragraphs)} paragraphs")

    # 4. Translate each paragraph as a whole (parallel)
    translated = {}

    def translate_para(idx, para_lines):
        text = _paragraph_text(para_lines)
        return idx, translate_text(text, dest)

    with ThreadPoolExecutor(max_workers=min(8, len(paragraphs) + 1)) as pool:
        futures = [pool.submit(translate_para, i, para)
                   for i, para in enumerate(paragraphs)]
        for f in as_completed(futures):
            idx, text = f.result()
            translated[idx] = text

    # 5. Display overlays — one per paragraph
    # Use a single max width based on the widest paragraph's original bbox
    max_overlay_width = max(
        (_paragraph_bbox(para)[2] - _paragraph_bbox(para)[0])
        for para in paragraphs
    ) if paragraphs else 400

    overlay_windows = []
    for i, para_lines in enumerate(paragraphs):
        bbox = _paragraph_bbox(para_lines)
        orig_w = bbox[2] - bbox[0]

        # Position at paragraph's top-left + screen offset
        ox = bbox[0] + screen_x
        oy = bbox[1] + screen_y

        # Use original paragraph width as the wrap constraint
        wrap_width = max(orig_w, 150)

        text = translated.get(i, _paragraph_text(para_lines))
        win = _create_overlay(text, ox, oy, wrap_width, font_size,
                              alpha, text_color)
        overlay_windows.append(win)

    logger.info(f"Displayed {len(overlay_windows)} translation overlays")

    # 6. Dismiss on Escape / Q
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
