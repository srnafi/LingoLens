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
# Timing helper
# ---------------------------------------------------------------------------

class StageTimer:
    """Measures time for each pipeline stage."""
    def __init__(self):
        self.stages = []
        self._start = time.time()

    def mark(self, name):
        now = time.time()
        elapsed = now - self._start
        self.stages.append((name, elapsed))
        self._start = now
        return elapsed

    def report(self):
        lines = ["Pipeline timing:"]
        prev = 0
        for name, t in self.stages:
            dt = t - prev
            lines.append(f"  {name}: {dt*1000:.0f}ms (cumulative: {t*1000:.0f}ms)")
            prev = t
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# OCR via Flask — with background health check
# ---------------------------------------------------------------------------

def _check_flask_health():
    """Check if Flask is ready. Returns True/False, no waiting."""
    try:
        resp = requests.get(f"{FLASK_URL}/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _wait_for_flask(timeout=FLASK_HEALTH_TIMEOUT):
    start = time.time()
    while time.time() - start < timeout:
        if _check_flask_health():
            return True
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
# OCR result parsing
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


# ---------------------------------------------------------------------------
# Text grouping: words -> lines -> paragraphs
# ---------------------------------------------------------------------------

def _group_words_into_lines(words):
    """Group words into lines based on vertical alignment."""
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


def _line_bbox(line_words):
    return (
        min(w['x_min'] for w in line_words),
        min(w['y_min'] for w in line_words),
        max(w['x_max'] for w in line_words),
        max(w['y_max'] for w in line_words),
    )


def _group_lines_into_paragraphs(lines):
    """Group lines into paragraphs based on vertical spacing."""
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


def _paragraph_bbox(para_lines):
    x_min = min(w['x_min'] for line in para_lines for w in line)
    y_min = min(w['y_min'] for line in para_lines for w in line)
    x_max = max(w['x_max'] for line in para_lines for w in line)
    y_max = max(w['y_max'] for line in para_lines for w in line)
    return x_min, y_min, x_max, y_max


def _line_text(line_words):
    return ' '.join(w['text'] for w in line_words)


def _paragraph_text(para_lines):
    return '\n'.join(_line_text(line) for line in para_lines)


# ---------------------------------------------------------------------------
# Font size estimation
# ---------------------------------------------------------------------------

def _estimate_font_size(words):
    if not words:
        return 12
    heights = sorted(w['height'] for w in words)
    median_h = heights[len(heights) // 2]
    return max(8, int(median_h * 0.75))


# ---------------------------------------------------------------------------
# Single-window overlay
# ---------------------------------------------------------------------------

def _create_overlay_window(screen_x, screen_y, snip_width, snip_height, alpha):
    root = _get_tk_root()
    win = tk.Toplevel(root)
    win.geometry(f'{snip_width}x{snip_height}+{screen_x}+{screen_y}')
    win.overrideredirect(True)
    win.attributes('-alpha', alpha)
    win.attributes('-topmost', True)
    win.wm_attributes('-transparentcolor', 'white')

    canvas = tk.Canvas(win, width=snip_width, height=snip_height,
                       highlightthickness=0, bg='white')
    canvas.pack()
    return win, canvas


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
# Main entry point
# ---------------------------------------------------------------------------

def show_translations(screen_x, screen_y, dest, alpha, font_size,
                      text_color="#000000"):
    """Parallel pipeline: detect → OCR → translate → render.

    Stages:
    1. Flask health check (parallel with other work)
    2. OCR (single HTTP POST)
    3. Parse + group (CPU-bound, fast)
    4. Translate paragraphs (parallel ThreadPoolExecutor)
    5. Render to single canvas
    """
    screen_x = int(screen_x)
    screen_y = int(screen_y)
    alpha = float(alpha)
    font_size = int(font_size)

    timer = StageTimer()
    logger.info(f"show_translations: screen=({screen_x},{screen_y}), "
                f"dest={dest}, alpha={alpha}, font_size={font_size}")

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    crops_folder = _this_dir / "crops"

    # Stage 1: Wait for Flask (non-blocking check loop)
    if not _wait_for_flask():
        logger.error("Flask OCR server not ready")
        return
    timer.mark("Flask health check")

    # Stage 2: Run OCR (single blocking HTTP POST)
    ocr_results = _run_ocr(str(crops_folder))
    timer.mark(f"OCR ({len(ocr_results)} words)")

    if not ocr_results:
        logger.warning("No OCR results")
        return

    # Stage 3: Parse + group (fast CPU work)
    words = _parse_ocr_results(ocr_results)
    if not words:
        logger.warning("No valid OCR words")
        return

    lines = _group_words_into_lines(words)
    paragraphs = _group_lines_into_paragraphs(lines)
    est_font = _estimate_font_size(words)
    timer.mark(f"Parse+group ({len(lines)} lines, {len(paragraphs)} paras)")

    # Stage 4: Translate all paragraphs in parallel
    def translate_para(idx, para):
        text = _paragraph_text(para)
        return idx, translate_text(text, dest)

    translated = {}
    n_workers = min(8, len(paragraphs) + 1)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(translate_para, i, para)
                   for i, para in enumerate(paragraphs)]
        for f in as_completed(futures):
            idx, text = f.result()
            translated[idx] = text
    timer.mark(f"Translate ({len(paragraphs)} paras, {n_workers} workers)")

    # Stage 5: Render to single canvas
    all_x_min = min(w['x_min'] for w in words)
    all_y_min = min(w['y_min'] for w in words)
    all_x_max = max(w['x_max'] for w in words)
    all_y_max = max(w['y_max'] for w in words)

    margin = 20
    snip_w = all_x_max - all_x_min + margin * 2
    snip_h = all_y_max - all_y_min + margin * 2
    overlay_x = all_x_min + screen_x - margin
    overlay_y = all_y_min + screen_y - margin

    win, canvas = _create_overlay_window(
        overlay_x, overlay_y, snip_w, snip_h, alpha)

    use_font_size = max(est_font, font_size)

    for para_idx, para_lines in enumerate(paragraphs):
        bbox = _paragraph_bbox(para_lines)
        px_min, py_min, px_max, py_max = bbox

        draw_x = px_min - all_x_min + margin
        draw_y = py_min - all_y_min + margin
        para_w = px_max - px_min

        translated_text = translated.get(para_idx, _paragraph_text(para_lines))

        # Adaptive font sizing
        actual_font = use_font_size
        text_w, text_h = _measure_text(translated_text, actual_font)

        if text_w > para_w * 1.5 and para_w > 50:
            scale = para_w / text_w
            actual_font = max(int(use_font_size * scale * 0.9),
                            int(use_font_size * 0.6))
            text_w, text_h = _measure_text(translated_text, actual_font)

        # Draw with outline for visibility
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            canvas.create_text(draw_x + dx, draw_y + dy,
                             anchor='nw', text=translated_text,
                             font=("fixedsys", actual_font),
                             fill='#888888')
        canvas.create_text(draw_x, draw_y, anchor='nw',
                          text=translated_text,
                          font=("fixedsys", actual_font),
                          fill=text_color)

    timer.mark(f"Render ({len(paragraphs)} paras)")
    logger.info(timer.report())

    # Dismiss on Escape / Q
    def dismiss(event=None):
        try:
            win.destroy()
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
    root.bind('<Escape>', dismiss)
    root.bind('<Key-q>', dismiss)
    root.deiconify()
    root.focus_force()
    root.mainloop()


if __name__ == "__main__":
    show_translations(0, 0, "es", 0.8, 12)
