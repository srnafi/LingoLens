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
# OCR result parsing
# ---------------------------------------------------------------------------

def _parse_ocr_results(ocr_results):
    """Parse OCR {coords_str: text} into structured word dicts.

    Each word retains its original image-relative bounding box.
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
    return [w for w in words if w['text']]


# ---------------------------------------------------------------------------
# Text grouping: words -> lines -> paragraphs
# ---------------------------------------------------------------------------

def _group_words_into_lines(words):
    """Group words into lines based on vertical alignment.

    Words belong to the same line when their vertical centers are close
    relative to their height. Each line is sorted left-to-right.
    """
    if not words:
        return []

    words.sort(key=lambda w: (w['cy'], w['cx']))
    lines = [[words[0]]]

    for word in words[1:]:
        line = lines[-1]
        # Use the average vertical center and height of the current line
        avg_cy = sum(w['cy'] for w in line) / len(line)
        avg_h = sum(w['height'] for w in line) / len(line)

        # Words are on the same line if their vertical centers are within
        # 50% of the average word height
        if abs(word['cy'] - avg_cy) < avg_h * 0.5:
            lines[-1].append(word)
        else:
            lines.append([word])

    # Sort words left-to-right within each line
    for line in lines:
        line.sort(key=lambda w: w['cx'])

    return lines


def _line_bbox(line_words):
    """Get bounding box covering all words in a line."""
    return (
        min(w['x_min'] for w in line_words),
        min(w['y_min'] for w in line_words),
        max(w['x_max'] for w in line_words),
        max(w['y_max'] for w in line_words),
    )


def _group_lines_into_paragraphs(lines):
    """Group lines into paragraphs based on vertical spacing.

    Lines with a gap smaller than 1.2x their combined height are in the
    same paragraph.
    """
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
    """Get bounding box covering all lines in a paragraph."""
    x_min = min(w['x_min'] for line in para_lines for w in line)
    y_min = min(w['y_min'] for line in para_lines for w in line)
    x_max = max(w['x_max'] for line in para_lines for w in line)
    y_max = max(w['y_max'] for line in para_lines for w in line)
    return x_min, y_min, x_max, y_max


def _line_text(line_words):
    """Join words in a line into a single string."""
    return ' '.join(w['text'] for w in line_words)


def _paragraph_text(para_lines):
    """Join all lines in a paragraph."""
    return '\n'.join(_line_text(line) for line in para_lines)


# ---------------------------------------------------------------------------
# Font size estimation from OCR geometry
# ---------------------------------------------------------------------------

def _estimate_font_size(words):
    """Estimate source font size from median OCR bounding box height.

    Returns a pixel height that approximately matches the source text.
    """
    if not words:
        return 12

    heights = sorted(w['height'] for w in words)
    # Use the median height, which is more robust than mean
    median_h = heights[len(heights) // 2]

    # The font pixel size is roughly the bounding box height minus padding.
    # OCR boxes typically have some vertical padding.
    # A reasonable approximation: font_size ≈ box_height * 0.75
    estimated = max(8, int(median_h * 0.75))
    return estimated


# ---------------------------------------------------------------------------
# Single-window overlay
# ---------------------------------------------------------------------------

def _create_overlay_window(screen_x, screen_y, snip_width, snip_height,
                           alpha):
    """Create ONE transparent overlay window covering the entire snipped region.

    The window is positioned at (screen_x, screen_y) and sized to
    (snip_width, snip_height). All translated text is drawn inside
    this single window using image-relative coordinates.
    """
    root = _get_tk_root()

    win = tk.Toplevel(root)
    win.geometry(f'{snip_width}x{snip_height}+{screen_x}+{screen_y}')
    win.overrideredirect(True)
    win.attributes('-alpha', alpha)
    win.attributes('-topmost', True)
    # Transparent background — text is drawn on top
    win.wm_attributes('-transparentcolor', 'white')

    canvas = tk.Canvas(win, width=snip_width, height=snip_height,
                       highlightthickness=0, bg='white')
    canvas.pack()

    return win, canvas


def _estimate_snip_size(words):
    """Estimate the snipped region size from OCR word bounding boxes.

    If we know the words' positions, the snip region must be large enough
    to contain them all.
    """
    if not words:
        return 400, 200

    x_min = min(w['x_min'] for w in words)
    y_min = min(w['y_min'] for w in words)
    x_max = max(w['x_max'] for w in words)
    y_max = max(w['y_max'] for w in words)

    # Add some margin
    return (x_max - x_min + 40, y_max - y_min + 40)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def show_translations(screen_x, screen_y, dest, alpha, font_size,
                      text_color="#000000"):
    """Single-overlay pipeline: OCR -> group -> translate -> render.

    Creates ONE transparent overlay window covering the entire snipped
    region. All translated text is drawn inside that window at
    image-relative coordinates, exactly matching where the source text
    appeared within the snip.
    """
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

    # 3. Parse OCR results into structured words
    words = _parse_ocr_results(ocr_results)
    if not words:
        logger.warning("No valid OCR words")
        return

    # 4. Group words into lines, then paragraphs
    lines = _group_words_into_lines(words)
    paragraphs = _group_lines_into_paragraphs(lines)
    logger.info(f"Grouped: {len(words)} words -> {len(lines)} lines -> "
                f"{len(paragraphs)} paragraphs")

    # 5. Estimate source font size from OCR geometry
    est_font = _estimate_font_size(words)
    logger.info(f"Estimated source font size: {est_font}px "
                f"(user override: {font_size}px)")

    # 6. Determine overlay dimensions from the snipped region
    # The snip region is defined by the bounding box of all OCR words,
    # expanded with some margin
    all_x_min = min(w['x_min'] for w in words)
    all_y_min = min(w['y_min'] for w in words)
    all_x_max = max(w['x_max'] for w in words)
    all_y_max = max(w['y_max'] for w in words)

    margin = 20
    snip_w = all_x_max - all_x_min + margin * 2
    snip_h = all_y_max - all_y_min + margin * 2

    # The overlay window starts at the snip's top-left + screen offset
    overlay_x = all_x_min + screen_x - margin
    overlay_y = all_y_min + screen_y - margin

    logger.info(f"Overlay window: pos=({overlay_x},{overlay_y}), "
                f"size={snip_w}x{snip_h}")

    # 7. Create ONE overlay window
    win, canvas = _create_overlay_window(
        overlay_x, overlay_y, snip_w, snip_h, alpha)

    # 8. Translate each paragraph as a unit, then render line by line
    def translate_para(idx, para):
        text = _paragraph_text(para)
        return idx, translate_text(text, dest)

    translated = {}
    with ThreadPoolExecutor(max_workers=min(8, len(paragraphs) + 1)) as pool:
        futures = [pool.submit(translate_para, i, para)
                   for i, para in enumerate(paragraphs)]
        for f in as_completed(futures):
            idx, text = f.result()
            translated[idx] = text

    # 9. Render translated text into the canvas
    # For each paragraph, draw the translated text at the paragraph's
    # bounding box position (relative to the overlay window)
    use_font_size = max(est_font, font_size)  # prefer larger of estimated vs user

    for para_idx, para_lines in enumerate(paragraphs):
        bbox = _paragraph_bbox(para_lines)
        px_min, py_min, px_max, py_max = bbox

        # Position relative to the overlay window's top-left
        draw_x = px_min - all_x_min + margin
        draw_y = py_min - all_y_min + margin

        para_w = px_max - px_min
        para_h = py_max - py_min

        translated_text = translated.get(para_idx, _paragraph_text(para_lines))

        # Measure text at the estimated font size
        label = tk.Label(canvas, text=translated_text,
                        font=("fixedsys", use_font_size))
        label.pack()
        _get_tk_root().update_idletasks()
        text_w = label.winfo_reqwidth()
        text_h = label.winfo_reqheight()
        label.destroy()

        # If text is wider than the source region, try to fit it
        actual_font = use_font_size
        if text_w > para_w * 1.5 and para_w > 50:
            # Scale down font to fit, but not below 60% of estimated
            scale = para_w / text_w
            actual_font = max(int(use_font_size * scale * 0.9),
                            int(use_font_size * 0.6))
            # Re-measure with adjusted font
            label = tk.Label(canvas, text=translated_text,
                            font=("fixedsys", actual_font))
            label.pack()
            _get_tk_root().update_idletasks()
            text_w = label.winfo_reqwidth()
            text_h = label.winfo_reqheight()
            label.destroy()

        logger.info(f"  para {para_idx}: draw at ({draw_x},{draw_y}), "
                     f"font={actual_font}, text='{translated_text[:50]}...'")

        # Draw text with outline for visibility
        # First draw a subtle outline/shadow for contrast
        outline_color = '#888888'
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            canvas.create_text(draw_x + dx, draw_y + dy,
                             anchor='nw', text=translated_text,
                             font=("fixedsys", actual_font),
                             fill=outline_color)

        # Then draw the main text
        canvas.create_text(draw_x, draw_y, anchor='nw',
                          text=translated_text,
                          font=("fixedsys", actual_font),
                          fill=text_color)

    logger.info(f"Rendered {len(paragraphs)} translated paragraphs "
                f"into single overlay")

    # 10. Dismiss on Escape / Q
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
