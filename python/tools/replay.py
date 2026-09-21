"""Replay tool -- re-renders a debug dump offline, prints metrics.

Loads debug/<stamp>/capture.png + ocr.json (+ translations.json when present),
runs blocks -> render via blend.py, writes the last five artifacts, and prints
the metrics table. This is how you iterate without the desktop.

Usage:
    .venv/Scripts/python.exe python/tools/replay.py debug/<stamp> [--dest ru] [--stub-translate]
"""
import os
import sys
import json
import argparse
from pathlib import Path
import numpy as np
import cv2

# Set offscreen BEFORE any Qt import
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_python_dir = str(Path(__file__).resolve().parent.parent)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

from PIL import Image
import blocks
import blend


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
    capture_bgr = cv2.imread(str(capture_path))
    if capture_bgr is None:
        capture_bgr = np.array(Image.open(capture_path).convert("RGB"))
        capture_bgr = capture_bgr[:, :, ::-1].copy()
    print(f"  capture: {capture_bgr.shape[1]}x{capture_bgr.shape[0]}")

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
        translations_json = json.loads(trans_path.read_text(encoding="utf-8"))
        print(f"  translations: {len(translations_json)} entries")
        # translations.json keys may be string indices; normalize to int
        translations = {int(k) if k.isdigit() else k: v for k, v in translations_json.items()}
    else:
        print("  no translations.json, --stub-translate required to continue")
        if not args.stub_translate:
            print("  Exiting (no translation source). Re-run with --stub-translate.")
            sys.exit(1)
        translations = {}

    # Load blocks.json if present (for block text)
    blocks_path = dump / "blocks.json"
    if blocks_path.exists():
        blocks_data = json.loads(blocks_path.read_text(encoding="utf-8"))
    else:
        blocks_data = []

    # Parse OCR into word dicts via overlay's parser
    sys.path.insert(0, _python_dir)
    import overlay
    words = overlay._parse_ocr_results(ocr_results)
    print(f"  parsed words: {len(words)}")

    # Group into blocks
    block_records = blocks.build_blocks(words)
    n_words = len(words)
    n_lines = sum(len(blk.lines) for blk in block_records)
    n_blocks = len(block_records)
    print(f"  grouped: {n_words} words -> {n_lines} lines -> {n_blocks} blocks")

    # Build translation list (index by block position)
    translation_list = []
    for i in range(n_blocks):
        if str(i) in translations or i in translations:
            t = translations.get(str(i), translations.get(i, ""))
        elif i < len(blocks_data) and 'text' in blocks_data[i]:
            t = blocks_data[i]['text']  # stub: use source text
        else:
            t = block_records[i].text if i < len(block_records) else ""
        translation_list.append(t)

    # Render via blend.py
    capture_rgb = capture_bgr[:, :, ::-1].copy()
    rgba, placements, metrics = blend.render_overlay(
        capture_rgb, block_records, translation_list, dest_lang=args.dest)

    # Write last five artifacts
    Image.fromarray(rgba, "RGBA").save(str(dump / "overlay_rgba.png"))
    comp = blend.composite(capture_rgb, rgba)
    cv2.imwrite(str(dump / "composite.png"), comp[:, :, ::-1])

    removed, _ = blend.remove_text(capture_rgb,
                                    [tuple(int(v) for v in blk.bbox) for blk in block_records])
    cv2.imwrite(str(dump / "removed.png"), removed[:, :, ::-1])

    # Update metrics.json with blend's computed metrics
    # Preserve existing fields, add blend metrics
    existing_metrics = {}
    metrics_path = dump / "metrics.json"
    if metrics_path.exists():
        existing_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    existing_metrics.update(metrics)
    existing_metrics["timings_stages"] = existing_metrics.get("timings_stages", {})
    existing_metrics["timings"] = existing_metrics.get("timings", {})
    metrics_path.write_text(json.dumps(existing_metrics, indent=2, default=str),
                            encoding="utf-8")

    # Print metrics table
    print(f"\n  Metrics table:")
    print(f"    word->line->block counts: ({n_words}, {n_lines}, {n_blocks})")
    print(f"    pixels_changed_outside_patches: {metrics['pixels_changed_outside_patches']}")

    for i, p in enumerate(placements):
        ratio = p.font_px / p.src_px if p.src_px > 0 else 0
        status = "PASS" if p.fits else "FLOOR"
        print(f"    block {i}: font={p.font_px}px src={p.src_px:.1f}px ratio={ratio:.2f} "
              f"contrast={p.contrast:.1f} fits={p.fits} busy={p.busy} "
              f"p99_bg={p.p99_bg_dist:.1f} {status}")

    print(f"\n  Artifacts written:")
    for f in ["removed.png", "overlay_rgba.png", "composite.png", "metrics.json"]:
        p = dump / f
        if p.exists():
            print(f"    {f} ({p.stat().st_size} bytes)")
    print(f"\n  Replay complete. Manual review of composite.png required.")


if __name__ == "__main__":
    main()
