"""Block grouping for LingoLens.

Groups OCR word boxes into lines, then lines into translation blocks.
A block is the translation unit: a single word/label, one line, or a paragraph.

Pure logic -- no window code, no network. Headless-testable.

Word format (dict): {text, x_min, x_max, y_min, y_max, cx, cy, width, height}
Line format: list of word dicts, sorted left-to-right
Block format: list of lines (list of list of word dicts)
"""
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Constants (spec section 6)
# ---------------------------------------------------------------------------
LINE_MERGE_CY = 0.5        # word joins a line if |cy - line_cy| < LINE_MERGE_CY * line_height
COLUMN_GAP = 1.5           # split a line at horizontal gaps > COLUMN_GAP * avg_height
PARA_GAP = 0.9             # lines merge into a block if vertical gap < PARA_GAP * avg_height
PARA_LEFT_ALIGN = 1.0      # ...and left edges differ by < PARA_LEFT_ALIGN * height
PARA_HEIGHT_RATIO = (0.6, 1.6)  # height ratio bounds for merging (heading vs body)
MIN_WORD_PIXELS = 3        # drop boxes under this many pixels in any dimension

# CJK character ranges (Han, Hiragana, Katakana, Hangul, halfwidth Katakana)
_CJK_RANGES = [
    (0x4E00, 0x9FFF),
    (0x3040, 0x309F),
    (0x30A0, 0x30FF),
    (0xAC00, 0xD7AF),
    (0xFF60, 0xFF9F),
]
_CJK_THRESHOLD = 0.5       # fraction of CJK chars needed to trigger empty-string join


# ---------------------------------------------------------------------------
# CJK detection for text joining
# ---------------------------------------------------------------------------
def _is_cjk_char(ch: str) -> bool:
    cp = ord(ch)
    for lo, hi in _CJK_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def _majority_cjk(text: str) -> bool:
    """True if the majority of non-space characters in text are CJK."""
    cjk = 0
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        if _is_cjk_char(ch):
            cjk += 1
    return total > 0 and (cjk / total) >= _CJK_THRESHOLD


def _join_words(words: List[dict]) -> str:
    """Join word texts: space-separated for Latin, empty-separated for CJK."""
    texts = [w['text'].strip() for w in words if w.get('text', '').strip()]
    if not texts:
        return ""
    combined = " ".join(texts)
    if _majority_cjk(combined):
        return "".join(texts)
    return combined


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def _normalize_words(words: List[dict]) -> List[dict]:
    """Enforce x0<x1, y0<y1; drop boxes under MIN_WORD_PIXELS; recompute cx/cy."""
    out = []
    for w in words:
        x0, x1 = sorted([w['x_min'], w['x_max']])
        y0, y1 = sorted([w['y_min'], w['y_max']])
        if (x1 - x0) < MIN_WORD_PIXELS or (y1 - y0) < MIN_WORD_PIXELS:
            continue
        nw = dict(w)
        nw['x_min'], nw['x_max'] = x0, x1
        nw['y_min'], nw['y_max'] = y0, y1
        nw['cx'] = (x0 + x1) / 2
        nw['cy'] = (y0 + y1) / 2
        nw['width'] = x1 - x0
        nw['height'] = y1 - y0
        out.append(nw)
    return out


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------
def group_words_into_lines(words: List[dict]) -> List[List[dict]]:
    """Group words into text lines, splitting at large horizontal gaps.

    Steps:
    1. Normalise: enforce x0<x1, y0<y1, drop tiny boxes, recompute cx/cy.
    2. Sort by (cy, cx) and assign each word to the nearest line by vertical
       proximity: |cy - line_cy| < LINE_MERGE_CY * line_height.
    3. Split each line at horizontal gaps > COLUMN_GAP * avg_height
       (handles columns, separate buttons on one row).
    4. Sort output top-to-bottom, left-to-right.
    """
    ws = _normalize_words(words)
    if not ws:
        return []

    ws.sort(key=lambda w: (w['cy'], w['cx']))
    lines: List[List[dict]] = []
    for w in ws:
        placed = False
        for ln in lines:
            line_cy = float(np.mean([x['cy'] for x in ln]))
            line_h = float(np.mean([x['height'] for x in ln]))
            if abs(w['cy'] - line_cy) < LINE_MERGE_CY * line_h:
                ln.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])

    # Split each line at big horizontal gaps (columns / separate buttons)
    out: List[List[dict]] = []
    for ln in lines:
        ln.sort(key=lambda w: w['cx'])
        seg = [ln[0]]
        for a, b in zip(ln, ln[1:]):
            gap = b['x_min'] - a['x_max']
            avg_h = (a['height'] + b['height']) / 2
            if gap > COLUMN_GAP * avg_h:
                out.append(seg)
                seg = [b]
            else:
                seg.append(b)
        out.append(seg)

    # Sort by position: top-to-bottom, then left-to-right
    out.sort(key=lambda l: (l[0]['cy'], l[0]['cx']))
    return out


def group_lines_into_blocks(lines: List[List[dict]]) -> List[List[List[dict]]]:
    """Group lines into blocks (translation units).

    A block is one or more vertically-stacked lines that form a single
    paragraph. Merging requires ALL of:
    - vertical gap < PARA_GAP * avg_height
    - horizontal overlap between consecutive lines
    - left edges within PARA_LEFT_ALIGN * height
    - height ratio within PARA_HEIGHT_RATIO (heading vs body guard)

    Returns a list of blocks; each block is a list of lines.
    """
    if not lines:
        return []

    blocks: List[List[List[dict]]] = []
    for ln in lines:
        b = (min(w['x_min'] for w in ln),
             min(w['y_min'] for w in ln),
             max(w['x_max'] for w in ln),
             max(w['y_max'] for w in ln))
        h = b[3] - b[1]
        merged = False
        for blk in blocks:
            prev_ln = blk[-1]
            pb = (min(w['x_min'] for w in prev_ln),
                  min(w['y_min'] for w in prev_ln),
                  max(w['x_max'] for w in prev_ln),
                  max(w['y_max'] for w in prev_ln))
            ph = pb[3] - pb[1]
            gap = b[1] - pb[3]
            if (0 <= gap < PARA_GAP * (h + ph) / 2
                    and min(b[2], pb[2]) > max(b[0], pb[0])    # horizontal overlap
                    and abs(b[0] - pb[0]) < PARA_LEFT_ALIGN * h  # left-align
                    and PARA_HEIGHT_RATIO[0] < h / max(ph, 1) < PARA_HEIGHT_RATIO[1]):  # height ratio
                blk.append(ln)
                merged = True
                break
        if not merged:
            blocks.append([ln])

    # Sort blocks top-to-bottom, left-to-right
    blocks.sort(key=lambda blk: (blk[0][0]['cy'], blk[0][0]['cx']))
    return blocks


@dataclass
class BlockRecord:
    """A computed block with metadata for rendering."""
    words: List[dict]
    lines: List[List[dict]]
    bbox: Tuple[int, int, int, int]
    n_lines: int
    n_words: int
    text: str
    src_px: float


def _bbox_of(words: List[dict]) -> Tuple[int, int, int, int]:
    """Bounding box of a list of words: (x_min, y_min, x_max, y_max)."""
    return (int(min(w['x_min'] for w in words)),
            int(min(w['y_min'] for w in words)),
            int(max(w['x_max'] for w in words)),
            int(max(w['y_max'] for w in words)))


def _estimate_src_px(block_words: List[dict]) -> float:
    """Source font size estimate: median line height / 1.25, floor 9."""
    if not block_words:
        return 9.0
    heights = sorted(w['height'] for w in block_words)
    median_h = float(heights[len(heights) // 2])
    return max(9.0, median_h / 1.25)


def build_blocks(words: List[dict]) -> List[BlockRecord]:
    """Full pipeline: words -> lines -> blocks, with metadata.

    Returns a list of BlockRecord dataclasses.
    """
    lines = group_words_into_lines(words)
    blocks = group_lines_into_blocks(lines)
    records = []
    for blk in blocks:
        all_w = [w for ln in blk for w in ln]
        if not all_w:
            continue
        text = _join_words(all_w)
        bbox = _bbox_of(all_w)
        src_px = _estimate_src_px(all_w)
        records.append(BlockRecord(
            words=all_w,
            lines=blk,
            bbox=bbox,
            n_lines=len(blk),
            n_words=len(all_w),
            text=text,
            src_px=src_px,
        ))
    return records


# ---------------------------------------------------------------------------
# Backward-compatible re-exports (spec section 4: keep old names working)
# ---------------------------------------------------------------------------
def _group_words_into_lines(words: List[dict]) -> List[List[dict]]:
    """Back-compat wrapper for overlay.py / legacy tests."""
    return group_words_into_lines(words)


def _group_lines_into_paragraphs(lines: List[List[dict]]) -> List[List[List[dict]]]:
    """Back-compat wrapper for overlay.py / legacy tests."""
    return group_lines_into_blocks(lines)


def _line_bbox(line_words: List[dict]) -> Tuple[int, int, int, int]:
    return _bbox_of(line_words)


def _paragraph_bbox(para_lines: List[List[dict]]) -> Tuple[int, int, int, int]:
    all_w = [w for ln in para_lines for w in ln]
    return _bbox_of(all_w)


def _estimate_font_size(words):
    """Back-compat: estimate font size from word heights (floor 8).

    Matches the old overlay.py behaviour: int(median_height * 0.75),
    floor 8.  Used by legacy tests and the back-compat wrapper.
    """
    if not words:
        return 12
    heights = sorted(w['height'] for w in words)
    median_h = float(heights[len(heights) // 2])
    return max(8, int(median_h * 0.75))
