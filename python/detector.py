import os
import logging
import time
import cv2
import numpy as np
from openvino import Core
from pathlib import Path

logger = logging.getLogger(__name__)

_this_dir = Path(__file__).parent
crops_folder = _this_dir / "crops"
crops_folder.mkdir(parents=True, exist_ok=True)

_detector_instance = None

# ---------------------------------------------------------------------------
# Detection thresholds (spec section 5, defect 7)
# ---------------------------------------------------------------------------
CONF_THRESHOLD = float(os.environ.get("LINGOLENS_CONF", "0.3"))
NMS_IOU = 0.1
MIN_BOX_PX = 6  # drop boxes narrower or shorter than this many pixels


def postprocess_predictions(preds, sx, sy, img_w, img_h, conf_thr=None, iou_thr=None):
    """Post-process OpenVINO text-detection predictions into kept boxes.

    Pure function -- no I/O, no model state. Steps:
    1. Drop all-zero rows (padding / empty predictions).
    2. Drop rows with confidence < conf_thr.
    3. Scale normalized coords back to original image space.
    4. Clamp to [0, W] x [0, H].
    5. Drop degenerate boxes (width or height < MIN_BOX_PX).
    6. Non-maximum suppression.

    Parameters
    ----------
    preds : np.ndarray, shape (N, 5)
        Each row: [x_min_n, y_min_n, x_max_n, y_max_n, conf] in normalized coords.
    sx, sy : float
        Scale factors from model size to image size.
    img_w, img_h : int
        Original image dimensions (for clamping).
    conf_thr : float or None
        Confidence threshold; defaults to CONF_THRESHOLD.
    iou_thr : float or None
        NMS IoU threshold; defaults to NMS_IOU.

    Returns
    -------
    list[list[float]]
        Kept boxes as [x0, y0, x1, y1, conf], clamped and sorted by confidence desc.
    """
    import numpy as np

    if conf_thr is None:
        conf_thr = CONF_THRESHOLD
    if iou_thr is None:
        iou_thr = NMS_IOU

    if preds is None or len(preds) == 0:
        return []

    preds = np.asarray(preds, dtype=np.float64)
    if preds.ndim == 1:
        preds = preds[np.newaxis, :]

    # 1. Drop all-zero rows
    preds = preds[~np.all(preds == 0, axis=1)]

    # 2. Drop low-confidence
    if len(preds) > 0:
        confs = preds[:, -1]
        preds = preds[confs >= conf_thr]

    if len(preds) == 0:
        return []

    # 3. Scale to image coordinates
    boxes = []
    for p in preds:
        x_min = float(p[0] * sx)
        y_min = float(p[1] * sy)
        x_max = float(p[2] * sx)
        y_max = float(p[3] * sy)
        conf = float(p[4])
        boxes.append([x_min, y_min, x_max, y_max, conf])

    # 4. Clamp to image bounds
    for b in boxes:
        b[0] = max(0.0, min(b[0], float(img_w)))
        b[1] = max(0.0, min(b[1], float(img_h)))
        b[2] = max(0.0, min(b[2], float(img_w)))
        b[3] = max(0.0, min(b[3], float(img_h)))

    # 5. Drop degenerate boxes
    boxes = [b for b in boxes
             if (b[2] - b[0]) >= MIN_BOX_PX and (b[3] - b[1]) >= MIN_BOX_PX]

    if not boxes:
        return []

    # 6. NMS (using the existing calculate_iou / nms logic)
    det = TextDetector.__new__(TextDetector)
    boxes_only = [[b[0], b[1], b[2], b[3]] for b in boxes]
    scores = [b[4] for b in boxes]
    kept = det.nms(boxes_only, scores, iou_thresh=iou_thr)

    # Re-attach confidence to kept boxes
    kept_with_conf = []
    for kb in kept:
        for b in boxes:
            if b[:4] == kb:
                kept_with_conf.append(list(b))
                break
    # Sort by confidence descending
    kept_with_conf.sort(key=lambda b: b[4], reverse=True)
    return kept_with_conf


def get_detector():
    global _detector_instance
    if _detector_instance is None:
        logger.info("Loading OpenVINO text detection model...")
        _detector_instance = TextDetector()
        logger.info("OpenVINO model ready")
    return _detector_instance


class TextDetector:
    def __init__(self):
        ie = Core()
        model_path = str(_this_dir / "models" / "horizontal-text-detection-0001.xml")
        weights_path = str(_this_dir / "models" / "horizontal-text-detection-0001.bin")
        if not os.path.exists(model_path) or not os.path.exists(weights_path):
            raise FileNotFoundError(
                f"OpenVINO text detection model not found.\n"
                f"Expected: {model_path}\nExpected: {weights_path}\n"
                f"Download from: https://github.com/openvinotoolkit/open_model_zoo"
            )
        self.model = ie.read_model(model=model_path, weights=weights_path)
        self.execution_net = ie.compile_model(self.model, "CPU")
        self.input_layer = self.model.inputs[0]
        self.output_layer = self.model.outputs[0]

    def calculate_iou(self, box1, box2):
        x1a, y1a, x2a, y2a = box1
        x1b, y1b, x2b, y2b = box2
        ix1 = max(x1a, x1b); iy1 = max(y1a, y1b)
        ix2 = min(x2a, x2b); iy2 = min(y2a, y2b)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        area_a = (x2a - x1a) * (y2a - y1a)
        area_b = (x2b - x1b) * (y2b - y1b)
        return inter / (area_a + area_b - inter + 1e-6)

    def nms(self, boxes, scores, iou_thresh):
        idxs = np.argsort(scores)[::-1]
        keep = []
        while len(idxs) > 0:
            cur = idxs[0]
            keep.append(boxes[cur])
            idxs = idxs[1:]
            idxs = np.array([i for i in idxs
                             if self.calculate_iou(boxes[cur], boxes[i]) < iou_thresh])
        return keep

    def detect(self, image_path):
        """Detect text regions, crop them, return list of coordinate dicts."""
        img = cv2.imread(image_path)
        if img is None:
            logger.error(f"Failed to read: {image_path}")
            return []

        os.makedirs(crops_folder, exist_ok=True)
        _clear_folder(crops_folder)

        img_h, img_w = img.shape[:2]
        logger.info(f"Image size: {img_w}x{img_h}")

        _, _, h, w = self.input_layer.shape
        resized = cv2.resize(img, (w, h))
        inp = np.expand_dims(resized.transpose(2, 0, 1), 0)
        result = self.execution_net.infer_new_request({self.input_layer.any_name: inp})
        preds = result[1]

        # Scale back to original image coordinates
        ry, rx = img.shape[:2]
        rry, rrx = resized.shape[:2]
        sx, sy = rx / rrx, ry / rry
        logger.info(f"Scale factors: sx={sx:.4f}, sy={sy:.4f}")

        raw_count = len(preds) if preds is not None else 0
        t0 = time.time()
        kept_boxes = postprocess_predictions(preds, sx, sy, img_w, img_h)
        pp_ms = (time.time() - t0) * 1000
        logger.info(f"Detect: raw={raw_count}, kept={len(kept_boxes)}, "
                     f"conf_thr={CONF_THRESHOLD}, nms_iou={NMS_IOU}, postprocess={pp_ms:.1f}ms")

        coordinates = []
        for box in kept_boxes:
            x_min, y_min, x_max, y_max = [int(round(v)) for v in box[:4]]
            # Clamp (postprocess already clamped floats, but int rounding can push
            # a value to exactly img_w/img_h which is out of range for slicing)
            x_min = max(0, min(x_min, img_w - 1))
            y_min = max(0, min(y_min, img_h - 1))
            x_max = max(0, min(x_max, img_w))
            y_max = max(0, min(y_max, img_h))
            if x_max <= x_min or y_max <= y_min:
                logger.debug(f"Skip degenerate crop: ({x_min},{y_min})->({x_max},{y_max})")
                continue
            crop = img[y_min:y_max, x_min:x_max]
            if crop.size == 0:
                logger.debug(f"Skip empty crop at ({x_min},{y_min})->({x_max},{y_max})")
                continue
            fname = f"{x_min},{x_max},{y_min},{y_max}.png"
            fpath = os.path.join(crops_folder, fname)
            cv2.imwrite(fpath, crop)
            coordinates.append({
                'x_min': x_min, 'y_min': y_min,
                'x_max': x_max, 'y_max': y_max,
                'conf': float(box[4]) if len(box) > 4 else 0.0,
                'file_name': fpath,
            })

        logger.info(f"Detected {len(coordinates)} text regions")
        for c in coordinates:
            logger.debug(f"  crop: ({c['x_min']},{c['y_min']})->"
                         f"({c['x_max']},{c['y_max']})")
        return coordinates


def _clear_folder(folder):
    for f in os.listdir(folder):
        fp = os.path.join(folder, f)
        try:
            if os.path.isfile(fp):
                os.remove(fp)
        except Exception as e:
            logger.error(f"Failed to delete {fp}: {e}")


def main(image_path="image1.png", x1=0, y1=0, destination='hi',
         alpha=0.9, font_size=10, text_color="#000000"):
    """Pipeline: detect text -> crop -> hand off to overlay."""
    import overlay
    try:
        detector = get_detector()
        coords = detector.detect(image_path)

        if not coords:
            logger.warning("No text regions detected")
            try:
                os.remove(image_path)
            except OSError:
                pass
            return

        logger.info(f"{len(coords)} regions detected, running OCR + translation")
        overlay.show_translations(
            screen_x=x1, screen_y=y1, dest=destination,
            alpha=alpha, font_size=font_size, text_color=text_color,
            image_path=image_path,
        )

        # Clean up after overlay is done
        try:
            os.remove(image_path)
        except OSError:
            pass
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        # Ensure cleanup even on failure
        try:
            os.remove(image_path)
        except OSError:
            pass


if __name__ == "__main__":
    main("image1.png")
