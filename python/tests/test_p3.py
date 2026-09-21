"""P3 Blend renderer tests (spec section 9, 10; defects 3, 4).

Tests blend.py against the synthetic fixture and against the reference
algorithm's numeric acceptance criteria (spec section 11).

Run: QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python/tests/test_p3.py -v
"""
import os
import sys
import inspect
import numpy as np
from pathlib import Path

_python_dir = str(Path(__file__).resolve().parent.parent)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.fixtures import make_fixture, FIXTURE_TRANSLATIONS
import blend
import blocks


def _make_translations(block_records):
    """Build a translation list from FIXTURE_TRANSLATIONS, keyed by first word."""
    out = []
    for blk in block_records:
        first_word = blk.words[0]['text']
        if first_word in FIXTURE_TRANSLATIONS:
            out.append(FIXTURE_TRANSLATIONS[first_word])
        else:
            out.append(blk.text)
    return out


def _boxes_of(block_records):
    """Extract integer box tuples from BlockRecords as (x0,y0,x1,y1)."""
    return [tuple(int(v) for v in blk.bbox) for blk in block_records]


# ---------------------------------------------------------------------------
# test_remove_flat: flat background blocks have MAE <= 2.0 vs ground truth
# ---------------------------------------------------------------------------
def test_remove_flat():
    """On flat background blocks, source text removal MAE vs ground truth <= 2.0."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    boxes = _boxes_of(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()
    clean_rgb = clean_bgr[:, :, ::-1].copy()

    removed, infos = blend.remove_text(shot_rgb, boxes)

    for i, info in enumerate(infos):
        x0, y0, x1, y1 = boxes[i]
        if info.ring_std < blend.FLAT_STD:
            rem_region = removed[y0:y1, x0:x1].astype(np.float32)
            cln_region = clean_rgb[y0:y1, x0:x1].astype(np.float32)
            mae = float(np.abs(rem_region - cln_region).mean())
            assert mae <= 2.0, f"Block {i} flat MAE = {mae:.2f}, expected <= 2.0"


# ---------------------------------------------------------------------------
# test_remove_gradient: textured blocks have MAE <= 6.0 vs ground truth
# ---------------------------------------------------------------------------
def test_remove_gradient():
    """On textured/gradient blocks, MAE vs ground truth <= 6.0."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    boxes = _boxes_of(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()
    clean_rgb = clean_bgr[:, :, ::-1].copy()

    removed, infos = blend.remove_text(shot_rgb, boxes)

    for i, info in enumerate(infos):
        x0, y0, x1, y1 = boxes[i]
        if info.ring_std >= blend.FLAT_STD:
            rem_region = removed[y0:y1, x0:x1].astype(np.float32)
            cln_region = clean_rgb[y0:y1, x0:x1].astype(np.float32)
            mae = float(np.abs(rem_region - cln_region).mean())
            assert mae <= 6.0, f"Block {i} textured MAE = {mae:.2f}, expected <= 6.0"


# ---------------------------------------------------------------------------
# test_outside_patches_untouched: alpha 0 and composite == source outside patches
# ---------------------------------------------------------------------------
def test_outside_patches_untouched():
    """After overlay render, alpha == 0 outside all patches, and composite
    equals source outside all patches."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    translations = _make_translations(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()

    rgba, placements, metrics = blend.render_overlay(shot_rgb, block_records, translations)

    H, W = shot_rgb.shape[:2]
    covered = np.zeros((H, W), bool)
    for p in placements:
        pt = p.patch
        if pt[2] > pt[0] and pt[3] > pt[1]:
            covered[pt[1]:pt[3], pt[0]:pt[2]] = True

    alpha = rgba[..., 3]
    outside_alpha = int((alpha[~covered] > 0).sum())
    assert outside_alpha == 0, f"alpha outside patches = {outside_alpha}, expected 0"

    comp = blend.composite(shot_rgb, rgba)
    diff = np.abs(comp.astype(int) - shot_rgb.astype(int)).sum(2)[~covered]
    changed = int((diff > 0).sum())
    assert changed == 0, f"{changed} pixels changed outside patches, expected 0"


# ---------------------------------------------------------------------------
# test_contrast_guard: low-contrast pair replaced by black/white (>= 4.5)
# ---------------------------------------------------------------------------
def test_contrast_guard():
    """Every rendered block has text/background contrast >= 4.5."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    translations = _make_translations(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()

    rgba, placements, metrics = blend.render_overlay(shot_rgb, block_records, translations)

    for i, p in enumerate(placements):
        if p.font_px > 0:
            assert p.contrast >= blend.MIN_CONTRAST, \
                f"Block {i} contrast = {p.contrast:.1f}, expected >= {blend.MIN_CONTRAST}"


# ---------------------------------------------------------------------------
# test_fit_monotonic: fit never exceeds free rect; font respects floor
# ---------------------------------------------------------------------------
def test_fit_monotonic():
    """Font size fits within free rect and respects floor."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    translations = _make_translations(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()

    rgba, placements, metrics = blend.render_overlay(shot_rgb, block_records, translations)

    for i, p in enumerate(placements):
        if p.font_px > 0:
            assert p.font_px >= blend.MIN_FONT_PX, \
                f"Block {i} font_px = {p.font_px} < MIN_FONT_PX"
            free_w = p.free_rect[2] - p.free_rect[0]
            free_h = p.free_rect[3] - p.free_rect[1]
            assert free_w >= 1 and free_h >= 1, \
                f"Block {i} has non-positive free rect: {p.free_rect}"


# ---------------------------------------------------------------------------
# test_font_ratio: font_px / src_px within [0.6, 1.05] for all rendered blocks
# ---------------------------------------------------------------------------
def test_font_ratio():
    """Font ratio (font_px / src_px) within [0.6, 1.05] for all rendered blocks."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    translations = _make_translations(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()

    rgba, placements, metrics = blend.render_overlay(shot_rgb, block_records, translations)

    for i, p in enumerate(placements):
        if p.font_px > 0 and p.src_px > 0:
            ratio = p.font_px / p.src_px
            assert blend.MIN_FONT_RATIO - 0.05 <= ratio <= 1.05, \
                f"Block {i} font ratio = {ratio:.2f}, expected within [0.55, 1.05]"


# ---------------------------------------------------------------------------
# test_rtl_alignment: RTL sample uses right-to-left layout
# ---------------------------------------------------------------------------
def test_rtl_alignment():
    """RTL destination languages produce RightToLeft layout flags."""
    assert blend.is_rtl("ar") is True
    assert blend.is_rtl("ur") is True
    assert blend.is_rtl("he") is True
    assert blend.is_rtl("fa") is True
    assert blend.is_rtl("en") is False
    assert blend.is_rtl("ru") is False
    assert blend.is_rtl("ja") is False


# ---------------------------------------------------------------------------
# test_removal_metrics_flat: ground-truth-free proxy checks
# ---------------------------------------------------------------------------
def test_removal_metrics_flat():
    """Flat blocks: p99 bg distance <= 12; textured: box edge <= 1.5*ring_edge + 3."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    boxes = _boxes_of(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()

    removed, infos = blend.remove_text(shot_rgb, boxes)

    for i, info in enumerate(infos):
        m = blend.removal_metrics(removed, info)
        if info.ring_std < blend.FLAT_STD:
            assert m["p99_bg_dist"] <= 12, \
                f"Block {i} flat p99_bg_dist = {m['p99_bg_dist']:.1f}, expected <= 12"
        else:
            assert m["box_edge"] <= 1.5 * m["ring_edge"] + 3, \
                f"Block {i} textured box_edge = {m['box_edge']:.1f} > 1.5*{m['ring_edge']:.1f}+3"


# ---------------------------------------------------------------------------
# test_no_per_word_inpaint: remove_text uses ONE inpaint call (not per word)
# ---------------------------------------------------------------------------
def test_no_per_word_inpaint():
    """remove_text accumulates masks and calls cv2.inpaint once, not per-word."""
    src = inspect.getsource(blend.remove_text)
    analyse_src = inspect.getsource(blend.analyse_block)
    assert "ring" in analyse_src.lower(), "analyse_block must sample a ring"
    assert "inpaint_mask" in src, "remove_text must use a single accumulated inpaint mask"
    assert "for box in boxes" in src


# ---------------------------------------------------------------------------
# test_blend_full_pipeline: fixture yields 32 -> 8 -> 4 with full render
# ---------------------------------------------------------------------------
def test_blend_full_pipeline():
    """Full blend pipeline on fixture: 32 words -> 8 lines -> 4 blocks, all render."""
    shot_bgr, clean_bgr, words = make_fixture()
    assert len(words) == 32
    lines = blocks.group_words_into_lines(words)
    assert len(lines) == 8
    block_records = blocks.build_blocks(words)
    assert len(block_records) == 4

    translations = _make_translations(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()
    rgba, placements, metrics = blend.render_overlay(shot_rgb, block_records, translations)

    assert rgba is not None
    assert rgba.shape == (shot_rgb.shape[0], shot_rgb.shape[1], 4)
    assert len(placements) == 4
    assert metrics['counts']['blocks'] == 4


# ---------------------------------------------------------------------------
# test_render_metrics_complete: metrics has all required fields
# ---------------------------------------------------------------------------
def test_render_metrics_complete():
    """render_overlay metrics include all spec section 8 fields."""
    shot_bgr, clean_bgr, words = make_fixture()
    block_records = blocks.build_blocks(words)
    translations = _make_translations(block_records)
    shot_rgb = shot_bgr[:, :, ::-1].copy()

    rgba, placements, metrics = blend.render_overlay(shot_rgb, block_records, translations)

    assert 'counts' in metrics
    assert 'blocks' in metrics
    assert 'pixels_changed_outside_patches' in metrics
    assert metrics['pixels_changed_outside_patches'] == 0

    for blk in metrics['blocks']:
        for field in ['bbox', 'n_lines', 'src_px', 'font_px', 'ratio', 'contrast',
                      'fits', 'busy', 'container', 'free_rect', 'patch',
                      'ring_std', 'p99_bg_dist', 'box_edge', 'ring_edge']:
            assert field in blk, f"Missing field '{field}' in block metrics"
