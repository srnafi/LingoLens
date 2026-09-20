"""Debug dump writer — writes debug/<timestamp>/ artifacts when LINGOLENS_DEBUG=1.

Called from the pipeline to capture intermediate state for offline analysis.
All artifacts are written to debug/<stamp>/.
"""
import os
import json
import time
import numpy as np
from pathlib import Path


def _debug_dir():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path("debug") / stamp


def write_dump(capture_img, detections, ocr_results, blocks, translations,
               removed_img, overlay_rgba, composite_img, metrics, timings, env_info):
    """Write all debug artifacts. Returns the dump directory path."""
    d = _debug_dir()
    d.mkdir(parents=True, exist_ok=True)

    import cv2

    # capture.png
    cv2.imwrite(str(d / "capture.png"), capture_img)

    # detections.json
    with open(d / "detections.json", "w") as f:
        json.dump(detections, f, indent=2, default=str)

    # boxes.png — detections drawn on capture
    boxes_img = capture_img.copy()
    for det in detections:
        x0, y0, x1, y1 = det.get("x_min", 0), det.get("y_min", 0), det.get("x_max", 0), det.get("y_max", 0)
        cv2.rectangle(boxes_img, (x0, y0), (x1, y1), (0, 255, 0), 1)
    cv2.imwrite(str(d / "boxes.png"), boxes_img)

    # ocr.json
    with open(d / "ocr.json", "w") as f:
        json.dump(ocr_results, f, indent=2, default=str, ensure_ascii=False)

    # blocks.json
    with open(d / "blocks.json", "w") as f:
        json.dump(blocks, f, indent=2, default=str, ensure_ascii=False)

    # blocks.png — blocks drawn, numbered
    blocks_img = capture_img.copy()
    for i, blk in enumerate(blocks):
        x0, y0, x1, y1 = blk.get("bbox", (0, 0, 0, 0))
        cv2.rectangle(blocks_img, (x0, y0), (x1, y1), (0, 0, 255), 1)
        cv2.putText(blocks_img, str(i), (x0 + 2, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
    cv2.imwrite(str(d / "blocks.png"), blocks_img)

    # translations.json
    with open(d / "translations.json", "w") as f:
        json.dump(translations, f, indent=2, default=str, ensure_ascii=False)

    # removed.png
    cv2.imwrite(str(d / "removed.png"), removed_img)

    # overlay_rgba.png
    if overlay_rgba is not None:
        Path(d / "overlay_rgba.png").write_bytes(
            _rgba_to_png(overlay_rgba)
        )

    # composite.png
    if composite_img is not None:
        cv2.imwrite(str(d / "composite.png"), composite_img)

    # metrics.json
    with open(d / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # timings.json
    with open(d / "timings.json", "w") as f:
        json.dump(timings, f, indent=2, default=str)

    # env.json
    with open(d / "env.json", "w") as f:
        json.dump(env_info, f, indent=2, default=str)

    return str(d)


def _rgba_to_png(rgba_arr):
    """Convert HxWx4 uint8 ndarray to PNG bytes using PIL."""
    from PIL import Image
    import io
    img = Image.fromarray(rgba_arr, "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def is_debug():
    return os.environ.get("LINGOLENS_DEBUG", "") == "1"
