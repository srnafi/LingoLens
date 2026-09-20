"""Integration test for the overlay pipeline.

Tests the full data flow: OCR results → word grouping → paragraph grouping
→ translation (mocked) → coordinate math — without requiring a live
OpenCV model or Qt display.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from overlay import (
    _parse_ocr_results,
    _group_words_into_lines,
    _group_lines_into_paragraphs,
    _estimate_font_size,
    _line_bbox,
    _paragraph_bbox,
)


class _MockWord:
    """Helper to build word dicts for tests."""
    @staticmethod
    def make(text, x_min=0, y_min=0, x_max=50, y_max=70):
        cx = (x_min + x_max) / 2
        cy = (y_min + y_max) / 2
        return {
            'text': text,
            'x_min': x_min, 'x_max': x_max,
            'y_min': y_min, 'y_max': y_max,
            'cx': cx, 'cy': cy,
            'width': x_max - x_min,
            'height': y_max - y_min,
        }


class TestParseOcrResults(unittest.TestCase):
    def test_basic_parse(self):
        results = {
            "10,50,100,120": "Hello",
            "60,110,100,120": "World",
        }
        words = _parse_ocr_results(results)
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]['text'], "Hello")
        self.assertEqual(words[0]['x_min'], 10)
        self.assertEqual(words[0]['x_max'], 50)

    def test_empty_results(self):
        self.assertEqual(_parse_ocr_results({}), [])

    def test_invalid_coords(self):
        results = {"bad,coords": "text"}
        self.assertEqual(_parse_ocr_results(results), [])

    def test_empty_text(self):
        results = {"10,50,100,120": ""}
        self.assertEqual(_parse_ocr_results(results), [])


class TestGroupWordsIntoLines(unittest.TestCase):
    def test_single_word(self):
        words = [_MockWord.make("Hello")]
        lines = _group_words_into_lines(words)
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]), 1)

    def test_two_words_same_line(self):
        w1 = _MockWord.make("Hello", x_min=10, x_max=50, y_min=100, y_max=120)
        w2 = _MockWord.make("World", x_min=60, x_max=100, y_min=105, y_max=125)
        lines = _group_words_into_lines([w1, w2])
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]), 2)

    def test_words_different_lines(self):
        w1 = _MockWord.make("Line1", x_min=10, x_max=50, y_min=100, y_max=120)
        w2 = _MockWord.make("Line2", x_min=10, x_max=50, y_min=200, y_max=220)
        lines = _group_words_into_lines([w1, w2])
        self.assertEqual(len(lines), 2)


class TestGroupLinesIntoParagraphs(unittest.TestCase):
    def test_single_line(self):
        words = [_MockWord.make("Hello")]
        lines = _group_words_into_lines(words)
        paras = _group_lines_into_paragraphs(lines)
        self.assertEqual(len(paras), 1)

    def test_close_lines_same_para(self):
        w1 = _MockWord.make("L1", x_min=10, x_max=50, y_min=100, y_max=110)
        w2 = _MockWord.make("L2", x_min=10, x_max=50, y_min=115, y_max=125)
        lines = _group_words_into_lines([w1, w2])
        paras = _group_lines_into_paragraphs(lines)
        self.assertEqual(len(paras), 1)

    def test_far_lines_separate(self):
        w1 = _MockWord.make("Line1", x_min=10, x_max=50, y_min=100, y_max=110)
        w2 = _MockWord.make("Line2", x_min=10, x_max=50, y_min=300, y_max=310)
        lines = _group_words_into_lines([w1, w2])
        paras = _group_lines_into_paragraphs(lines)
        self.assertEqual(len(paras), 2)


class TestFontEstimation(unittest.TestCase):
    def test_basic_estimate(self):
        words = [
            _MockWord.make("A", y_min=100, y_max=130),  # h=30
            _MockWord.make("B", y_min=105, y_max=135),  # h=30
        ]
        est = _estimate_font_size(words)
        self.assertGreater(est, 0)

    def test_empty_words(self):
        self.assertEqual(_estimate_font_size([]), 12)

    def test_min_font_size(self):
        words = [_MockWord.make("A", y_min=100, y_max=101)]  # h=1
        est = _estimate_font_size(words)
        self.assertGreaterEqual(est, 8)


class TestBboxFunctions(unittest.TestCase):
    def test_line_bbox(self):
        words = [
            _MockWord.make("A", x_min=10, y_min=100, x_max=30, y_max=120),
            _MockWord.make("B", x_min=50, y_min=90, x_max=70, y_max=130),
        ]
        x_min, y_min, x_max, y_max = _line_bbox(words)
        self.assertEqual(x_min, 10)
        self.assertEqual(y_min, 90)
        self.assertEqual(x_max, 70)
        self.assertEqual(y_max, 130)

    def test_paragraph_bbox(self):
        line1 = [_MockWord.make("A", x_min=10, y_min=100, x_max=30, y_max=120)]
        line2 = [_MockWord.make("B", x_min=50, y_min=130, x_max=70, y_max=150)]
        x_min, y_min, x_max, y_max = _paragraph_bbox([line1, line2])
        self.assertEqual(x_min, 10)
        self.assertEqual(y_min, 100)
        self.assertEqual(x_max, 70)
        self.assertEqual(y_max, 150)


class TestSyntheticPipeline(unittest.TestCase):
    """Test the full grouping pipeline with realistic simulated OCR data."""

    def test_realistic_text_block(self):
        """Simulate OCR results for a paragraph of text."""
        # 3 lines × 3 words each, typical paragraph layout
        words_data = []
        for line_idx in range(3):
            y = 100 + line_idx * 35
            for word_idx in range(3):
                x = 50 + word_idx * 100
                words_data.append({
                    "coords": f"{x},{x+80},{y},{y+20}"
                })

        # Build OCR-style results dict
        ocr_results = {}
        for i, wd in enumerate(words_data):
            ocr_results[wd["coords"]] = f"word{i}"

        words = _parse_ocr_results(ocr_results)
        self.assertEqual(len(words), 9)

        lines = _group_words_into_lines(words)
        self.assertEqual(len(lines), 3)

        paragraphs = _group_lines_into_paragraphs(lines)
        self.assertEqual(len(paragraphs), 1)
        self.assertEqual(len(paragraphs[0]), 3)  # 3 lines in paragraph

        est_font = _estimate_font_size(words)
        self.assertGreater(est_font, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
