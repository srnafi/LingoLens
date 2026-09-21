"""P2 Detection and grouping tests (spec section 9 / 10, defect 5 & 7).

Run: QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python/tests/ -q
"""
import os
import sys
import inspect
import numpy as np
from pathlib import Path

_python_dir = str(Path(__file__).resolve().parent.parent)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

from tests.fixtures import make_fixture, FIXTURE_TRANSLATIONS
import blocks
import detector
import overlay


# ---------------------------------------------------------------------------
# Helper: assert a word box has x_min < x_max and y_min < y_max.
# ---------------------------------------------------------------------------
def _assert_box_valid(w):
    assert w['x_min'] < w['x_max'], f"x_min ({w['x_min']}) >= x_max ({w['x_max']})"
    assert w['y_min'] < w['y_max'], f"y_min ({w['y_min']}) >= y_max ({w['y_max']})"


# ---------------------------------------------------------------------------
# Test: fixture yields 32 words -> 8 lines -> 4 blocks
# ---------------------------------------------------------------------------
def test_blocks_fixture():
    """Fixture: 32 words -> 8 lines -> 4 blocks.

    Fails on old code: grouping merges unrelated text (no horizontal
    overlap/alignment check, no COLUMN_GAP split). Old code returns 2.
    """
    shot, clean, words = make_fixture()
    assert len(words) == 32, f"Expected 32 words in fixture, got {len(words)}"

    # Verify all fixture boxes are sane
    for w in words:
        _assert_box_valid(w)

    lines = blocks.group_words_into_lines(words)
    assert len(lines) == 8, (
        f"Expected 8 lines, got {len(lines)}. "
        "Old group_lines does no COLUMN_GAP split (spec 6.2)."
    )

    block_records = blocks.build_blocks(words)
    assert len(block_records) == 4, (
        f"Expected 4 blocks, got {len(block_records)}. "
        "Old code merges unrelated text — no horizontal overlap/alignment check (defect 5)."
    )

    # Verify each block has sane bboxes
    for blk in block_records:
        x0, y0, x1, y1 = blk.bbox
        assert x0 < x1 and y0 < y1, f"Block bbox inverted: {blk.bbox}"


# ---------------------------------------------------------------------------
# Test: two far-apart words on one row -> 2 blocks; two columns -> separate blocks
# ---------------------------------------------------------------------------
def test_blocks_columns():
    """Two far-apart words on one row -> 2 blocks (COLUMN_GAP split).

    The words share the same cy so they start in the same line, but the
    horizontal gap exceeds COLUMN_GAP, so group_words_into_lines splits
    them into 2 line segments -> 2 blocks.
    """
    words = [
        {"text": "Left", "x_min": 10, "x_max": 50, "y_min": 100, "y_max": 120,
         "cx": 30, "cy": 110, "width": 40, "height": 20},
        {"text": "Right", "x_min": 300, "x_max": 350, "y_min": 100, "y_max": 120,
         "cx": 325, "cy": 110, "width": 50, "height": 20},
    ]
    lines = blocks.group_words_into_lines(words)
    blocks_list = blocks.group_lines_into_blocks(lines)
    # COLUMN_GAP splits far-apart words into separate line segments
    assert len(lines) == 2, (
        f"Expected 2 line segments (COLUMN_GAP split), got {len(lines)}"
    )
    assert len(blocks_list) == 2, (
        f"Expected 2 blocks (far-apart words on one row), got {len(blocks_list)}"
    )


def test_blocks_two_columns():
    """Two columns of text -> separate blocks."""
    words = [
        {"text": "Col1A", "x_min": 10, "x_max": 50, "y_min": 100, "y_max": 120,
         "cx": 30, "cy": 110, "width": 40, "height": 20},
        {"text": "Col1B", "x_min": 10, "x_max": 50, "y_min": 125, "y_max": 145,
         "cx": 30, "cy": 135, "width": 40, "height": 20},
        {"text": "Col2A", "x_min": 200, "x_max": 240, "y_min": 100, "y_max": 120,
         "cx": 220, "cy": 110, "width": 40, "height": 20},
        {"text": "Col2B", "x_min": 200, "x_max": 240, "y_min": 125, "y_max": 145,
         "cx": 220, "cy": 135, "width": 40, "height": 20},
    ]
    lines = blocks.group_words_into_lines(words)
    blocks_list = blocks.group_lines_into_blocks(lines)
    assert len(blocks_list) == 2, (
        f"Expected 2 blocks (two columns), got {len(blocks_list)}"
    )


# ---------------------------------------------------------------------------
# Test: different heights (heading vs body) are not merged
# ---------------------------------------------------------------------------
def test_blocks_heading_vs_body():
    """A heading (taller) and body text (shorter) on separate lines
    with a small gap should NOT merge if their height ratio is outside
    the PARA_HEIGHT_RATIO bounds."""
    # Heading: height 40; Body: height 14. Ratio = 40/14 = 2.85 > 1.6
    heading = [{"text": "TITLE", "x_min": 10, "x_max": 200, "y_min": 100, "y_max": 140,
                "cx": 105, "cy": 120, "width": 190, "height": 40}]
    body_line = [{"text": "body", "x_min": 10, "x_max": 60, "y_min": 142, "y_max": 156,
                  "cx": 35, "cy": 149, "width": 50, "height": 14}]
    lines = blocks.group_words_into_lines(heading + body_line)
    blocks_list = blocks.group_lines_into_blocks(lines)
    assert len(blocks_list) == 2, (
        f"Expected 2 blocks (heading vs body, height ratio violated), "
        f"got {len(blocks_list)}"
    )


# ---------------------------------------------------------------------------
# Test: detector postprocess (defect 7)
# ---------------------------------------------------------------------------
def test_detector_postprocess_conf_threshold():
    """postprocess_predictions drops boxes below conf_thr."""
    preds = np.array([
        [0.1, 0.1, 0.3, 0.3, 0.1],   # conf 0.1 < 0.3 -> dropped
        [0.1, 0.1, 0.3, 0.3, 0.5],   # conf 0.5 >= 0.3 -> kept
        [0.1, 0.1, 0.3, 0.3, 0.4],   # conf 0.4 >= 0.3 -> kept (overlaps with above, NMS)
    ])
    kept = detector.postprocess_predictions(preds, sx=100, sy=100, img_w=100, img_h=100,
                                            conf_thr=0.3, iou_thr=0.1)
    assert len(kept) <= 2, f"Expected at most 2 boxes after conf+NMS, got {len(kept)}"
    for b in kept:
        assert b[4] >= 0.3, f"Box with conf {b[4]} below threshold 0.3"


def test_detector_postprocess_clamp():
    """postprocess_predictions clamps boxes to image bounds."""
    preds = np.array([
        [0.0, 0.0, 5.0, 5.0, 0.9],   # normalized coords exceed 1.0 -> clamped
    ])
    kept = detector.postprocess_predictions(preds, sx=100, sy=100, img_w=100, img_h=100,
                                            conf_thr=0.1, iou_thr=0.1)
    assert len(kept) == 1, f"Expected 1 box, got {len(kept)}"
    b = kept[0]
    assert b[0] >= 0 and b[1] >= 0, f"Box not clamped to 0: {b}"
    assert b[2] <= 100 and b[3] <= 100, f"Box exceeds image: {b}"


def test_detector_postprocess_min_size():
    """postprocess_predictions drops boxes smaller than MIN_BOX_PX."""
    preds = np.array([
        [0.1, 0.1, 0.101, 0.101, 0.9],  # in 100px image -> ~0.1px -> dropped
    ])
    kept = detector.postprocess_predictions(preds, sx=100, sy=100, img_w=100, img_h=100,
                                            conf_thr=0.1, iou_thr=0.1)
    assert len(kept) == 0, f"Expected 0 boxes (too small), got {len(kept)}"


def test_detector_postprocess_zero_rows():
    """postprocess_predictions drops all-zero rows."""
    preds = np.array([
        [0.0, 0.0, 0.0, 0.0, 0.0],   # all-zero row
        [0.1, 0.1, 0.3, 0.3, 0.5],   # valid
    ])
    kept = detector.postprocess_predictions(preds, sx=100, sy=100, img_w=100, img_h=100,
                                            conf_thr=0.1, iou_thr=0.1)
    assert len(kept) == 1, f"Expected 1 box (zero row dropped), got {len(kept)}"


def test_detector_has_conf_threshold():
    """Detector has CONF_THRESHOLD and NMS_IOU constants."""
    assert hasattr(detector, "CONF_THRESHOLD"), "defect 7: no CONF_THRESHOLD"
    assert hasattr(detector, "NMS_IOU"), "defect 7: no NMS_IOU"
    assert detector.CONF_THRESHOLD == 0.3, f"Expected CONF_THRESHOLD=0.3, got {detector.CONF_THRESHOLD}"
    assert detector.NMS_IOU == 0.1, f"Expected NMS_IOU=0.1, got {detector.NMS_IOU}"


# ---------------------------------------------------------------------------
# Test: word filtering (spec 5.1 — drop non-alphanumeric)
# ---------------------------------------------------------------------------
def test_parse_ocr_filters_non_alnum():
    """Words with no letters or digits are dropped (icons like |, O, ~)."""
    ocr = {
        "10,50,10,20": "Hello",
        "60,110,10,20": "~",       # icon -> dropped
        "120,170,10,20": "|",      # icon -> dropped
        "180,230,10,20": "OK",
    }
    words = overlay._parse_ocr_results(ocr)
    texts = [w['text'] for w in words]
    assert "Hello" in texts
    assert "OK" in texts
    assert "~" not in texts
    assert "|" not in texts
    assert len(words) == 2, f"Expected 2 alphanumeric words, got {len(words)}: {texts}"


# ---------------------------------------------------------------------------
# Test: inverted test data guard in _make_word
# ---------------------------------------------------------------------------
def test_make_word_rejects_inverted():
    """The _make_word helper asserts x_min < x_max and y_min < y_max.

    This guard catches the 7 inverted calls that were fixed in test_overlay.py.
    """
    sys.path.insert(0, os.path.join(_python_dir))
    # Import _make_word from test_overlay
    import test_overlay
    mod = test_overlay

    # Valid box should work
    w = mod._make_word("Hello", 10, 20, 50, 100)
    assert w['x_min'] == 10 and w['y_min'] == 20

    # Inverted y should raise
    try:
        mod._make_word("Bad", 10, 100, 50, 20)
        assert False, "Should have raised AssertionError for inverted y"
    except AssertionError:
        pass

    # Inverted x should raise
    try:
        mod._make_word("Bad", 50, 20, 10, 100)
        assert False, "Should have raised AssertionError for inverted x"
    except AssertionError:
        pass


# ---------------------------------------------------------------------------
# Test: CJK joining (spec section 6 — empty-string join for CJK)
# ---------------------------------------------------------------------------
def test_cjk_joining():
    """CJK words are joined without spaces; Latin with spaces."""
    cjk_words = [
        {"text": "今日", "x_min": 10, "x_max": 60, "y_min": 10, "y_max": 30,
         "cx": 35, "cy": 20, "width": 50, "height": 20},
        {"text": "は", "x_min": 65, "x_max": 80, "y_min": 10, "y_max": 30,
         "cx": 72.5, "cy": 20, "width": 15, "height": 20},
        {"text": "良い", "x_min": 85, "x_max": 120, "y_min": 10, "y_max": 30,
         "cx": 102.5, "cy": 20, "width": 35, "height": 20},
    ]
    result = blocks._join_words(cjk_words)
    assert " " not in result, f"CJK text should not have spaces: {result!r}"
    assert result == "今日は良い", f"Expected '今日は良い', got {result!r}"

    latin_words = [
        {"text": "Hello", "x_min": 10, "x_max": 50, "y_min": 10, "y_max": 30,
         "cx": 30, "cy": 20, "width": 40, "height": 20},
        {"text": "world", "x_min": 55, "x_max": 95, "y_min": 10, "y_max": 30,
         "cx": 75, "cy": 20, "width": 40, "height": 20},
    ]
    result = blocks._join_words(latin_words)
    assert result == "Hello world", f"Expected 'Hello world', got {result!r}"


# ---------------------------------------------------------------------------
# Test: blocks.py produces correct bbox, text, src_px
# ---------------------------------------------------------------------------
def test_block_record_metadata():
    """BlockRecord has correct bbox, text, src_px."""
    words = [
        {"text": "Hello", "x_min": 10, "x_max": 60, "y_min": 20, "y_max": 50,
         "cx": 35, "cy": 35, "width": 50, "height": 30},
        {"text": "world", "x_min": 65, "x_max": 110, "y_min": 20, "y_max": 50,
         "cx": 87, "cy": 35, "width": 45, "height": 30},
    ]
    recs = blocks.build_blocks(words)
    assert len(recs) == 1
    blk = recs[0]
    assert blk.bbox == (10, 20, 110, 50), f"bbox mismatch: {blk.bbox}"
    assert blk.text == "Hello world", f"text mismatch: {blk.text}"
    assert blk.n_words == 2
    assert blk.n_lines == 1
    # src_px = median(line_h) / 1.25 = 30 / 1.25 = 24, floor 9
    assert blk.src_px == 24.0, f"src_px mismatch: {blk.src_px}"


# ---------------------------------------------------------------------------
# Test: fixture block texts match expected translations
# ---------------------------------------------------------------------------
def test_block_texts_match_fixture_translations():
    """Each of the 4 fixture blocks should start with a key word from
    FIXTURE_TRANSLATIONS (so the translation lookup is deterministic)."""
    shot, clean, words = make_fixture()
    recs = blocks.build_blocks(words)
    assert len(recs) == 4

    for blk in recs:
        # Each block's first word should be a key in FIXTURE_TRANSLATIONS
        first_word = blk.words[0]['text']
        assert first_word in FIXTURE_TRANSLATIONS, (
            f"Block starting with '{first_word}' not in FIXTURE_TRANSLATIONS"
        )
        _assert_box_valid({
            'x_min': blk.bbox[0], 'x_max': blk.bbox[2],
            'y_min': blk.bbox[1], 'y_max': blk.bbox[3]
        })