"""Blend renderer for LingoLens (spec section 7).

Ports the reference algorithm from docs/reference/blend_reference.py into
production code, adapted to the project's BlockRecord data structures.

A block is the translation unit: a single word/label, one line, or a paragraph.
The renderer:
  1. Removes source text (ring-median fill for flat backgrounds, ONE inpaint
     call for textured/gradient backgrounds).
  2. Derives foreground/background colours from the source with a WCAG contrast
     guard.
  3. Finds the container rect via flood-fill on the text-removed image.
  4. Computes the free rect (where translated text may legally sit).
  5. Fits the largest pixel font that fits, within [0.6 * src_px, src_px].
  6. Renders patches onto a fully-transparent QImage (only patches are opaque).

This module contains NO window code. It returns a QImage and metrics dict;
only overlay.py shows windows (spec section 4.3: "never subclass or
instantiate a window inside blend.py").

Headless-testable with QT_QPA_PLATFORM=offscreen.
"""
import os
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path

import numpy as np
import cv2

logger = logging.getLogger('lingolens.blend')

# ---------------------------------------------------------------------------
# Constants (spec section 7; mirror blend_reference.py)
# ---------------------------------------------------------------------------
BOX_PAD = 2                # px added around each source box before sampling / masking
RING = 4                   # px ring outside the padded box used to sample the background
FLAT_STD = 6.0             # ring std below this => flat background => solid fill
GLYPH_MIN_DIST = 28.0      # min colour distance from bg for a pixel to count as glyph
GLYPH_REL_DIST = 0.35      # ...or this fraction of the max distance in the box
MIN_CONTRAST = 4.5         # WCAG AA
FLOOD_TOL = 6              # flood-fill tolerance for container detection
MIN_FONT_PX = 8            # never go below this pixel size
MIN_FONT_RATIO = 0.6       # floor at 0.6x source font
MAX_FONT_RATIO = 1.0       # never exceed 1.0x source font (text can expand into free space)
FONT_FAMILIES = ["Segoe UI", "Arial", "DejaVu Sans", "Noto Sans"]

# RTL target languages (spec section 7.6)
RTL_LANGS = {"ar", "ur", "he", "fa"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class BlockInfo:
    """Per-block analysis results from remove_text -> analyse_block."""
    box: Tuple[int, int, int, int]  # padded, clipped box (x0, y0, x1, y1)
    bg: np.ndarray                  # background colour (BGR, 3 floats)
    fg: np.ndarray                  # foreground/glyph colour (BGR, 3 floats)
    ring_std: float                 # std of the ring sample
    glyph_mask: Optional[np.ndarray]  # 0/255 mask over the box, None if flat


@dataclass
class PlaceResult:
    """Placement info for a single block in the overlay."""
    block_index: int
    src_px: float
    font_px: int
    fits: bool
    bg: np.ndarray
    fg: np.ndarray
    contrast: float
    container: Tuple[int, int, int, int]
    free_rect: Tuple[int, int, int, int]
    patch: Tuple[int, int, int, int]
    ring_std: float
    busy: bool
    centered_h: bool
    centered_v: bool
    p99_bg_dist: float
    box_edge: float
    ring_edge: float
    alignment: str
    rtl: bool


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
def _lum_rgb(rgb: np.ndarray) -> float:
    """Relative luminance of an RGB pixel (0.0 = black, 1.0 = white).
    Uses the standard sRGB luminance formula. Input is an RGB triple (0-255).
    """
    c = np.array(rgb, float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast_ratio(fg_rgb: np.ndarray, bg_rgb: np.ndarray) -> float:
    """WCAG contrast ratio between two RGB colors (1.0 = no contrast, 21 = max)."""
    la = _lum_rgb(fg_rgb)
    lb = _lum_rgb(bg_rgb)
    lighter = max(la, lb)
    darker = min(la, lb)
    if lighter == 0 and darker == 0:
        return 1.0
    return (lighter + 0.05) / (darker + 0.05)


def _clip_box(b, W, H):
    """Clip a box (x0, y0, x1, y1) to image bounds."""
    return (max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3]))


# ---------------------------------------------------------------------------
# 7.1 Remove source text
# ---------------------------------------------------------------------------
def _bgr_to_rgb(bgr):
    """Convert BGR to RGB (numpy arrays in this codebase are BGR; Qt/RGB is RGB)."""
    return bgr[..., ::-1]


def analyse_block(img_rgb: np.ndarray, box: Tuple[int, int, int, int]) -> BlockInfo:
    """Analyse a single block's background and glyphs.

    Parameters
    ----------
    img_rgb : np.ndarray (H, W, 3) uint8
        Source image in RGB order (Qt uses RGB).
    box : (x0, y0, x1, y1)
        Source text bounding box in image coordinates.

    Returns
    -------
    BlockInfo with bg (RGB float), fg (RGB float), ring_std, glyph_mask
    """
    H, W = img_rgb.shape[:2]

    # Pad the box by BOX_PAD, then clip
    b = _clip_box((box[0] - BOX_PAD, box[1] - BOX_PAD,
                   box[2] + BOX_PAD, box[3] + BOX_PAD), W, H)
    x0, y0, x1, y1 = b

    if x1 <= x0 or y1 <= y0:
        bg = np.array([128, 128, 128], float)
        return BlockInfo(box=b, bg=bg, fg=np.array([0, 0, 0], float),
                         ring_std=255.0, glyph_mask=None)

    # Sample the RING outside the padded box for the background
    rx0, ry0 = max(0, b[0] - RING), max(0, b[1] - RING)
    rx1, ry1 = min(W, b[2] + RING), min(H, b[3] + RING)

    if rx1 > rx0 and ry1 > ry0:
        ring_region = img_rgb[ry0:ry1, rx0:rx1].astype(np.float64)
        # Exclude the padded box area from the ring sample
        keep_mask = np.ones((ry1 - ry0, rx1 - rx0), bool)
        bx0 = b[0] - rx0
        by0 = b[1] - ry0
        bx1 = b[2] - rx0
        by1 = b[3] - ry0
        if bx0 < keep_mask.shape[1] and by0 < keep_mask.shape[0]:
            keep_mask[max(0, by0):min(keep_mask.shape[0], by1),
                      max(0, bx0):min(keep_mask.shape[1], bx1)] = False
        ring_pixels = ring_region[keep_mask]
        if len(ring_pixels) > 0:
            bg = np.median(ring_pixels, axis=0)
        else:
            bg = np.array([128, 128, 128], float)
        ring_std = float(np.mean(np.std(ring_pixels, axis=0))) if len(ring_pixels) > 1 else 255.0
    else:
        bg = np.array([128, 128, 128], float)
        ring_std = float(np.std(img_rgb.reshape(-1, 3)[:100], axis=0).mean()) if img_rgb.size > 300 else 255.0

    # Build glyph mask: pixels deviating from the background
    roi = img_rgb[y0:y1, x0:x1].astype(np.float64)
    dist = np.linalg.norm(roi - bg, axis=2)
    threshold = max(GLYPH_MIN_DIST, GLYPH_REL_DIST * dist.max()) if dist.max() > 0 else GLYPH_MIN_DIST
    glyph_mask = (dist > threshold).astype(np.uint8) * 255

    # Foreground colour: median of glyph pixels at or above the 60th percentile of distance
    if glyph_mask.any():
        glyph_dist = dist[glyph_mask > 0]
        pct60 = np.percentile(glyph_dist, 60)
        glyph_pixels = roi[dist >= pct60]
        fg = np.median(glyph_pixels, axis=0) if len(glyph_pixels) > 0 else np.median(roi[dist > GLYPH_MIN_DIST * 0.5], axis=0)
    else:
        # No detectable glyphs — fall back to source sample's fg (caller handles contrast)
        fg = np.array([0, 0, 0] if _lum_rgb(bg) > 0.4 else [255, 255, 255], float)

    return BlockInfo(box=b, bg=bg, fg=fg, ring_std=ring_std,
                     glyph_mask=glyph_mask if glyph_mask.any() else None)


def remove_text(img_rgb: np.ndarray, boxes: List[Tuple[int, int, int, int]]) -> Tuple[np.ndarray, List[BlockInfo]]:
    """Remove source text from the image.

    - Flat backgrounds (ring_std < FLAT_STD): fill the entire padded box with
      the ring median colour. This also removes anti-aliasing and ClearType
      fringes. ONE pass per flat block, no inpaint.
    - Textured/gradient backgrounds: build a glyph mask for each block, dilate
      2x, OR all masks into one full-image mask, and call cv2.inpaint ONCE
      for the whole image.
    - Busy backgrounds (ring_std > 25): fill the padded box with the ring
      median (opaque), flag busy=True. A smudged translation is worse than
      a visible backdrop.

    Returns (text_removed_image_rgb, list_of_BlockInfo)
    """
    out = img_rgb.copy()
    infos: List[BlockInfo] = []
    inpaint_mask = np.zeros(img_rgb.shape[:2], np.uint8)
    k = np.ones((3, 3), np.uint8)

    for box in boxes:
        info = analyse_block(img_rgb, box)
        infos.append(info)

        if info.ring_std > 25:
            # Busy background: solid fill, flag busy
            out[info.box[1]:info.box[3], info.box[0]:info.box[2]] = info.bg.astype(np.uint8)
            info_busy = True
        elif info.ring_std < FLAT_STD:
            # Flat background: solid fill (removes text + AA halos)
            out[info.box[1]:info.box[3], info.box[0]:info.box[2]] = info.bg.astype(np.uint8)
            info_busy = False
        else:
            # Textured/gradient: dilate glyph mask, accumulate into single inpaint mask
            if info.glyph_mask is not None:
                mask = np.zeros(img_rgb.shape[:2], np.uint8)
                gx0, gy0 = info.box[0], info.box[1]
                gw, gh = info.box[2] - info.box[0], info.box[3] - info.box[1]
                mask[gy0:gy0 + gh, gx0:gx0 + gw] = cv2.dilate(info.glyph_mask, k, iterations=2)
                inpaint_mask |= mask
            info_busy = False

        # Store busy flag on info
        info_busy_attr = hasattr(info, 'busy')
        if not info_busy_attr:
            pass  # BlockInfo doesn't have a busy field; we track separately

    if inpaint_mask.any():
        out = cv2.inpaint(out, inpaint_mask, 3, cv2.INPAINT_TELEA)

    return out, infos


def removal_metrics(img_removed: np.ndarray, info: BlockInfo) -> Dict[str, float]:
    """Ground-truth-free quality proxies for text removal (usable on REAL captures).

    flat blocks: p99 colour distance of the box from the ring background <= 12
    textured:    box edge <= 1.5 x ring edge + 3
    """
    b = info.box
    H, W = img_removed.shape[:2]
    roi = img_removed[b[1]:b[3], b[0]:b[2]].astype(np.float32)
    p99 = float(np.percentile(np.linalg.norm(roi - info.bg, axis=2), 99))

    g = cv2.cvtColor(img_removed, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mag = np.abs(np.gradient(g)[0]) + np.abs(np.gradient(g)[1])

    ext_box = _clip_box((b[0] - 3 * RING, b[1] - 3 * RING, b[2] + 3 * RING, b[3] + 3 * RING), W, H)
    ring_mask = np.ones((ext_box[3] - ext_box[1], ext_box[2] - ext_box[0]), bool)
    ring_mask[b[1] - ext_box[1]:b[3] - ext_box[1],
              b[0] - ext_box[0]:b[2] - ext_box[0]] = False
    ring_pixels = g[ext_box[1]:ext_box[3], ext_box[0]:ext_box[2]][ring_mask]
    ring_edge = float(ring_pixels.mean())
    box_edge = float(mag[b[1]:b[3], b[0]:b[2]].mean())

    return dict(p99_bg_dist=p99, box_edge=box_edge, ring_edge=ring_edge)


# ---------------------------------------------------------------------------
# 7.3 Container and free space
# ---------------------------------------------------------------------------
def container_rect(removed: np.ndarray, box: Tuple[int, int, int, int],
                   tol: int = FLOOD_TOL) -> Tuple[int, int, int, int]:
    """Bounding rect of the region around the block with ~the same background.

    Uses cv2.floodFill on the text-removed image (4-connected, mask-only).
    Guards against leaks: if the region exceeds 4x box width + 80 or 6x box
    height + 80, fall back to a grown box.
    """
    H, W = removed.shape[:2]
    seed = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)

    # Clip seed to image bounds
    sx = max(0, min(seed[0], W - 1))
    sy = max(0, min(seed[1], H - 1))

    m = np.zeros((H + 2, W + 2), np.uint8)
    try:
        cv2.floodFill(removed.copy(), m, (sx, sy), (0, 0, 0),
                      (tol,) * 3, (tol,) * 3,
                      4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8))
    except Exception:
        return box

    ys, xs = np.where(m[1:-1, 1:-1] > 0)
    bw, bh = box[2] - box[0], box[3] - box[1]

    if len(xs) == 0:
        return box

    r = (min(int(xs.min()), box[0]), min(int(ys.min()), box[1]),
         max(int(xs.max()) + 1, box[2]), max(int(ys.max()) + 1, box[3]))

    if (r[2] - r[0]) > 4 * bw + 80 or (r[3] - r[1]) > 6 * bh + 80:
        return (max(0, box[0] - bw // 2), box[1],
                min(W, box[2] + bw // 2), min(H, box[3] + 2 * bh))

    return r


def free_rect(box: Tuple[int, int, int, int],
              container: Tuple[int, int, int, int],
              others: List[Tuple[int, int, int, int]],
              inset: int, gap: int = 6) -> Tuple[int, int, int, int]:
    """Room the translated text may occupy: grow right/down inside the container,
    stop at neighbouring blocks.
    """
    x1_right = container[2] - inset
    y1_bottom = container[3] - inset

    for o in others:
        if o == box:
            continue
        # Neighbour to the right (overlapping rows): stop horizontal growth
        if o[0] >= box[2] - 2 and o[1] < box[3] and o[3] > box[1]:
            x1_right = min(x1_right, o[0] - gap)
        # Neighbour below (overlapping columns): stop vertical growth
        if o[1] >= box[3] - 2 and o[0] < x1_right and o[2] > box[0]:
            y1_bottom = min(y1_bottom, o[1] - gap)

    return (box[0], box[1], max(x1_right, box[2]), max(y1_bottom, box[3]))


# ---------------------------------------------------------------------------
# 7.4 Fit
# ---------------------------------------------------------------------------
def pick_family():
    """Return the first installed font family from FONT_FAMILIES, else default."""
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFont, QFontDatabase
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    have = set(QFontDatabase().families())
    return next((f for f in FONT_FAMILIES if f in have), QFont().defaultFamily())


def fit_font(text: str, family: str, w: int, h: int, src_px: float) -> Tuple[int, bool]:
    """Largest pixel size <= src_px whose wrapped text fits (w, h).

    Returns (pixel_size, fits). Pixel size is clamped to [MIN_FONT_PX, src_px].
    """
    from PyQt5.QtCore import Qt, QRect
    from PyQt5.QtGui import QFont, QFontMetrics

    lo = max(MIN_FONT_PX, int(src_px * MIN_FONT_RATIO))
    hi = int(src_px)

    for s in range(hi, lo - 1, -1):
        f = QFont(family)
        f.setPixelSize(s)
        r = QFontMetrics(f).boundingRect(
            QRect(0, 0, max(1, w), 100000),
            Qt.TextWordWrap | Qt.AlignLeft, text)
        if r.height() <= h and r.width() <= w:
            return s, True
    return lo, False


# ---------------------------------------------------------------------------
# 7.7 Patches and output
# ---------------------------------------------------------------------------
def is_rtl(dest_lang: str) -> bool:
    """Check if the destination language uses right-to-left script."""
    return dest_lang in RTL_LANGS


def build_overlay(capture_rgb: np.ndarray,
                  blocks,
                  translations: List[str],
                  dest_lang: str = "en") -> Tuple[Optional['QImage'], List[PlaceResult], Dict[str, Any]]:
    """Build the overlay QImage and compute per-block placement metrics.

    Parameters
    ----------
    capture_rgb : np.ndarray (H, W, 3) uint8
        The captured screen region in RGB order.
    blocks : list of BlockRecord
        Grouped blocks from blocks.build_blocks().
    translations : list of str
        One translated text per block (indexed by block position).
    dest_lang : str
        Destination language code (for RTL detection).

    Returns
    -------
    (QImage or None, list of PlaceResult, metrics dict)
    """
    from PyQt5.QtCore import Qt, QRect
    from PyQt5.QtGui import QImage, QPainter, QFont, QFontMetrics, QColor
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    H, W = capture_rgb.shape[:2]
    qimg = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
    qimg.fill(Qt.transparent)
    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    family = pick_family()
    rtl = is_rtl(dest_lang)
    if rtl:
        painter.setLayoutDirection(Qt.RightToLeft)

    box_tuples = [(int(b.bbox[0]), int(b.bbox[1]), int(b.bbox[2]), int(b.bbox[3])) for b in blocks]

    # 1. Remove source text from the capture
    removed, infos = remove_text(capture_rgb, box_tuples)

    placements: List[PlaceResult] = []
    metrics_blocks: List[Dict] = []

    for i, block in enumerate(blocks):
        x0, y0, x1, y1 = box_tuples[i]
        src_px = block.src_px
        info = infos[i]
        bg_rgb = info.bg
        fg_rgb = info.fg

        text = translations[i] if i < len(translations) else block.text

        # Skip blocks with empty or unchanged translation (spec 7.7)
        if not text or not text.strip():
            placements.append(_empty_place(src_px, bg_rgb, fg_rgb, info.ring_std, (x0, y0, x1, y1), block_index=i))
            continue
        if text.strip().lower() == block.text.strip().lower():
            placements.append(_empty_place(src_px, bg_rgb, fg_rgb, info.ring_std, (x0, y0, x1, y1), block_index=i))
            continue

        # 7.2 Colours — enforce WCAG contrast
        contrast = _contrast_ratio(fg_rgb, bg_rgb)
        busy = info.ring_std > 25
        if contrast < MIN_CONTRAST:
            if _lum_rgb(bg_rgb) > 0.4:
                fg_rgb = np.array([0, 0, 0], float)
            else:
                fg_rgb = np.array([255, 255, 255], float)
            contrast = _contrast_ratio(fg_rgb, bg_rgb)

        # 7.3 Container
        cont = container_rect(removed, (x0, y0, x1, y1))

        # Free rect
        inset = max(4, round(0.35 * src_px))
        avail = free_rect((x0, y0, x1, y1), cont, box_tuples, inset)

        # 7.4 Fit
        free_w = avail[2] - avail[0]
        free_h = avail[3] - avail[1]
        font_px, fits = fit_font(text, family, free_w, free_h, src_px)

        # 7.5 Alignment (mirrors blend_reference.py)
        cw = cont[2] - cont[0]
        box_w = x1 - x0
        centered_h = (y1 - y0) > 0 and abs((x0 + x1) / 2 - (cont[0] + cont[2]) / 2) < 0.06 * cw and cw < 3 * box_w
        centered_v = cont[3] > cont[1] and abs((y0 + y1) / 2 - (cont[1] + cont[3]) / 2) < 0.10 * (cont[3] - cont[1])

        if centered_h:
            alignment = "center"
            text_rect = QRect(cont[0] + inset, avail[1], cw - 2 * inset, avail[3] - avail[1])
            flags = Qt.TextWordWrap | Qt.AlignHCenter | Qt.AlignTop
        else:
            alignment = "left"
            text_rect = QRect(avail[0], avail[1], avail[2] - avail[0], avail[3] - avail[1])
            flags = Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop
        if rtl:
            alignment = "right"
            flags = Qt.TextWordWrap | Qt.AlignRight | Qt.AlignVCenter

        # Measure rendered text for vertical centering and patch computation
        font = QFont(family)
        font.setPixelSize(font_px)
        painter.setFont(font)
        fm = QFontMetrics(font)
        br = fm.boundingRect(text_rect, flags, text)

        if centered_v:
            text_rect.moveTop(cont[1] + max(0, ((cont[3] - cont[1]) - br.height()) // 2))
        elif (y1 - y0) > 0 and font_px and br.height() < (y1 - y0):
            text_rect.moveTop(y0 + ((y1 - y0) - br.height()) // 2)

        # 7.7 Patch = union(source box, text rect), clipped to image
        patch = (min(x0, text_rect.left()), min(y0, text_rect.top()),
                 max(x1, text_rect.left() + text_rect.width()),
                 max(y1, text_rect.top() + br.height()))
        patch = _clip_box(patch, W, H)

        # Copy text-removed pixels into the patch (opaque)
        if patch[2] > patch[0] and patch[3] > patch[1]:
            crop_rgb = np.ascontiguousarray(removed[patch[1]:patch[3], patch[0]:patch[2]])
            bytes_per_line = crop_rgb.shape[1] * 3
            crop_img = QImage(crop_rgb.data, crop_rgb.shape[1], crop_rgb.shape[0],
                              bytes_per_line, QImage.Format_RGB888).copy()
            painter.drawImage(patch[0], patch[1], crop_img)

        # Draw the translation text
        pen = QColor(int(fg_rgb[0]), int(fg_rgb[1]), int(fg_rgb[2]))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawText(text_rect, flags, text)

        # Metrics
        m = removal_metrics(removed, info)
        placements.append(PlaceResult(
            block_index=i, src_px=src_px, font_px=font_px, fits=fits,
            bg=bg_rgb, fg=fg_rgb, contrast=contrast,
            container=cont, free_rect=avail, patch=patch,
            ring_std=info.ring_std, busy=busy,
            centered_h=centered_h, centered_v=centered_v,
            p99_bg_dist=m['p99_bg_dist'], box_edge=m['box_edge'], ring_edge=m['ring_edge'],
            alignment=alignment, rtl=rtl))

        metrics_blocks.append({
            'bbox': [x0, y0, x1, y1],
            'n_lines': block.n_lines,
            'src_px': round(src_px, 1),
            'font_px': font_px,
            'ratio': round(font_px / src_px, 2) if src_px > 0 else 0,
            'contrast': round(contrast, 1),
            'fits': fits,
            'busy': busy,
            'container': list(cont),
            'free_rect': list(avail),
            'patch': list(patch),
            'ring_std': round(info.ring_std, 1),
            'p99_bg_dist': round(m['p99_bg_dist'], 1),
            'box_edge': round(m['box_edge'], 1),
            'ring_edge': round(m['ring_edge'], 1),
        })

    painter.end()

    # Compute pixels_changed_outside_patches (spec 11, criterion 6)
    rgba = _qimage_to_rgba(qimg)
    alpha = rgba[..., 3:4]
    covered = np.zeros((H, W), bool)
    for p in placements:
        pt = p.patch
        if pt[2] > pt[0] and pt[3] > pt[1]:
            covered[pt[1]:pt[3], pt[0]:pt[2]] = True
    changed_outside = int((alpha[~covered] > 0).sum())

    metrics = {
        'counts': {
            'words': sum(b.n_words for b in blocks),
            'lines': sum(b.n_lines for b in blocks),
            'blocks': len(blocks),
        },
        'blocks': metrics_blocks,
        'pixels_changed_outside_patches': changed_outside,
    }

    return qimg, placements, metrics


def _empty_place(src_px, bg_rgb, fg_rgb, ring_std, bbox, block_index=0):
    """Create a PlaceResult for a skipped block (no translation / unchanged)."""
    return PlaceResult(
        block_index=block_index, src_px=src_px, font_px=0, fits=False, bg=bg_rgb, fg=fg_rgb,
        contrast=0, container=bbox, free_rect=bbox, patch=bbox,
        ring_std=ring_std, busy=False, centered_h=False, centered_v=False,
        p99_bg_dist=0, box_edge=0, ring_edge=0,
        alignment="left", rtl=False)


def _qimage_to_rgba(qimg, capture_rgb: np.ndarray = None) -> np.ndarray:
    """Convert a QImage (Format_ARGB32_Premultiplied) to HxWx4 RGBA uint8.

    If capture_rgb is provided, the RGB channels of transparent pixels
    (alpha == 0) are filled with the corresponding source pixels so the saved
    PNG is visually correct in viewers that ignore alpha.
    """
    from PyQt5.QtGui import QImage
    qimg = qimg.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    h, w = qimg.height(), qimg.width()
    ptr = qimg.constBits()
    ptr.setsize(h * qimg.bytesPerLine())
    argb = np.frombuffer(ptr, np.uint8).reshape(h, qimg.bytesPerLine() // 4, 4)[:, :w].copy()
    a = argb[..., 3:4].astype(np.float32)
    rgb = np.where(a > 0, argb[..., :3].astype(np.float32) * 255.0 / np.maximum(a, 1), 0)
    # ARGB32 is BGRA in memory on little-endian machines
    rgba = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], a[..., 0] / 255.0 * 255]).clip(0, 255).astype(np.uint8)
    # Fill source RGB into transparent areas so the PNG is visually correct
    if capture_rgb is not None:
        alpha_mask = rgba[..., 3] == 0
        rgba[alpha_mask, :3] = capture_rgb[alpha_mask]
    return rgba


def composite(shot_rgb: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    """Alpha-blend the overlay over the capture: comp = overlay*a + shot*(1-a)."""
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    return (rgba[..., :3] * a + shot_rgb * (1 - a)).astype(np.uint8)


def render_overlay(capture_rgb: np.ndarray, blocks, translations: List[str],
                   dest_lang: str = "en") -> Tuple[np.ndarray, List[PlaceResult], Dict]:
    """High-level entry: capture_rgb -> (rgba_overlay, placements, metrics).

    capture_rgb is (H, W, 3) uint8 in RGB order.
    Returns overlay as HxWx4 RGBA uint8.
    """
    qimg, placements, metrics = build_overlay(capture_rgb, blocks, translations, dest_lang)
    if qimg is None:
        H, W = capture_rgb.shape[:2]
        rgba = np.zeros((H, W, 4), np.uint8)
        rgba[..., :3] = capture_rgb
        return rgba, [], metrics

    rgba = _qimage_to_rgba(qimg, capture_rgb)
    return rgba, placements, metrics
