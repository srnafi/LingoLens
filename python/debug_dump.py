"""Debug dump writer — writes debug/<timestamp>/ artifacts when LINGOLENS_DEBUG=1.

Called from the pipeline to capture intermediate state for offline analysis.
All artifacts are written to debug/<stamp>/.
"""
import os
import json
import time
import cv2
import numpy as np
from pathlib import Path
from PIL import Image


_this_dir = Path(__file__).parent.parent  # project root (F:/LingoLens)

def _debug_dir():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return _this_dir / "debug" / stamp


def is_debug():
    """Return True when LINGOLENS_DEBUG is set in the environment."""
    return os.environ.get("LINGOLENS_DEBUG", "") == "1"


class DebugDump:
    """Context object that writes debug artifacts stage-by-stage.

    Created once per pipeline run when LINGOLENS_DEBUG=1. Each stage() call
    records a timing checkpoint; the writer methods save the corresponding
    artifact into the dump directory.
    """

    def __init__(self):
        self.dir = _debug_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._stages = {}
        self._t0 = time.time()

    def stage(self, name):
        """Record a timing checkpoint for a pipeline stage."""
        self._stages[name] = time.time() - self._t0

    def write_capture(self, capture_bgr):
        """Write the captured image as capture.png."""
        cv2.imwrite(str(self.dir / "capture.png"), capture_bgr)

    def write_detections(self, detections):
        """Write detections.json (boxes + conf)."""
        with open(self.dir / "detections.json", "w", encoding="utf-8") as f:
            json.dump(detections, f, indent=2, default=str, ensure_ascii=False)

    def write_ocr(self, ocr_results):
        """Write ocr.json (exact Flask response)."""
        with open(self.dir / "ocr.json", "w", encoding="utf-8") as f:
            json.dump(ocr_results, f, indent=2, default=str, ensure_ascii=False)

    def write_boxes_png(self, capture_bgr, boxes):
        """Write boxes.png (detections drawn on the capture)."""
        img = capture_bgr.copy()
        for box in boxes:
            if len(box) == 4:
                x0, y0, x1, y1 = box
                cv2.rectangle(img, (x0, y0), (x1, y1), (0, 255, 0), 1)
        cv2.imwrite(str(self.dir / "boxes.png"), img)

    def write_blocks(self, paragraphs, words):
        """Write blocks.json (grouped blocks)."""
        blocks = []
        for i, para in enumerate(paragraphs):
            all_w = [w for line in para for w in line]
            if not all_w:
                continue
            text = ' '.join(w['text'] for w in all_w)
            x1 = min(w['x_min'] for w in all_w)
            y1 = min(w['y_min'] for w in all_w)
            x2 = max(w['x_max'] for w in all_w)
            y2 = max(w['y_max'] for w in all_w)
            blocks.append({
                "index": i,
                "text": text,
                "bbox": [x1, y1, x2, y2],
                "n_lines": len(para),
                "n_words": len(all_w),
            })
        with open(self.dir / "blocks.json", "w", encoding="utf-8") as f:
            json.dump(blocks, f, indent=2, default=str, ensure_ascii=False)

    def write_blocks_png(self, capture_bgr, paragraphs, words):
        """Write blocks.png (blocks drawn, numbered)."""
        img = capture_bgr.copy()
        for i, para in enumerate(paragraphs):
            all_w = [w for line in para for w in line]
            if not all_w:
                continue
            x1 = min(w['x_min'] for w in all_w)
            y1 = min(w['y_min'] for w in all_w)
            x2 = max(w['x_max'] for w in all_w)
            y2 = max(w['y_max'] for w in all_w)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 1)
            cv2.putText(img, str(i), (x1 + 2, y2 - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
        cv2.imwrite(str(self.dir / "blocks.png"), img)

    def write_translations(self, translations):
        """Write translations.json (block index -> translated text)."""
        with open(self.dir / "translations.json", "w", encoding="utf-8") as f:
            json.dump(translations, f, indent=2, default=str, ensure_ascii=False)

    def write_removed(self, removed_img):
        """Write removed.png (capture with source text removed)."""
        cv2.imwrite(str(self.dir / "removed.png"), removed_img)

    def write_overlay(self, rgba_arr):
        """Write overlay_rgba.png (the QImage as RGBA)."""
        Image.fromarray(rgba_arr, "RGBA").save(str(self.dir / "overlay_rgba.png"), format="PNG")

    def write_composite(self, capture_bgr, rgba_img):
        """Write composite.png (capture with overlay alpha-blended on top)."""
        h = min(capture_bgr.shape[0], rgba_img.shape[0])
        w = min(capture_bgr.shape[1], rgba_img.shape[1])
        cap_rgb = cv2.cvtColor(capture_bgr[:h, :w], cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        ov_rgba = rgba_img[:h, :w].astype(np.float32) / 255.0
        alpha = ov_rgba[:, :, 3:4]
        comp = cap_rgb * (1 - alpha) + ov_rgba[:, :, :3] * alpha
        comp = np.clip(comp, 0, 255).astype(np.uint8)
        cv2.imwrite(str(self.dir / "composite.png"), cv2.cvtColor(comp, cv2.COLOR_RGB2BGR))

    def write_metrics(self, metrics):
        """Write metrics.json, merging in stage timings."""
        metrics = dict(metrics)
        metrics["timings_stages"] = self._stages
        with open(self.dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, default=str)

    def write_env(self, screen_size=None, device_pixel_ratio=None):
        """Write env.json (python, Qt, OpenCV, screen info)."""
        import platform
        try:
            import PyQt5.QtCore as qtc
            qt_version = qtc.QT_VERSION_STR
        except Exception:
            qt_version = None
        env = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": cv2.__version__,
            "pyqt5": qt_version,
            "screen_size": screen_size,
            "device_pixel_ratio": device_pixel_ratio,
            "lingolens_debug": os.environ.get("LINGOLENS_DEBUG", ""),
        }
        with open(self.dir / "env.json", "w", encoding="utf-8") as f:
            json.dump(env, f, indent=2, default=str)

    def write_timings(self, timings):
        """Write timings.json (optional extra timing info)."""
        with open(self.dir / "timings.json", "w", encoding="utf-8") as f:
            json.dump(timings, f, indent=2, default=str)

    def finish(self):
        """Mark the dump as complete."""
        pass


def write_dump(capture_img, detections, ocr_results, blocks, translations,
               removed_img, overlay_rgba, composite_img, metrics, timings, env_info):
    """Write all debug artifacts (legacy single-call form). Returns the dump dir."""
    d = _debug_dir()
    d.mkdir(parents=True, exist_ok=True)

    # capture.png
    cv2.imwrite(str(d / "capture.png"), capture_img)

    # detections.json
    with open(d / "detections.json", "w", encoding="utf-8") as f:
        json.dump(detections, f, indent=2, default=str, ensure_ascii=False)

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
        Image.fromarray(overlay_rgba, "RGBA").save(str(d / "overlay_rgba.png"), format="PNG")

    # composite.png
    if composite_img is not None:
        cv2.imwrite(str(d / "composite.png"), composite_img)

    # metrics.json
    with open(d / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)

    # timings.json
    with open(d / "timings.json", "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2, default=str)

    # env.json
    with open(d / "env.json", "w", encoding="utf-8") as f:
        json.dump(env_info, f, indent=2, default=str)

    return str(d)
