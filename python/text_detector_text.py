import os
import logging
import cv2
import numpy as np
from openvino import Core
import text_displayer
from pathlib import Path

logger = logging.getLogger(__name__)

current_file_directory = Path(__file__).parent
crops_folder = current_file_directory / "crops"
crops_folder.mkdir(parents=True, exist_ok=True)

# Singleton TextDetector — loaded once, reused across snips
_detector_instance = None


def get_detector():
    """Lazy-load the OpenVINO TextDetector singleton."""
    global _detector_instance
    if _detector_instance is None:
        logger.info("Loading OpenVINO text detection model...")
        _detector_instance = TextDetector()
        logger.info("OpenVINO text detection model ready")
    return _detector_instance


class TextDetector:
    def __init__(self):
        ie = Core()
        model_path = "models/horizontal-text-detection-0001.xml"
        weights_path = "models/horizontal-text-detection-0001.bin"
        if not os.path.exists(model_path) or not os.path.exists(weights_path):
            raise FileNotFoundError(
                f"OpenVINO text detection model not found.\n"
                f"Expected: {model_path}\n"
                f"Expected: {weights_path}\n"
                f"Download from: https://github.com/openvinotoolkit/open_model_zoo"
            )
        self.model = ie.read_model(model=model_path, weights=weights_path)
        self.execution_net = ie.compile_model(self.model, "CPU")
        self.colors = {"red": (0, 0, 255), "green": (0, 255, 0)}
        self.input_layer = self.model.inputs[0]
        self.output_layer = self.model.outputs[0]

    def calculate_iou(self, box1, box2):
        x_min1, y_min1, x_max1, y_max1 = box1
        x_min2, y_min2, x_max2, y_max2 = box2

        inter_x_min = max(x_min1, x_min2)
        inter_y_min = max(y_min1, y_min2)
        inter_x_max = min(x_max1, x_max2)
        inter_y_max = min(y_max1, y_max2)

        if inter_x_min < inter_x_max and inter_y_min < inter_y_max:
            inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        else:
            inter_area = 0

        box1_area = (x_max1 - x_min1) * (y_max1 - y_min1)
        box2_area = (x_max2 - x_min2) * (y_max2 - y_min2)

        iou = inter_area / (box1_area + box2_area - inter_area + 1e-6)
        return iou

    def non_maximum_suppression(self, boxes, confidence_scores, iou_threshold):
        indices = np.argsort(confidence_scores)[::-1]
        keep_boxes = []

        while len(indices) > 0:
            current_idx = indices[0]
            keep_boxes.append(boxes[current_idx])
            indices = indices[1:]

            remaining_indices = []
            for idx in indices:
                iou = self.calculate_iou(boxes[current_idx], boxes[idx])
                if iou < iou_threshold:
                    remaining_indices.append(idx)
            indices = remaining_indices

        return keep_boxes

    def save_crops(self, im_name, original_image, resized_image, predictions):
        os.makedirs(crops_folder, exist_ok=True)
        clear_crops_folder(crops_folder)

        (real_y, real_x), (resized_y, resized_x) = original_image.shape[:2], resized_image.shape[:2]
        ratio_x, ratio_y = real_x / resized_x, real_y / resized_y

        text_coordinates = []
        boxes = []
        confidence_scores = []

        for box in predictions:
            conf = box[-1]
            (x_min, y_min, x_max, y_max) = [
                int(max(corner_position * ratio_y, 10)) if idx % 2
                else int(corner_position * ratio_x)
                for idx, corner_position in enumerate(box[:-1])
            ]
            boxes.append([x_min, y_min, x_max, y_max])
            confidence_scores.append(conf)

        nms_boxes = self.non_maximum_suppression(boxes, confidence_scores, iou_threshold=0.1)

        for box in nms_boxes:
            x_min, y_min, x_max, y_max = box
            cropped_text = original_image[y_min:y_max, x_min:x_max]
            crop_file_name = f"{x_min},{x_max},{y_min},{y_max}.png"
            crop_file_path = os.path.join(crops_folder, crop_file_name)
            cv2.imwrite(crop_file_path, cropped_text)

            text_coordinates.append({
                "x_min": x_min,
                "y_min": y_min,
                "x_max": x_max,
                "y_max": y_max,
                "confidence": conf,
                "file_name": crop_file_path,
            })

        return text_coordinates

    def draw_overlay(self, im_name, original_image, resized_image, predictions):
        (real_y, real_x), (resized_y, resized_x) = original_image.shape[:2], resized_image.shape[:2]
        ratio_x, ratio_y = real_x / resized_x, real_y / resized_y

        boxes = []
        confidence_scores = []

        for box in predictions:
            conf = box[-1]
            (x_min, y_min, x_max, y_max) = [
                int(max(corner_position * ratio_y, 10)) if idx % 2
                else int(corner_position * ratio_x)
                for idx, corner_position in enumerate(box[:-1])
            ]
            boxes.append([x_min, y_min, x_max, y_max])
            confidence_scores.append(conf)

        nms_boxes = self.non_maximum_suppression(boxes, confidence_scores, iou_threshold=0.2)

        for box in nms_boxes:
            x_min, y_min, x_max, y_max = box
            original_image = cv2.rectangle(original_image, (x_min, y_min), (x_max, y_max), self.colors["green"], 1)

        return original_image

    def detect(self, image_path):
        """Run text detection on an image. Returns (cropped_count, coordinates)."""
        im_name = os.path.basename(image_path)
        img = cv2.imread(image_path)
        if img is None:
            logger.error(f"Failed to read image: {image_path}")
            return 0, []

        _, _, height, width = self.input_layer.shape
        resized_image = cv2.resize(img, (width, height))
        input_image = np.expand_dims(resized_image.transpose(2, 0, 1), 0)

        result = self.execution_net.infer_new_request({self.input_layer.any_name: input_image})
        predictions = result[1]

        if predictions.ndim == 1:
            predictions = predictions[np.newaxis, :]

        predictions_req = predictions[~np.all(predictions == 0, axis=1)]
        text_coordinates = self.save_crops(im_name, img, resized_image, predictions_req)

        return len(text_coordinates), text_coordinates


def clear_crops_folder(folder_path):
    """Delete all files in the specified folder."""
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")


def main(image_path="image1.png", threshold=0.3, x1=0, y1=0,
         destination='hi', alpha=0.9, font_size=10, text_color="#000000"):
    """Full pipeline: detect text -> crop -> OCR -> translate -> display overlays."""
    try:
        detector = get_detector()
        count, coordinates = detector.detect(image_path)

        # Clean up the source screenshot
        try:
            os.remove(image_path)
        except OSError:
            pass

        if count == 0:
            logger.warning("No text regions detected")
            return

        logger.info(f"Detected {count} text regions, running OCR + translation overlay")

        text_displayer.main(
            x1=x1, y1=y1, dest=destination,
            alpha=alpha, font_size=font_size, text_color=text_color,
        )
    except Exception as e:
        logger.error(f"Text detection pipeline failed: {e}", exc_info=True)


if __name__ == "__main__":
    main("image1.png")
