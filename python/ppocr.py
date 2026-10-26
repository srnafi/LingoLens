"""PP-OCRv6 text detection + recognition on OpenVINO.

This is the second, optional text-recognition engine the Control Center can
switch to (settings key ``ocr_engine``). The current engine
(``detector.py`` OpenVINO boxes + ``ocr_server.py`` EasyOCR) is untouched and
stays the default.

Method
------
Two PP-OCRv6 ONNX graphs, the standard PaddleOCR pipeline:

  * detector   PP-OCRv6_det_tiny (DBNet)    models/ppocr/shared/det.onnx
  * recogniser PP-OCRv6_small_rec (CTC)     models/ppocr/cjk/rec.onnx
  * dictionary 18,708 characters            models/ppocr/cjk/dict.txt
  * classifier shared/cls.onnx ships but is unused: the reference
    implementation sets ``DoAngle = false``, so text-line rotation is not
    corrected.

The model files and the preprocessing/post-processing numbers come from
OverTranslate (MIT, https://github.com/Hon-Lu/OverTranslate), whose OCR layer
runs these same PaddleOCR releases (Apache-2.0) through RapidOcrNet. Its manga
model is a different, CC BY-NC-SA 4.0 model and is not used here.

Runtime
-------
The reference runs the graphs with onnxruntime. LingoLens already ships
OpenVINO, which reads these .onnx files directly, so no new runtime dependency
is added; the graphs, weights, thresholds and normalisation are the same
numbers:

  * detector input: longest side <= 2048, pad 8 px, align to 32, normalise with
    (px - 127.5) / 127.5
  * DB post-process: thresh 0.4, box score 0.2, unclip 1.4
  * recogniser: height 48, width capped at 320, (px/255 - 0.5) / 0.5
  * recognition confidence floor: 0.6
  * dictionary order: ["blank"] + dict.txt + [" "]

Language coverage is limited to what the shipped models read: Latin (the
EasyOCR source option 1 bundle), Chinese (2) and Japanese (3). Korean (6) needs
the separate ``korean/rec.onnx``, which is not downloaded, so KO falls back.
Russian (4) and Bengali (5) have no model here and fall back to the current
engine. See ``supports_option``.

The public surface is plain Python so it runs headless:

    engine = get_engine()
    lines = engine.recognize_image(bgr)      # [{"text", "conf", "x_min", ...}]
    mapping = engine.run(path_or_bgr)        # {"x_min,x_max,y_min,y_max": text}
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_this_dir = Path(__file__).parent
MODELS_DIR = _this_dir / "models" / "ppocr"
DET_MODEL = MODELS_DIR / "shared" / "det.onnx"
REC_MODEL = MODELS_DIR / "cjk" / "rec.onnx"
REC_DICT = MODELS_DIR / "cjk" / "dict.txt"

ENGINE_ID = "ppocr"
ENGINE_LABEL = "PP-OCRv6"

# --- PP-OCRv6 constants (do not tune without the same measurement) -----
DET_MAX_SIDE = 2048          # ScreenshotDetectSize
DET_PAD = 8                  # DetectorPadding
DET_ALIGN = 32               # DetectorAlignment
DET_THRESH = 0.4             # DetectorThresholds.BoxThresh
DET_BOX_THRESH = 0.2         # DetectorThresholds.BoxScoreThresh
DET_UNCLIP = 1.4             # DetectorThresholds.UnClipRatio
DET_NORM = 127.5             # HalfNormalization (mean == std == 127.5)

REC_HEIGHT = 48
REC_MAX_WIDTH = 320
REC_NORM = 0.5
REC_MIN_CONF = 0.6           # MinRecognitionConfidence

MIN_BOX_PX = 3

# EasyOCR source option -> the PP-OCR model that can read it.
#   option 1 = Latin bundle (es fr it pt vi de en), 2 = Chinese, 3 = Japanese,
#   4 = Russian, 5 = Bengali, 6 = Korean. Mirrors ocr_server.LANGUAGE_MAP.
SUPPORTED_OPTIONS = {1, 2, 3}
# Korean would need models/ppocr/korean/rec.onnx (not shipped here);
# flip this on once that file exists.
KOREAN_OPTION = 6
_KOREAN_MODEL = MODELS_DIR / "korean" / "rec.onnx"
_KOREAN_DICT = MODELS_DIR / "korean" / "dict.txt"


class OcrUnavailable(RuntimeError):
    """The optional models are not installed."""


def models_present() -> bool:
    """True when the detector + CJK recogniser files are all on disk."""
    return DET_MODEL.is_file() and REC_MODEL.is_file() and REC_DICT.is_file()


def supports_option(option) -> bool:
    """Whether this engine can read the OCR language bundle ``option``."""
    try:
        option = int(option)
    except (TypeError, ValueError):
        return False
    if option in SUPPORTED_OPTIONS:
        return True
    if option == KOREAN_OPTION:
        return _KOREAN_MODEL.is_file() and _KOREAN_DICT.is_file()
    return False


# ---------------------------------------------------------------------------
# Pure geometry / decoding helpers (unit-tested headless, no model needed)
# ---------------------------------------------------------------------------

def order_quad(points):
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if pts.shape[0] != 4:
        raise ValueError("quad needs 4 points")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def det_canvas_size(width, height, pad=DET_PAD, align=DET_ALIGN):
    """Detector input size for an image of ``width`` x ``height``.

    The reference implementation's ``AlignedLength`` grows the bitmap until ``length + 2*pad``
    is a multiple of 32; the library then adds the ``pad`` border, so the graph
    itself sees a canvas that is a multiple of 32 with the image at ``(pad, pad)``.
    """
    def aligned(n):
        return max(align, int(np.ceil((n + 2 * pad) / align)) * align)
    return aligned(width), aligned(height)


def ctc_decode(logits, charset, blank=0):
    """Greedy CTC decode of a (T, C) score table.

    Returns ``(text, confidence)`` where confidence is the mean probability of
    the characters that were kept (the reference implementation's per-character average).
    """
    table = np.asarray(logits, dtype=np.float32)
    if table.ndim != 2 or table.shape[0] == 0:
        return "", 0.0
    # Softmax only if the graph returns raw logits.
    row_sums = table.sum(axis=1)
    if not np.allclose(row_sums, 1.0, atol=1e-2):
        e = np.exp(table - table.max(axis=1, keepdims=True))
        table = e / e.sum(axis=1, keepdims=True)

    idx = table.argmax(axis=1)
    probs = table.max(axis=1)
    chars = []
    kept = []
    prev = -1
    for step, k in enumerate(idx):
        if k != blank and k != prev:
            chars.append(charset[k] if 0 <= k < len(charset) else "")
            kept.append(float(probs[step]))
        prev = k
    text = "".join(chars).strip()
    conf = float(np.mean(kept)) if kept else 0.0
    return text, conf


def load_charset(dict_path):
    """PaddleOCR character table: blank, dictionary lines, then space."""
    text = Path(dict_path).read_text(encoding="utf-8")
    lines = text.splitlines()
    return ["blank"] + lines + [" "]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PpOcr:
    """PP-OCRv6 detect + recognise on OpenVINO. One instance per process."""

    def __init__(self, det_model=DET_MODEL, rec_model=REC_MODEL, dict_path=REC_DICT):
        self.det_path = Path(det_model)
        self.rec_path = Path(rec_model)
        self.dict_path = Path(dict_path)
        for p in (self.det_path, self.rec_path, self.dict_path):
            if not p.is_file():
                raise OcrUnavailable(f"missing PP-OCR model: {p}")

        from openvino import Core  # local import: keeps module import cheap

        core = Core()
        self._det_model = core.read_model(str(self.det_path))
        self._rec_model = core.read_model(str(self.rec_path))
        self._det = core.compile_model(self._det_model, "CPU")
        self._rec = core.compile_model(self._rec_model, "CPU")
        self.charset = load_charset(self.dict_path)
        self._lock = threading.Lock()
        logger.info(
            "PP-OCR ready: det=%s rec=%s dict=%d",
            self.det_path.name, self.rec_path.name, len(self.charset))

    # -- detection ---------------------------------------------------------
    def _prepare_det(self, img_bgr):
        h, w = img_bgr.shape[:2]
        ratio = 1.0 if max(h, w) <= DET_MAX_SIDE else DET_MAX_SIDE / max(h, w)
        rw = max(1, int(round(w * ratio)))
        rh = max(1, int(round(h * ratio)))
        resized = (cv2.resize(img_bgr, (rw, rh), interpolation=cv2.INTER_CUBIC)
                   if (rw, rh) != (w, h) else img_bgr)
        cw, ch = det_canvas_size(rw, rh)
        canvas = np.zeros((ch, cw, 3), dtype=np.uint8)
        canvas[DET_PAD:DET_PAD + rh, DET_PAD:DET_PAD + rw] = resized
        x = (canvas.astype(np.float32) - DET_NORM) / DET_NORM
        return x.transpose(2, 0, 1)[None], rw / w, rh / h

    def detect(self, img_bgr):
        """Return ``[(quad, score, bbox), ...]`` in source-image coordinates."""
        h, w = img_bgr.shape[:2]
        inp, sx, sy = self._prepare_det(img_bgr)
        with self._lock:
            out = self._det([inp])[self._det.outputs[0]]
        prob = np.asarray(out)[0][0]
        return self._db_postprocess(prob, sx, sy, w, h)

    def _db_postprocess(self, prob, sx, sy, img_w, img_h):
        mask = (prob > DET_THRESH).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            if len(contour) < 4:
                continue
            blob = np.zeros_like(mask)
            cv2.drawContours(blob, [contour], -1, 1, -1)
            score = float(prob[blob > 0].mean())
            if score < DET_BOX_THRESH:
                continue
            (cx, cy), (bw, bh), angle = cv2.minAreaRect(contour)
            if bw < 1 or bh < 1:
                continue
            offset = bw * bh * DET_UNCLIP / (2 * (bw + bh))
            quad = cv2.boxPoints(((cx, cy), (bw + 2 * offset, bh + 2 * offset), angle))
            quad = np.array([[(x - DET_PAD) / sx, (y - DET_PAD) / sy] for x, y in quad],
                            dtype=np.float32)
            quad[:, 0] = quad[:, 0].clip(0, img_w)
            quad[:, 1] = quad[:, 1].clip(0, img_h)
            x0, y0 = quad.min(axis=0)
            x1, y1 = quad.max(axis=0)
            if x1 - x0 < MIN_BOX_PX or y1 - y0 < MIN_BOX_PX:
                continue
            boxes.append((quad, score, (float(x0), float(y0), float(x1), float(y1))))
        boxes.sort(key=lambda b: (b[2][1], b[2][0]))
        return boxes

    # -- recognition -------------------------------------------------------
    def _crop(self, img_bgr, quad):
        pts = order_quad(quad)
        cw = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[3] - pts[2])))
        ch = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
        if cw < 1 or ch < 1:
            return None
        dst = np.array([[0, 0], [cw, 0], [cw, ch], [0, ch]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(pts, dst)
        return cv2.warpPerspective(img_bgr, matrix, (cw, ch))

    def _prepare_rec(self, crop):
        if crop.shape[0] > crop.shape[1] * 1.5:   # tall crop: a vertical line
            crop = np.rot90(crop)
        ch, cw = crop.shape[:2]
        nw = max(1, int(round(REC_HEIGHT * cw / ch)))
        if nw > REC_MAX_WIDTH:
            nw = REC_MAX_WIDTH
        resized = cv2.resize(crop, (nw, REC_HEIGHT), interpolation=cv2.INTER_LINEAR)
        x = resized.astype(np.float32) / 255.0
        x = (x - REC_NORM) / REC_NORM
        return x.transpose(2, 0, 1)[None]

    def recognize(self, img_bgr, boxes):
        """Recognise detected boxes; returns lines passing the confidence floor."""
        lines = []
        for quad, det_score, bbox in boxes:
            crop = self._crop(img_bgr, quad)
            if crop is None or crop.size == 0:
                continue
            with self._lock:
                out = self._rec([self._prepare_rec(crop)])[self._rec.outputs[0]]
            text, conf = ctc_decode(np.asarray(out)[0], self.charset)
            if not text or conf < REC_MIN_CONF:
                continue
            x0, y0, x1, y1 = bbox
            lines.append({
                "text": text,
                "conf": round(conf, 3),
                "det_conf": round(float(det_score), 3),
                "x_min": int(round(x0)), "y_min": int(round(y0)),
                "x_max": int(round(x1)), "y_max": int(round(y1)),
            })
        return lines

    # -- public ------------------------------------------------------------
    def recognize_image(self, img_bgr, timings=None):
        """Full detect+recognise pass over a BGR image."""
        if img_bgr is None or img_bgr.size == 0:
            return []
        t0 = time.time()
        boxes = self.detect(img_bgr)
        t1 = time.time()
        lines = self.recognize(img_bgr, boxes)
        t2 = time.time()
        if timings is not None:
            timings["detect_ms"] = round((t1 - t0) * 1000, 1)
            timings["recognize_ms"] = round((t2 - t1) * 1000, 1)
            timings["det_boxes"] = len(boxes)
            timings["kept_lines"] = len(lines)
        logger.info(
            "PP-OCR: %dx%d det=%d kept=%d detect=%.0fms rec=%.0fms",
            img_bgr.shape[1], img_bgr.shape[0], len(boxes), len(lines),
            (t1 - t0) * 1000, (t2 - t1) * 1000)
        return lines

    def run(self, image, timings=None):
        """Detect + recognise, returning the Flask-style ``{coords: text}`` map."""
        img = cv2.imread(str(image)) if isinstance(image, (str, Path)) else image
        lines = self.recognize_image(img, timings=timings)
        result = {}
        for line in lines:
            key = f"{line['x_min']},{line['x_max']},{line['y_min']},{line['y_max']}"
            if key in result:
                result[key] = (result[key] + " " + line["text"]).strip()
            else:
                result[key] = line["text"]
        return result


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    """Process-wide lazily-built engine (raises OcrUnavailable if no models)."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = PpOcr()
    return _engine


if __name__ == "__main__":  # manual check: python ppocr.py <image.png>
    import sys

    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s: %(message)s")
    if len(sys.argv) < 2:
        print("usage: python ppocr.py <image.png>")
        raise SystemExit(2)
    t = {}
    res = get_engine().run(sys.argv[1], timings=t)
    print(f"lines={len(res)} timings={t}")
    for k, v in res.items():
        print(f"  {k}: {v}")
