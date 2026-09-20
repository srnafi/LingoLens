"""Unit tests for the overlay pipeline.

Tests the grouping, translation, and coordinate logic WITHOUT requiring
a real screenshot or OCR. Uses synthetic OCR data to verify correctness.

Run: .venv/Scripts/python.exe -m pytest python/test_overlay.py -v
 Or: .venv/Scripts/python.exe python/test_overlay.py
"""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup path
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from overlay import (
    _parse_ocr_results,
    _group_words_into_lines,
    _group_lines_into_paragraphs,
    _estimate_font_size,
    _line_bbox,
    _paragraph_bbox,
)


def _make_word(text, x_min, y_min, x_max, y_max):
    """Helper: create a word dict like OCR would produce."""
    return {
        'text': text,
        'x_min': x_min, 'x_max': x_max,
        'y_min': y_min, 'y_max': y_max,
        'cx': (x_min + x_max) / 2,
        'cy': (y_min + y_max) / 2,
        'width': x_max - x_min,
        'height': y_max - y_min,
    }


def _para_to_text(para):
    """Convert paragraph (list of lines) to single text string."""
    return ' '.join(w['text'] for line in para for w in line)


def test_parse_ocr_results():
    """Test parsing OCR coordinate strings into word dicts."""
    ocr = {
        "10,50,5,20": "Hello",
        "60,120,5,20": "world",
        "10,50,30,45": "This",
    }
    words = _parse_ocr_results(ocr)
    assert len(words) == 3
    assert words[0]['text'] == 'Hello'
    assert words[0]['x_min'] == 10
    assert words[0]['cx'] == 30.0
    assert words[0]['width'] == 40
    print("test_parse_ocr_results: PASS")


def test_group_words_into_lines_simple():
    """Two words on same line should group together."""
    w1 = _make_word("Hello", 10, 100, 50, 120)   # y center ~110
    w2 = _make_word("world", 60, 102, 100, 122)  # y center ~112, height 20

    lines = _group_words_into_lines([w1, w2])
    assert len(lines) == 1
    assert len(lines[0]) == 2
    # Should be sorted left-to-right
    assert lines[0][0]['text'] == 'Hello'
    assert lines[0][1]['text'] == 'world'
    print("test_group_words_into_lines_simple: PASS")


def test_group_words_into_lines_separate():
    """Words on different Y lines should NOT group together."""
    w1 = _make_word("Line1", 10, 100, 50, 20)   # y center ~15
    w2 = _make_word("Line2", 10, 200, 50, 25)   # y center ~212.5

    lines = _group_words_into_lines([w1, w2])
    assert len(lines) == 2
    print("test_group_words_into_lines_separate: PASS")


def test_group_lines_into_paragraphs():
    """Lines close together form a paragraph; far apart form separate."""
    line1 = [_make_word("Sentence", 10, 100, 100, 120),
             _make_word("one", 110, 100, 140, 120)]
    line2 = [_make_word("Sentence", 10, 125, 100, 145),
             _make_word("two", 110, 125, 140, 145)]
    line3 = [_make_word("Button", 100, 500, 150, 530)]  # far below

    paragraphs = _group_lines_into_paragraphs([line1, line2, line3])
    assert len(paragraphs) == 2  # line1+line2 are close, line3 is far
    assert len(paragraphs[0]) == 2  # paragraph 1 has 2 lines
    assert len(paragraphs[1]) == 1  # paragraph 2 has 1 line
    print("test_group_lines_into_paragraphs: PASS")


def test_paragraph_text_flatten():
    """Test that paragraph text is extracted correctly."""
    line1 = [_make_word("Hello", 10, 100, 50, 20),
             _make_word("world", 60, 100, 100, 20)]
    line2 = [_make_word("This", 10, 30, 50, 15),
             _make_word("is", 60, 30, 90, 15),
             _make_word("test", 100, 30, 140, 15)]

    text = _para_to_text([line1, line2])
    assert 'Hello' in text
    assert 'world' in text
    assert 'This' in text
    assert 'test' in text
    print("test_paragraph_text_flatten: PASS")


def test_estimate_font_size():
    """Font size should be estimated from bounding box heights."""
    words = [_make_word("A", 0, 0, 50, 50),
             _make_word("B", 0, 0, 50, 50)]
    est = _estimate_font_size(words)
    assert est == 37  # int(50 * 0.75)
    assert est >= 8
    print("test_estimate_font_size: PASS")


def test_estimate_font_size_empty():
    """Empty words list should return default font size."""
    est = _estimate_font_size([])
    assert est == 12
    print("test_estimate_font_size_empty: PASS")


def test_line_bbox():
    """Line bounding box should cover all words."""
    line = [_make_word("A", 10, 20, 50, 40),
            _make_word("B", 60, 10, 100, 50)]
    bbox = _line_bbox(line)
    assert bbox == (10, 10, 100, 50)
    print("test_line_bbox: PASS")


def test_paragraph_bbox():
    """Paragraph bounding box should cover all lines."""
    line1 = [_make_word("A", 10, 20, 50, 40)]
    line2 = [_make_word("B", 60, 100, 100, 120)]
    bbox = _paragraph_bbox([line1, line2])
    assert bbox == (10, 20, 100, 120)
    print("test_paragraph_bbox: PASS")


def test_ui_button_grouping():
    """UI buttons: 'Cancel' and 'OK' on far-apart X but same Y should
    group into same line but separate paragraphs if vertically separated."""
    # Two buttons side by side on same line
    words = [
        _make_word("Cancel", 100, 10, 200, 30),
        _make_word("OK", 300, 10, 350, 30),
    ]
    lines = _group_words_into_lines(words)
    paragraphs = _group_lines_into_paragraphs(lines)
    assert len(lines) == 1  # Same line
    assert len(paragraphs) == 1  # Same paragraph (one line)
    print("test_ui_button_grouping: PASS")


def test_multi_line_sentence():
    """A sentence spanning multiple lines should stay as one paragraph."""
    words = [
        _make_word("This", 10, 100, 50, 125),
        _make_word("is", 60, 100, 90, 125),
        _make_word("text", 100, 100, 150, 125),
        _make_word("continuing", 10, 135, 90, 160),
        _make_word("on", 100, 135, 130, 160),
        _make_word("another", 140, 135, 210, 160),
        _make_word("line", 220, 135, 270, 160),
    ]
    lines = _group_words_into_lines(words)
    paragraphs = _group_lines_into_paragraphs(lines)
    assert len(paragraphs) == 1  # Multi-line sentence is one paragraph
    print("test_multi_line_sentence: PASS")


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 50)
    print("Running overlay pipeline unit tests")
    print("=" * 50)

    tests = [
        test_parse_ocr_results,
        test_group_words_into_lines_simple,
        test_group_words_into_lines_separate,
        test_group_lines_into_paragraphs,
        test_paragraph_text_flatten,
        test_estimate_font_size,
        test_estimate_font_size_empty,
        test_line_bbox,
        test_paragraph_bbox,
        test_ui_button_grouping,
        test_multi_line_sentence,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"{test.__name__}: FAIL - {e}")
            failed += 1
        except Exception as e:
            print(f"{test.__name__}: ERROR - {e}")
            failed += 1

    print()
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 50)
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
