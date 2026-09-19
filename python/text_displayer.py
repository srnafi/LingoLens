import tkinter as tk
import ctypes
import requests
import re
import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from translate import translate_word

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


def main(x1, y1, dest, alpha, font_size, text_color="#000000"):
    x = x1
    y = y1
    dest_lang = dest

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def wait_for_flask(timeout=FLASK_HEALTH_TIMEOUT):
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

    def run_ocr_request(folder_location):
        try:
            data = {'folder_location': folder_location}
            response = requests.post(f"{FLASK_URL}/ocr", json=data, timeout=120)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"OCR server returned status {response.status_code}")
                return {}
        except requests.ConnectionError:
            logger.error("Cannot connect to Flask OCR server")
            return {}
        except Exception as e:
            logger.error(f"OCR request failed: {e}")
            return {}

    def get_text_width(text, fsize):
        root = _get_tk_root()
        f = ("fixedsys", fsize)
        label = tk.Label(root, text=text, font=f)
        label.pack()
        root.update_idletasks()
        width = label.winfo_reqwidth()
        height = label.winfo_reqheight()
        label.destroy()
        return width, height

    def translate_batch_words(word):
        try:
            cleaned_word = re.sub(r'[^\w\s]', '', word)
            return translate_word(cleaned_word, dest_lang)
        except Exception as e:
            logger.debug(f"Translation failed for '{word}': {e}")
            return word

    current_file_directory = Path(__file__).parent
    crops_folder = current_file_directory / "crops"

    if not wait_for_flask():
        logger.error("Flask OCR server did not become ready in time")
        return

    ocr_results = run_ocr_request(str(crops_folder))
    if not ocr_results:
        logger.warning("No OCR results returned")
        return

    logger.info(f"OCR returned {len(ocr_results)} regions, translating...")

    translated_words = {}
    total_threads = min(32, (os.cpu_count() or 4) * 5)

    with ThreadPoolExecutor(max_workers=total_threads) as executor:
        futures = {
            executor.submit(translate_batch_words, word): coords
            for coords, word in ocr_results.items()
        }
        for future in as_completed(futures):
            coords = futures[future]
            translated_words[coords] = future.result()

    translated_words = dict(
        sorted(translated_words.items(), key=lambda item: int(item[0].split(',')[0]))
    )

    line_info = []
    overlay_windows = []

    for coords, text in translated_words.items():
        x_min, x_max, y_min, y_max = map(int, coords.split(','))
        tr_word = text
        new_width, new_height = get_text_width(tr_word, font_size)

        for prev_x_min, prev_x_max, prev_y_min, prev_y_max, rightmost_x in line_info:
            if not (y_max < prev_y_min or y_min > prev_y_max):
                if x_min < rightmost_x:
                    x_min = rightmost_x + 1

        rightmost_x = x_min + new_width
        line_info.append((x_min, rightmost_x, y_min, y_max, rightmost_x))

        word_window = tk.Toplevel()
        word_window.geometry(f'+{x_min + x}+{y_min + y}')
        word_window.overrideredirect(True)
        word_window.attributes('-alpha', alpha)
        word_window.attributes('-topmost', True)
        word_window.wm_attributes('-transparentcolor', 'white')

        canvas = tk.Canvas(word_window, width=new_width, height=new_height,
                           highlightthickness=0, bg='white')
        canvas.pack()
        canvas.create_text(2, -1, anchor='nw', text=tr_word,
                           font=("fixedsys", font_size), fill=text_color)
        overlay_windows.append(word_window)

    def dismiss_all(event=None):
        for w in overlay_windows:
            try:
                w.destroy()
            except tk.TclError:
                pass
        root_win = _get_tk_root()
        try:
            root_win.destroy()
        except tk.TclError:
            pass
        global _tk_root
        _tk_root = None

    root_win = _get_tk_root()
    root_win.bind('<Escape>', dismiss_all)
    root_win.bind('<Key-q>', dismiss_all)
    root_win.deiconify()
    root_win.focus_force()
    root_win.mainloop()


if __name__ == "__main__":
    main()
