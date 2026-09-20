"""Synthetic screenshot fixture with ground truth for deterministic headless tests.

Copied and adapted from docs/reference/blend_reference.py::make_fixture.
Returns:
    screenshot : np.ndarray (H, W, 3) uint8 BGR -- the snip with text on it.
    clean      : np.ndarray (H, W, 3) uint8 BGR -- same scene WITHOUT text (ground truth).
    words      : list[dict] -- ground-truth word bounding boxes in snip-relative coords.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _find_font_file():
    for p in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("no TTF found for the fixture; edit _find_font_file()")


def make_fixture():
    """Return (screenshot_bgr, clean_bgr, words). clean = screenshot with text removed."""
    W, H = 900, 420
    img = Image.fromarray(np.full((H, W, 3), 245, np.uint8))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 430, 170], fill=(255, 255, 255), outline=(200, 200, 200))   # white card
    d.rounded_rectangle([20, 200, 200, 250], 8, fill=(37, 99, 235))                  # blue button
    arr = np.array(img)
    for x in range(460, 880):                                                          # gradient banner
        t = (x - 460) / 420
        arr[20:100, x] = (np.array([120, 60, 30]) * (1 - t) + np.array([160, 60, 120]) * t).astype(np.uint8)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    d.rectangle([460, 140, 880, 300], fill=(30, 30, 46))                             # dark panel
    clean = np.array(img).copy()
    ff = _find_font_file()
    words = []

    def put(lines, x, y, size, color, gap=1.35):
        f = ImageFont.truetype(ff, size)
        for li, line in enumerate(lines):
            cx = x
            for tok in line.split():
                yy = y + int(li * size * gap)
                bb = d.textbbox((cx, yy), tok, font=f)
                d.text((cx, yy), tok, font=f, fill=color)
                words.append(dict(text=tok, x_min=bb[0] - 2, y_min=bb[1] - 2,
                                  x_max=bb[2] + 2, y_max=bb[3] + 2))
                cx = bb[2] + int(size * 0.3)

    put(["Your account settings let you", "manage notifications and privacy",
         "options for every device."], 36, 36, 18, (30, 30, 30))
    put(["Save changes"], 46, 213, 20, (255, 255, 255))
    put(["Welcome back to the dashboard"], 480, 46, 20, (255, 255, 255))
    put(["Storage is almost full.", "Upgrade your plan to keep",
         "syncing new files."], 480, 156, 16, (200, 200, 210))
    for w in words:
        w.update(cx=(w["x_min"] + w["x_max"]) / 2, cy=(w["y_min"] + w["y_max"]) / 2,
                 width=w["x_max"] - w["x_min"], height=w["y_max"] - w["y_min"])
    # Convert PIL RGB -> BGR for cv2 consistency
    shot_bgr = np.array(img)[:, :, ::-1].copy()
    clean_bgr = clean[:, :, ::-1].copy()
    return shot_bgr, clean_bgr, words


# Fixture translations: keyed by first word of the block (~30-50% longer)
FIXTURE_TRANSLATIONS = {
    "Your": "Настройки вашей учётной записи позволяют управлять уведомлениями и параметрами конфиденциальности на каждом устройстве.",
    "Save": "Сохранить изменения",
    "Welcome": "Добро пожаловать обратно на панель управления",
    "Storage": "Хранилище почти заполнено. Обновите тариф, чтобы продолжить синхронизацию новых файлов.",
}
