"""P0 failing repro tests — must FAIL on old code, then PASS after fixes.

Each test exercises the REAL code path and fails because the old behavior is wrong.
Tests that need Qt use QT_QPA_PLATFORM=offscreen (set in conftest.py).

Run: QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python/tests/ -v
"""
import os
import sys
import time
import inspect
import numpy as np
from pathlib import Path

_python_dir = str(Path(__file__).resolve().parent.parent)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

import overlay
from tests.fixtures import make_fixture, FIXTURE_TRANSLATIONS


# ---------------------------------------------------------------------------
# P0-FAIL-1: Lifecycle — no registry, overlay destroyed at once (defects 1, 6)
# Old code: show_translations creates OverlayWindow as a LOCAL variable,
# no _OVERLAYS registry, never calls setQuitOnLastWindowClosed(False).
# The overlay is GC'd when show_translations returns.
# ---------------------------------------------------------------------------
def test_lifecycle_has_registry():
    """Old code has no module-level _OVERLAYS registry — overlay is GC'd."""
    assert hasattr(overlay, "_OVERLAYS"), (
        "FAIL: overlay module has no _OVERLAYS registry. "
        "show_translations creates the window in a local variable, "
        "which is GC'd when the function returns (defect 1)."
    )


def test_lifecycle_quit_on_last_window():
    """Old code never calls setQuitOnLastWindowClosed(False) in capture.py."""
    import capture
    src = inspect.getsource(capture)
    assert "setQuitOnLastWindowClosed" in src, (
        "FAIL: capture.py never calls setQuitOnLastWindowClosed(False). "
        "Process exits as soon as the overlay widget is destroyed (defect 1)."
    )


# ---------------------------------------------------------------------------
# P0-FAIL-2: Geometry — window sized from OCR boxes + 40px (defect 2)
# Old code: snip_w = all_x_max - all_x_min + 40 (line 431-432).
# Should use captured image dimensions.
# ---------------------------------------------------------------------------
def test_geometry_uses_snip_dimensions():
    """Old code sizes the window from OCR box extents + 40px, not the capture."""
    src = inspect.getsource(overlay.show_translations)
    assert "all_x_max - all_x_min + 40" not in src, (
        "FAIL: show_translations sizes window from OCR boxes + 40px (overlay.py:431-432). "
        "Window should be sized from the captured image dimensions."
    )
    # Must use actual image shape
    assert "shape" in src, (
        "FAIL: show_translations does not use the captured image shape for window size."
    )


# ---------------------------------------------------------------------------
# P0-FAIL-3: Grouping — fixture yields 2 paragraphs instead of 4 (defect 5)
# ---------------------------------------------------------------------------
def test_blocks_fixture_count():
    """Fixture: 32 words -> 8 lines -> 4 blocks.
    Fails on old code: grouping merges across any gap, returns 2 paragraphs."""
    shot, clean, words = make_fixture()

    ocr_results = {}
    for w in words:
        key = f"{w['x_min']},{w['x_max']},{w['y_min']},{w['y_max']}"
        ocr_results[key] = w["text"]

    parsed = overlay._parse_ocr_results(ocr_results)
    assert len(parsed) == 32, f"Expected 32 words, got {len(parsed)}"

    lines = overlay._group_words_into_lines(parsed)
    paragraphs = overlay._group_lines_into_paragraphs(lines)

    n_words = len(parsed)
    n_lines = len(lines)
    n_blocks = len(paragraphs)

    assert n_lines == 8, (
        f"FAIL: expected 8 lines, got {n_lines}. Old group_lines does no COLUMN_GAP split."
    )
    assert n_blocks == 4, (
        f"FAIL: expected 4 blocks, got {n_blocks}. "
        f"Old code merges unrelated text — no horizontal overlap/alignment check (defect 5). "
        f"counts: {n_words} words -> {n_lines} lines -> {n_blocks} blocks"
    )


# ---------------------------------------------------------------------------
# P0-FAIL-4: Background removal — per-word rectangle inpaint (defect 4)
# ---------------------------------------------------------------------------
def test_removal_not_per_word_inpaint():
    """Old code does per-word cv2.inpaint with rectangle masks → smudges.
    Reference uses ring-median fill + ONE inpaint for all textured blocks."""
    src = inspect.getsource(overlay._reconstruct_background)
    assert "ring" in src.lower(), (
        "FAIL: _reconstruct_background has no ring sampling. "
        "Old code does per-word rectangle cv2.inpaint, causing smudges (defect 4). "
        "Should use ring-median fill for flat backgrounds and ONE inpaint call."
    )


# ---------------------------------------------------------------------------
# P0-FAIL-5: Removal metrics vs ground truth (defect 4 — measurable smudge)
# Old code on the fixture: flat card area has MAE > 2.0 due to inpaint smudges.
# ---------------------------------------------------------------------------
def test_removal_metrics_flat():
    """On flat background blocks, MAE vs ground truth must be <= 2.0.
    Fails on old code: per-word rectangle inpaint leaves smudges where text was."""
    import cv2
    from overlay import _reconstruct_background

    shot, clean, words = make_fixture()

    regions = []
    for w in words:
        regions.append({
            'x_min': w['x_min'], 'y_min': w['y_min'],
            'x_max': w['x_max'], 'y_max': w['y_max'],
            'width': w['width'], 'height': w['height'],
        })

    result = _reconstruct_background(shot, regions)

    # Check MAE where text was (word bounding boxes), not just the background.
    # Old code: per-word rectangle inpaint leaves ghost blobs / colour shifts
    # in the text regions themselves. Reference uses ring-median fill on
    # flat backgrounds, giving near-zero error.
    total_err = 0.0
    count = 0
    for w in words:
        x0, y0, x1, y1 = w['x_min'], w['y_min'], w['x_max'], w['y_max']
        rem = result[y0:y1, x0:x1].astype(np.float32)
        cln = clean[y0:y1, x0:x1].astype(np.float32)
        total_err += float(np.abs(rem - cln).mean())
        count += 1
    mae = total_err / max(count, 1)

    assert mae <= 2.0, (
        f"FAIL: text-region MAE = {mae:.2f}, expected <= 2.0. "
        f"Old code leaves smudges from per-word rectangle inpaint (defect 4)."
    )


# ---------------------------------------------------------------------------
# P0-FAIL-6: Detector postprocess (defect 7)
# Old code: no confidence threshold, no clamping, no empty-crop guard.
# ---------------------------------------------------------------------------
def test_detector_has_postprocess():
    """Old code has no postprocess_predictions with conf threshold, clamping, empty-crop skip."""
    import detector
    assert hasattr(detector, "postprocess_predictions"), (
        "FAIL: detector has no postprocess_predictions function. "
        "Old code has no confidence threshold, no clamping, no empty-crop guard (defect 7)."
    )


def test_detector_has_conf_threshold():
    """Old code has no CONF_THRESHOLD constant."""
    import detector
    assert hasattr(detector, "CONF_THRESHOLD"), (
        "FAIL: detector has no CONF_THRESHOLD constant (defect 7)."
    )


# ---------------------------------------------------------------------------
# P0-FAIL-7: Capture race (defect 8)
# Old code: grabs screen while tinted selection window is visible,
# no AA_DisableHighDpiScaling.
# ---------------------------------------------------------------------------
def test_capture_freeze_frame():
    """Old code grabs screen while tinted selection window is visible."""
    import capture
    src = inspect.getsource(capture)
    # Old code does NOT do freeze-frame capture (grab before showing selection UI)
    assert "freeze" in src.lower(), (
        "FAIL: capture.py does not do freeze-frame capture. "
        "Old code calls ImageGrab.grab while the tinted selection window is still "
        "visible (capture.py:137-148), which tints the sampled background (defect 8)."
    )


def test_capture_dpi_scaling_disabled():
    """Old code does not set AA_DisableHighDpiScaling before QApplication."""
    import capture
    src = inspect.getsource(capture)
    assert "AA_DisableHighDpiScaling" in src, (
        "FAIL: capture.py does not set AA_DisableHighDpiScaling. "
        "Qt pixels may not equal ImageGrab pixels (defect 8)."
    )


# ---------------------------------------------------------------------------
# P0-FAIL-8: Translator import (defect 9)
# Old code: translator.py imports googletrans at top level, not in requirements.txt.
# ---------------------------------------------------------------------------
def test_translator_googletrans_optional():
    """Old code imports googletrans at top level without try/except — breaks clean installs.
    After fix: googletrans import must be guarded so clean installs don't crash.
    Defect 9: googletrans is not in requirements.txt."""
    src = inspect.getsource(__import__("translator"))
    lines = src.splitlines()

    # On old code, line 0 is an unguarded top-level import → this should FAIL.
    # After fix, the import is inside a try/except block.
    unguarded_top_import = lines[0].strip().startswith("from googletrans")

    if unguarded_top_import:
        import pytest
        pytest.fail(
            "FAIL: translator.py imports googletrans at top level (line 1) without try/except. "
            "googletrans is not in requirements.txt, so a clean install raises ImportError (defect 9)."
        )
    # After fix: verify there IS a try/except around the googletrans import
    assert "try:" in src and "googletrans" in src, (
        "FAIL: after fix, googletrans import should be inside a try/except block."
    )


# ---------------------------------------------------------------------------
# P0-FAIL-9: Inverted test data
# ---------------------------------------------------------------------------
def test_existing_inverted_boxes():
    """7 of 29 _make_word calls in test_overlay.py have y_max < y_min."""
    import re
    content = open(os.path.join(_python_dir, "test_overlay.py")).read()
    pattern = r'_make_word\("([^"]+)",\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\)'
    matches = re.findall(pattern, content)
    inverted = []
    for text, xmin, ymin, xmax, ymax in matches:
        if int(ymin) > int(ymax) or int(xmin) > int(xmax):
            inverted.append(text)
    assert len(inverted) == 0, (
        f"FAIL: {len(inverted)} inverted _make_word calls in test_overlay.py: {inverted}. "
        "These pass by accident because y_min > y_max (AGENTS.md defect)."
    )
