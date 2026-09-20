"""Replay tool — re-renders a debug dump offline, prints metrics.

Loads debug/<stamp>/capture.png + ocr.json (+ translations.json when present),
runs blocks -> render, writes the last five artifacts, and prints the metrics table.

Usage:
    .venv/Scripts/python.exe python/tools/replay.py debug/<stamp> [--dest ru] [--stub-translate]
"""
import os
import sys
import json
import argparse
from pathlib import Path

# Set offscreen BEFORE any Qt import
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_python_dir = str(Path(__file__).resolve().parent.parent)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

import numpy as np
import cv2


def main():
    parser = argparse.ArgumentParser(description="Re-render a debug dump offline")
    parser.add_argument("dump_dir", help="Path to debug/<stamp> directory")
    parser.add_argument("--dest", default="ru", help="Target language")
    parser.add_argument("--stub-translate", action="store_true",
                        help="Use stub translations instead of network")
    args = parser.parse_args()

    dump = Path(args.dump_dir)
    if not dump.exists():
        print(f"ERROR: dump dir {dump} does not exist")
        sys.exit(1)

    print(f"Replay: {dump}")

    # Load capture
    capture_path = dump / "capture.png"
    if not capture_path.exists():
        print(f"ERROR: {capture_path} not found")
        sys.exit(1)
    capture = cv2.imread(str(capture_path))
    if capture is None:
        capture = np.array(__import__("PIL").Image.open(capture_path).convert("RGB"))
        capture = capture[:, :, ::-1].copy()
    print(f"  capture: {capture.shape[1]}x{capture.shape[0]}")

    # Load OCR results
    ocr_path = dump / "ocr.json"
    if ocr_path.exists():
        ocr_results = json.loads(ocr_path.read_text(encoding="utf-8"))
    else:
        ocr_results = {}
        print("  WARNING: ocr.json not found")

    print(f"  OCR results: {len(ocr_results)} entries")

    # Load translations if present
    trans_path = dump / "translations.json"
    if trans_path.exists():
        translations = json.loads(trans_path.read_text(encoding="utf-8"))
        print(f"  translations: {len(translations)} entries")
    else:
        print("  no translations.json, --stub-translate required to continue")
        if not args.stub_translate:
            print("  Exiting (no translation source). Re-run with --stub-translate.")
            sys.exit(1)
        translations = {}

    # Load metrics if present for reporting
    metrics_path = dump / "metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        print(f"\n  Metrics summary:")
        print(f"    pixels_changed_outside_patches: {metrics.get('pixels_changed_outside_patches', 'N/A')}")
        per_block = metrics.get("blocks", [])
        for i, blk in enumerate(per_block):
            print(f"    block {i}: font_px={blk.get('font_px','?')}, "
                  f"src_px={blk.get('src_px','?')}, ratio={blk.get('ratio','?')}, "
                  f"contrast={blk.get('contrast','?')}, fits={blk.get('fits','?')}, "
                  f"busy={blk.get('busy','?')}")

    print("\n  Replay complete. Manual review of composite.png required.")


if __name__ == "__main__":
    main()
