import os
import cv2
import numpy as np
from openvino import Core
import text_displayer
from pathlib import Path

# Get the current Python file's directory
current_file_directory = Path(__file__).parent

# Define the crops folder path
crops_folder = current_file_directory / "crops"

# Create the folder if it doesn't exist
crops_folder.mkdir(parents=True, exist_ok=True)

print(crops_folder)

class TextDetector:
    def __init__(self) -> None:
        ie = Core()
        # Load model and weights
        self.model = ie.read_model(
            model="models/horizontal-text-detection-0001.xml",
            weights="models/horizontal-text-detection-0001.bin"
        )
        self.execution_net = ie.compile_model(self.model, "CPU")
        self.colors = {"red": (0, 0, 255), "green": (0, 255, 0)}
        self.input_layer = self.model.inputs[0]
        self.output_layer = self.model.outputs[0]
        
    def calculate_iou(self, box1, box2):
        """Calculate Intersection over Union (IoU) between two boxes."""
        x_min1, y_min1, x_max1, y_max1 = box1
        x_min2, y_min2, x_max2, y_max2 = box2
        
        # Calculate intersection area
        inter_x_min = max(x_min1, x_min2)
        inter_y_min = max(y_min1, y_min2)
        inter_x_max = min(x_max1, x_max2)
        inter_y_max = min(y_max1, y_max2)
        
        if inter_x_min < inter_x_max and inter_y_min < inter_y_max:
            inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        else:
            inter_area = 0
        
        # Calculate area of both boxes
        box1_area = (x_max1 - x_min1) * (y_max1 - y_min1)
        box2_area = (x_max2 - x_min2) * (y_max2 - y_min2)
        
        # Calculate IoU
        iou = inter_area / (box1_area + box2_area - inter_area)
        return iou
    
    def non_maximum_suppression(self, boxes, confidence_scores, iou_threshold):
        """Apply Non-Maximum Suppression to filter overlapping boxes."""
        indices = np.argsort(confidence_scores)[::-1]  # Sort by confidence score in descending order
        keep_boxes = []
        
        while len(indices) > 0:
            current_idx = indices[0]
            keep_boxes.append(boxes[current_idx])
            indices = indices[1:]
            
            # Compare current box with the remaining ones and remove those with high IoU
            remaining_indices = []
            for idx in indices:
                iou = self.calculate_iou(boxes[current_idx], boxes[idx])
                if iou < iou_threshold:  # Only keep boxes with IoU below the threshold
                    remaining_indices.append(idx)
            
            indices = remaining_indices
        
        return keep_boxes
    
    # from the detected texts save each of them as a separate crop. save them with their specific coordinates in the image. these coordinates are later used to display the translated text in the right place
    def save_crops(self, im_name, original_image, resized_image, predictions):
        # Ensure crops folder exists
            # Ensure crops folder exists
        os.makedirs(crops_folder, exist_ok=True)
        
        # Clear the folder
        clear_crops_folder(crops_folder)
        
        # Fetch image shapes to calculate ratio
        (real_y, real_x), (resized_y, resized_x) = original_image.shape[:2], resized_image.shape[:2]
        ratio_x, ratio_y = real_x / resized_x, real_y / resized_y
        
        text_coordinates = []  # To store coordinates of detected text
        
        boxes = []
        confidence_scores = []
        
        for box in predictions:
            conf = box[-1]
            
            (x_min, y_min, x_max, y_max) = [
                int(max(corner_position * ratio_y, 10)) if idx % 2 
                else int(corner_position * ratio_x)
                for idx, corner_position in enumerate(box[:-1])
            ]
            
            # Append to list for NMS
            boxes.append([x_min, y_min, x_max, y_max])
            confidence_scores.append(conf)
        
        # Apply Non-Maximum Suppression to filter out overlapping boxes. the model sometimes detects the same text twice and draws overlapping boxes , 
        nms_boxes = self.non_maximum_suppression(boxes, confidence_scores, iou_threshold=0.1)
        
        for box in nms_boxes:
            x_min, y_min, x_max, y_max = box
            cropped_text = original_image[y_min:y_max, x_min:x_max]
            crop_file_name = f"{x_min},{x_max},{y_min},{y_max}.png"
            crop_file_path = os.path.join(crops_folder, crop_file_name)
            cv2.imwrite(crop_file_path, cropped_text)
            
            # Append the details
            text_coordinates.append({
                "x_min": x_min,
                "y_min": y_min,
                "x_max": x_max,
                "y_max": y_max,
                "confidence": conf,
                "file_name": crop_file_path
            })
        
        return text_coordinates
    
    def draw_overlay(self, im_name, original_image, resized_image, predictions):
        """Draw bounding boxes on the image."""
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
            
            # Add to list
            boxes.append([x_min, y_min, x_max, y_max])
            confidence_scores.append(conf)
        
        # Apply Non-Maximum Suppression with the IoU threshold
        nms_boxes = self.non_maximum_suppression(boxes, confidence_scores, iou_threshold=0.2)
        
        for box in nms_boxes:
            x_min, y_min, x_max, y_max = box
            original_image = cv2.rectangle(original_image, (x_min, y_min), (x_max, y_max), self.colors["green"], 1)
        
        # Display the image with the boxes
        cv2.imshow('Detected Text', original_image)
        cv2.waitKey(0)  # Wait until a key is pressed
        cv2.destroyAllWindows()  # Close the image window
    
    def test(self, image_path, threshold=0.3):
        im_name = os.path.basename(image_path)
        # Reading the image
        img = cv2.imread(image_path)
        
        # Extracting model inputs
        _, _, height, width = self.input_layer.shape
        
        # Resizing the input image to desired size
        resized_image = cv2.resize(img, (width, height))
        input_image = np.expand_dims(resized_image.transpose(2, 0, 1), 0)
        
        # Inference on the input image
        result = self.execution_net.infer_new_request({self.input_layer.any_name: input_image})
        
        # Output predictions
        predictions = result[1]

        if predictions.ndim == 1:
            predictions = predictions[np.newaxis, :]
        
        # Removing zero predictions  
        predictions_req = predictions[~np.all(predictions == 0, axis=1)]
        
        # Save cropped images and return coordinates
        text_coordinates = self.save_crops(im_name, img, resized_image, predictions_req)
        
        max_probability = 0
        
        self.draw_overlay(im_name, img, resized_image, predictions_req)
            
        return "TEXT NOT PRESENT", text_coordinates
    
# if __name__ == "__main__":
#     obj = TextDetector()
#     threshold = 0.5
    
#     # Inferencing image containing text (based on threshold)
#     text_image_path = "image1.png"
#     result, coordinates = obj.test(text_image_path, threshold)
#     print(result)
#     print("Detected Text Coordinates:")
#     for coord in coordinates:
#         print(coord)
#     text_displayer.main()
# In paste.py
def clear_crops_folder(folder_path):
    """Deletes all files in the specified folder."""
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")

def main(image_path="image1.png", threshold=0.3, x1=0, y1=0, destination='hi', alpha = 0.9, font_size = 10):
    obj = TextDetector()
    
    result, coordinates = obj.test(image_path, threshold)
    os.remove(image_path)

    #call the displayer python script after the detection is done and the deteted crop files are saved in the crops folder
    text_displayer.main(x1=x1,y1=y1,dest=destination,alpha=alpha, font_size = font_size)

if __name__ == "__main__":
    # Default image path when run directly
    main("image1.png")