import os
import logging
import cv2
import numpy as np
from openvino import Core
from pathlib import Path

logger = logging.getLogger(__name__)

_this_dir = Path(__file__).parent
crops_folder = _this_dir / "crops"
crops_folder.mkdir(parents=True, exist_ok=True)

_detector_instance = None


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
        model_path = "models/horizontal-text-detection-0001.xml"
        weights_path = "models/horizontal-text-detection-0001.bin"
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

        if preds.ndim == 1:
            preds = preds[np.newaxis, :]
        preds = preds[~np.all(preds == 0, axis=1)]

        # Scale back to original image coordinates
        ry, rx = img.shape[:2]
        rry, rrx = resized.shape[:2]
        sx, sy = rx / rrx, ry / rry
        logger.info(f"Scale factors: sx={sx:.4f}, sy={sy:.4f}")

        boxes, confs = [], []
        for p in preds:
            conf = p[-1]
            x_min = int(max(p[0] * sx, 0))
            y_min = int(max(p[1] * sy, 0))
            x_max = int(p[2] * sx)
            y_max = int(p[3] * sy)
            boxes.append([x_min, y_min, x_max, y_max])
            confs.append(conf)

        nms_boxes = self.nms(boxes, confs, iou_thresh=0.1)

        coordinates = []
        for box in nms_boxes:
            x_min, y_min, x_max, y_max = box
            crop = img[y_min:y_max, x_min:x_max]
            fname = f"{x_min},{x_max},{y_min},{y_max}.png"
            fpath = os.path.join(crops_folder, fname)
            cv2.imwrite(fpath, crop)
            coordinates.append({
                'x_min': x_min, 'y_min': y_min,
                'x_max': x_max, 'y_max': y_max,
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
        try:
            os.remove(image_path)
        except OSError:
            pass

        if not coords:
            logger.warning("No text regions detected")
            return

        logger.info(f"{len(coords)} regions detected, running OCR + translation")
        overlay.show_translations(
            screen_x=x1, screen_y=y1, dest=destination,
            alpha=alpha, font_size=font_size, text_color=text_color,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)


if __name__ == "__main__":
    main("image1.png")
