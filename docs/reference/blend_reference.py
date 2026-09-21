"""
REFERENCE SKETCH - not production code, not a drop-in replacement.

What this is
------------
A small, self-contained, *tested* demonstration of the "blend-in" rendering core that
LingoLens needs, plus a synthetic screenshot fixture WITH ground truth and a numeric
acceptance table. It was verified headless (QT_QPA_PLATFORM=offscreen, PyQt5 5.15,
OpenCV, Pillow) on Linux. It has NOT been run on the real Windows desktop.

How to use it
-------------
(If your Qt build lacks the offscreen platform plugin, set QT_QPA_PLATFORM to the native one, e.g. windows.)
  python docs/reference/blend_reference.py            # writes debug/ref/*.png, prints a metrics table
Port the *ideas* into python/blocks.py and python/blend.py, keeping the project's own
data structures. Keep the numeric checks (they are your definition of "works").

Pipeline shown here
-------------------
  words -> lines -> blocks (grouping)
  blocks -> remove source text (flat fill or glyph-mask inpaint, ONE inpaint call)
  blocks -> fg/bg colours (ring median + glyph pixels + WCAG contrast guard)
  blocks -> container rect (flood fill on the text-removed image) -> free rect (obstacles)
  block + translation -> font fit (largest pixel size that fits, wrapping allowed)
  everything -> RGBA overlay: fully transparent except the patches; patch pixels come from
                the text-removed image so the patch is invisible against the live screen.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # harmless on Windows when a display exists
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import (QGuiApplication, QImage, QPainter, QFont, QFontMetrics,
                         QColor, QFontDatabase)

# ----------------------------------------------------------------------------- constants
LINE_MERGE_CY = 0.5        # word joins a line if |cy - line cy| < 0.5 * line height
COLUMN_GAP = 1.5           # split a line into separate blocks if the horizontal gap > 1.5 * height
PARA_GAP = 0.9             # lines are one paragraph if vertical gap < 0.9 * avg line height
PARA_LEFT_ALIGN = 1.0      # ...and left edges differ by < 1.0 * line height
PARA_HEIGHT_RATIO = (0.6, 1.6)
BOX_PAD = 2                # px added around each source box before sampling / masking
RING = 4                   # px ring outside the padded box used to sample the background
FLAT_STD = 6.0             # ring std below this => flat background => solid fill
GLYPH_MIN_DIST = 28.0      # min colour distance from bg for a pixel to count as glyph
GLYPH_REL_DIST = 0.35      # ...or this fraction of the max distance in the box
MIN_CONTRAST = 4.5         # WCAG AA
FLOOD_TOL = 6              # flood-fill tolerance (floating range) for container detection
MIN_FONT_PX, MIN_FONT_RATIO = 8, 0.6
FONT_FAMILIES = ["Segoe UI", "Arial", "DejaVu Sans", "Noto Sans"]   # first installed wins


# ----------------------------------------------------------------------------- fixture
def _find_font_file():
    for p in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("no TTF found for the fixture; edit _find_font_file()")


def make_fixture():
    """Return (screenshot_rgb, clean_rgb, words). `clean` is the same screen WITHOUT text = ground truth."""
    W, H = 900, 420
    img = Image.fromarray(np.full((H, W, 3), 245, np.uint8))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 430, 170], fill=(255, 255, 255), outline=(200, 200, 200))   # white card
    d.rounded_rectangle([20, 200, 200, 250], 8, fill=(37, 99, 235))                   # blue button
    arr = np.array(img)
    for x in range(460, 880):                                                          # gradient banner
        t = (x - 460) / 420
        arr[20:100, x] = (np.array([120, 60, 30]) * (1 - t) + np.array([160, 60, 120]) * t).astype(np.uint8)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    d.rectangle([460, 140, 880, 300], fill=(30, 30, 46))                               # dark panel
    clean = np.array(img)
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
                words.append(dict(text=tok, x_min=bb[0] - 2, y_min=bb[1] - 2, x_max=bb[2] + 2, y_max=bb[3] + 2))
                cx = bb[2] + int(size * 0.3)

    put(["Your account settings let you", "manage notifications and privacy", "options for every device."], 36, 36, 18, (30, 30, 30))
    put(["Save changes"], 46, 213, 20, (255, 255, 255))
    put(["Welcome back to the dashboard"], 480, 46, 20, (255, 255, 255))
    put(["Storage is almost full.", "Upgrade your plan to keep", "syncing new files."], 480, 156, 16, (200, 200, 210))
    for w in words:
        w.update(cx=(w["x_min"] + w["x_max"]) / 2, cy=(w["y_min"] + w["y_max"]) / 2,
                 width=w["x_max"] - w["x_min"], height=w["y_max"] - w["y_min"])
    return np.array(img), clean, words


FIXTURE_TRANSLATIONS = {   # keyed by first English word of the block; deliberately ~30-50% longer
    "Your": "Настройки вашей учётной записи позволяют управлять уведомлениями и параметрами конфиденциальности на каждом устройстве.",
    "Save": "Сохранить изменения",
    "Welcome": "Добро пожаловать обратно на панель управления",
    "Storage": "Хранилище почти заполнено. Обновите тариф, чтобы продолжить синхронизацию новых файлов.",
}


# ----------------------------------------------------------------------------- grouping
def bbox_of(words):
    return (min(w["x_min"] for w in words), min(w["y_min"] for w in words),
            max(w["x_max"] for w in words), max(w["y_max"] for w in words))


def group_lines(words):
    ws = sorted(words, key=lambda w: (w["cy"], w["cx"]))
    lines = []
    for w in ws:
        for ln in lines:
            if abs(w["cy"] - np.mean([x["cy"] for x in ln])) < LINE_MERGE_CY * np.mean([x["height"] for x in ln]):
                ln.append(w)
                break
        else:
            lines.append([w])
    out = []
    for ln in lines:                       # split at big horizontal gaps (columns / separate buttons)
        ln.sort(key=lambda w: w["cx"])
        seg = [ln[0]]
        for a, b in zip(ln, ln[1:]):
            if b["x_min"] - a["x_max"] > COLUMN_GAP * (a["height"] + b["height"]) / 2:
                out.append(seg)
                seg = [b]
            else:
                seg.append(b)
        out.append(seg)
    return sorted(out, key=lambda l: (bbox_of(l)[1], bbox_of(l)[0]))


def group_blocks(lines):
    blocks = []
    for ln in lines:
        b = bbox_of(ln)
        h = b[3] - b[1]
        for blk in blocks:
            pb = bbox_of(blk[-1])
            ph = pb[3] - pb[1]
            gap = b[1] - pb[3]
            if (0 <= gap < PARA_GAP * (h + ph) / 2 and min(b[2], pb[2]) > max(b[0], pb[0])
                    and abs(b[0] - pb[0]) < PARA_LEFT_ALIGN * h
                    and PARA_HEIGHT_RATIO[0] < h / max(ph, 1) < PARA_HEIGHT_RATIO[1]):
                blk.append(ln)
                break
        else:
            blocks.append([ln])
    return blocks


# ----------------------------------------------------------------------------- colour + removal
def _lum(c):
    c = np.array(c, float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _clip_box(b, W, H):
    return (max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3]))


def analyse_block(img, box):
    """-> padded box, bg colour, ring std, glyph mask (uint8 0/255 over the box), fg colour."""
    H, W = img.shape[:2]
    b = _clip_box((box[0] - BOX_PAD, box[1] - BOX_PAD, box[2] + BOX_PAD, box[3] + BOX_PAD), W, H)
    x0, y0, x1, y1 = _clip_box((b[0] - RING, b[1] - RING, b[2] + RING, b[3] + RING), W, H)
    keep = np.ones((y1 - y0, x1 - x0), bool)
    keep[b[1] - y0:b[3] - y0, b[0] - x0:b[2] - x0] = False
    ring = img[y0:y1, x0:x1][keep]
    bg = np.median(ring, axis=0)
    std = float(np.mean(np.std(ring, axis=0)))
    roi = img[b[1]:b[3], b[0]:b[2]].astype(np.float32)
    dist = np.linalg.norm(roi - bg, axis=2)
    mask = (dist > max(GLYPH_MIN_DIST, GLYPH_REL_DIST * dist.max())).astype(np.uint8) * 255
    if mask.any():
        fg = np.median(roi[dist >= np.percentile(dist[mask > 0], 60)], axis=0)
    else:
        fg = np.array([0, 0, 0] if _lum(bg) > 0.4 else [255, 255, 255], float)
    return b, bg, std, mask, fg


def remove_text(img, boxes):
    """One flat fill per flat block; ONE cv2.inpaint call for all textured blocks. Returns (image, per-block info)."""
    out, infos = img.copy(), []
    inpaint_mask = np.zeros(img.shape[:2], np.uint8)
    k = np.ones((3, 3), np.uint8)
    for box in boxes:
        b, bg, std, mask, fg = analyse_block(img, box)
        infos.append(dict(box=b, bg=bg, fg=fg, ring_std=std))
        if std < FLAT_STD:                       # flat background: fill the whole padded box (also kills AA halos)
            out[b[1]:b[3], b[0]:b[2]] = bg.astype(np.uint8)
        else:                                    # gradient/texture: inpaint glyph pixels only (dilated 2x)
            inpaint_mask[b[1]:b[3], b[0]:b[2]] |= cv2.dilate(mask, k, iterations=2)
    if inpaint_mask.any():
        out = cv2.inpaint(out, inpaint_mask, 3, cv2.INPAINT_TELEA)
    return out, infos


def removal_metrics(img, info):
    """Ground-truth-free quality proxies for text removal (usable on REAL captures).

    flat blocks     : p99 colour distance of the box from the ring background must be small
                      (catches smudges/ghost blobs; leftover glyphs also show up here).
    textured blocks : mean edge energy inside the box must not exceed the surrounding ring's
                      (catches leftover glyph edges). Edge energy alone does NOT catch smudges.
    """
    b = info["box"]
    H, W = img.shape[:2]
    roi = img[b[1]:b[3], b[0]:b[2]].astype(np.float32)
    p99 = float(np.percentile(np.linalg.norm(roi - info["bg"], axis=2), 99))
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mag = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    x0, y0, x1, y1 = _clip_box((b[0] - 3 * RING, b[1] - 3 * RING, b[2] + 3 * RING, b[3] + 3 * RING), W, H)
    keep = np.ones((y1 - y0, x1 - x0), bool)
    keep[b[1] - y0:b[3] - y0, b[0] - x0:b[2] - x0] = False
    return dict(p99_bg_dist=p99, box_edge=float(mag[b[1]:b[3], b[0]:b[2]].mean()), ring_edge=float(mag[y0:y1, x0:x1][keep].mean()))


# ----------------------------------------------------------------------------- layout
def container_rect(removed, box, tol=FLOOD_TOL):
    """Bounding rect of the region around the block with ~the same background (measured on the text-removed image)."""
    H, W = removed.shape[:2]
    seed = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    m = np.zeros((H + 2, W + 2), np.uint8)
    cv2.floodFill(removed.copy(), m, seed, (0, 0, 0), (tol,) * 3, (tol,) * 3, 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8))
    ys, xs = np.where(m[1:-1, 1:-1] > 0)
    bw, bh = box[2] - box[0], box[3] - box[1]
    if len(xs) == 0:
        return tuple(box)
    r = (min(int(xs.min()), box[0]), min(int(ys.min()), box[1]), max(int(xs.max()) + 1, box[2]), max(int(ys.max()) + 1, box[3]))
    if (r[2] - r[0]) > 4 * bw + 80 or (r[3] - r[1]) > 6 * bh + 80:      # flood leaked into the page background
        return (max(0, box[0] - bw // 2), box[1], min(W, box[2] + bw // 2), min(H, box[3] + 2 * bh))
    return r


def free_rect(box, cont, others, inset, gap=6):
    """Room the translated text may occupy: grow right/down inside the container, stop at neighbouring blocks."""
    x1, y1 = cont[2] - inset, cont[3] - inset
    for o in others:
        if o == box:
            continue
        if o[0] >= box[2] - 2 and o[1] < box[3] and o[3] > box[1]:
            x1 = min(x1, o[0] - gap)
        if o[1] >= box[3] - 2 and o[0] < x1 and o[2] > box[0]:
            y1 = min(y1, o[1] - gap)
    return (box[0], box[1], max(x1, box[2]), max(y1, box[3]))


def pick_family():
    have = set(QFontDatabase().families())
    return next((f for f in FONT_FAMILIES if f in have), QFont().defaultFamily())


def fit_font(text, family, w, h, src_px):
    """Largest pixel size <= src_px whose wrapped text fits (w, h). Returns (px, fits)."""
    lo = max(MIN_FONT_PX, int(src_px * MIN_FONT_RATIO))
    for s in range(int(src_px), lo - 1, -1):
        f = QFont(family)
        f.setPixelSize(s)                       # ALWAYS pixel size; point sizes drift with DPI
        r = QFontMetrics(f).boundingRect(QRect(0, 0, max(1, w), 100000), Qt.TextWordWrap | Qt.AlignLeft, text)
        if r.height() <= h and r.width() <= w:
            return s, True
    return lo, False


def build_overlay(removed, blocks_words, infos, translations, family):
    """-> (RGBA ndarray (H,W,4), placements). Transparent except patches; patches carry text-removed pixels."""
    H, W = removed.shape[:2]
    boxes = [i["box"] for i in infos]
    qimg = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    qimg.fill(Qt.transparent)
    p = QPainter(qimg)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    placements = []
    for blk, info, text in zip(blocks_words, infos, translations):
        box = info["box"]
        bg, fg = info["bg"], info["fg"]
        line_hs = [max(w["y_max"] for w in ln) - min(w["y_min"] for w in ln) for ln in blk]
        src_px = max(9.0, float(np.median(line_hs)) / 1.25)
        cont = container_rect(removed, box)
        inset = max(4, round(0.35 * src_px))
        avail = free_rect(box, cont, boxes, inset)
        s, fits = fit_font(text, family, avail[2] - avail[0], avail[3] - avail[1], src_px)
        f = QFont(family)
        f.setPixelSize(s)
        fm = QFontMetrics(f)
        r = fm.boundingRect(QRect(0, 0, avail[2] - avail[0], 100000), Qt.TextWordWrap | Qt.AlignLeft, text)
        col = fg if contrast(fg, bg) >= MIN_CONTRAST else ((0, 0, 0) if _lum(bg) > 0.4 else (255, 255, 255))
        cw = cont[2] - cont[0]
        centered_h = len(blk) == 1 and abs((box[0] + box[2]) / 2 - (cont[0] + cont[2]) / 2) < 0.06 * cw and cw < 3 * (box[2] - box[0])
        centered_v = abs((box[1] + box[3]) / 2 - (cont[1] + cont[3]) / 2) < 0.10 * (cont[3] - cont[1])
        if centered_h:
            rect = QRect(cont[0] + inset, avail[1], cw - 2 * inset, avail[3] - avail[1])
            flags = Qt.TextWordWrap | Qt.AlignHCenter | Qt.AlignTop
        else:
            rect = QRect(avail[0], avail[1], avail[2] - avail[0], avail[3] - avail[1])
            flags = Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop
        if centered_v:
            rect.moveTop(cont[1] + max(0, ((cont[3] - cont[1]) - r.height()) // 2))
        elif len(blk) == 1 and r.height() < box[3] - box[1]:
            rect.moveTop(box[1] + ((box[3] - box[1]) - r.height()) // 2)
        # patch = union(source box, text rect) -> copy text-removed pixels into it, then draw the text
        patch = (min(box[0], rect.left()), min(box[1], rect.top()),
                 max(box[2], rect.left() + rect.width()), max(box[3], rect.top() + r.height()))
        patch = _clip_box(patch, W, H)
        crop = np.ascontiguousarray(removed[patch[1]:patch[3], patch[0]:patch[2]])
        qc = QImage(crop.data, crop.shape[1], crop.shape[0], crop.strides[0], QImage.Format_RGB888).copy()
        p.drawImage(patch[0], patch[1], qc)
        p.setFont(f)
        p.setPen(QColor(*[int(v) for v in col]))
        p.drawText(rect, flags, text)
        placements.append(dict(box=box, cont=cont, avail=avail, patch=patch, font_px=s, src_px=src_px, fits=fits,
                               contrast=contrast(col, bg), lines=round(r.height() / max(1, fm.lineSpacing()))))
    p.end()
    ptr = qimg.constBits()
    ptr.setsize(H * qimg.bytesPerLine())
    argb = np.frombuffer(ptr, np.uint8).reshape(H, qimg.bytesPerLine() // 4, 4)[:, :W].copy()
    a = argb[..., 3:4].astype(np.float32)
    rgb = np.where(a > 0, argb[..., :3].astype(np.float32) * 255.0 / np.maximum(a, 1), 0)   # un-premultiply
    # ARGB32 is BGRA in memory on little-endian machines
    rgba = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], a[..., 0]]).clip(0, 255).astype(np.uint8)
    return rgba, placements


def composite(shot, rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    return (rgba[..., :3] * a + shot * (1 - a)).astype(np.uint8)


# ----------------------------------------------------------------------------- acceptance table
def main():
    app = QGuiApplication([])
    out_dir = Path("debug/ref")
    out_dir.mkdir(parents=True, exist_ok=True)
    shot, clean, words = make_fixture()
    lines = group_lines(words)
    blocks = group_blocks(lines)
    boxes = [bbox_of([w for ln in b for w in ln]) for b in blocks]
    removed, infos = remove_text(shot, boxes)
    translations = [FIXTURE_TRANSLATIONS[b[0][0]["text"]] for b in blocks]
    rgba, pl = build_overlay(removed, blocks, infos, translations, pick_family())
    comp = composite(shot, rgba)
    for name, arr in [("source", shot), ("removed", removed), ("composite", comp)]:
        Image.fromarray(arr).save(out_dir / f"{name}.png")
    Image.fromarray(rgba, "RGBA").save(out_dir / "overlay_rgba.png")

    checks = []
    checks.append(("word->line->block counts (32 -> 8 -> 4)", (len(words), len(lines), len(blocks)) == (32, 8, 4), (len(words), len(lines), len(blocks))))
    for i, info in enumerate(infos):
        b = info["box"]
        err = float(np.abs(removed[b[1]:b[3], b[0]:b[2]].astype(int) - clean[b[1]:b[3], b[0]:b[2]].astype(int)).mean())
        limit = 2.0 if info["ring_std"] < FLAT_STD else 6.0
        checks.append((f"block {i}: source text removed, MAE vs ground truth <= {limit}", err <= limit, round(err, 2)))
        m = removal_metrics(removed, info)
        if info["ring_std"] < FLAT_STD:
            checks.append((f"block {i}: (real-data proxy) p99 bg distance <= 12", m["p99_bg_dist"] <= 12, round(m["p99_bg_dist"], 1)))
        else:
            checks.append((f"block {i}: (real-data proxy) box edge <= 1.5*ring edge + 3", m["box_edge"] <= 1.5 * m["ring_edge"] + 3, round(m["box_edge"], 1)))
    covered = np.zeros(shot.shape[:2], bool)
    for q in pl:
        covered[q["patch"][1]:q["patch"][3], q["patch"][0]:q["patch"][2]] = True
    checks.append(("overlay alpha == 0 outside all patches", int((rgba[..., 3][~covered] > 0).sum()) == 0, int((rgba[..., 3][~covered] > 0).sum())))
    checks.append(("composite == source outside all patches", int((np.abs(comp.astype(int) - shot.astype(int)).sum(2)[~covered] > 0).sum()) == 0, 0))
    for i, q in enumerate(pl):
        checks.append((f"block {i}: text/bg contrast >= {MIN_CONTRAST}", q["contrast"] >= MIN_CONTRAST, round(q["contrast"], 1)))
        checks.append((f"block {i}: font {q['font_px']}px within [0.6, 1.0] x source {q['src_px']:.1f}px", MIN_FONT_RATIO - 0.05 <= q["font_px"] / q["src_px"] <= 1.05, round(q["font_px"] / q["src_px"], 2)))
        checks.append((f"block {i}: text fits its free rect", q["fits"], q["fits"]))
    width = max(len(c[0]) for c in checks)
    for name, ok, val in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {val}")
    print(f"\nartifacts written to {out_dir.resolve()}")
    sys.exit(0 if all(c[1] for c in checks) else 1)


if __name__ == "__main__":
    main()
