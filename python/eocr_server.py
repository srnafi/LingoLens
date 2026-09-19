import os
from flask import Flask, jsonify, request
import easyocr
import time, sys
import json

app = Flask(__name__)

# Get the directory of the current script
script_directory = os.path.dirname(os.path.abspath(__file__))

# Set the model directory relative to the script's location
model_directory = os.path.join(script_directory, "EasyOCR", "model")

reader = easyocr.Reader(['es', 'fr', 'it', 'pt', 'vi', 'de', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)

def process_folder(folder_location):
    detected_texts = {}
    
    # List all files in the folder
    for file_name in os.listdir(folder_location):
        file_path = os.path.join(folder_location, file_name)
        
        # Check if it's an image file (you can add more extensions if needed)
        if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            print(f"Processing image: {file_path}")
            
            # Perform OCR
            result = reader.recognize(file_path)
            
            # Extract text from result
            detected_text = ' '.join([box[1] for box in result])
            # Extract coordinates from the filename (e.g., "382,469,540,578.png" -> "382,469,540,578")
            coordinates = file_name.replace(".png", "") 
            # Store the detected text with coordinates as the key
            detected_texts[coordinates] = detected_text
            # remove the crops after the ocr is done
            os.remove(file_path)
    
    return detected_texts

@app.route('/ocr', methods=['POST'])
def ocr():
    start = time.time()
    # Get folder location from request
    folder_location = request.json.get('folder_location', '')

    if not folder_location or not os.path.isdir(folder_location):
        return jsonify({"error": "Invalid folder location"}), 400

    # Process the images in the folder sequentially
    results = process_folder(folder_location)

    # Write results to a JSON file
    output_file = os.path.join(folder_location, 'ocr_results.json')
    with open(output_file, 'w', encoding='utf-8') as json_file:
        json.dump(results, json_file, ensure_ascii=False, indent=4)

    end = time.time()

    # Return detected text as a JSON response
    return jsonify(results)

if __name__ == '__main__':

    # initialize the specific reader based on the provided argument
    option = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    if option == 1:
        reader = easyocr.Reader(['es', 'fr', 'it', 'pt', 'vi', 'de', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)
    elif option == 2:
        # Simplified Chinese
        reader = easyocr.Reader(['ch_sim', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)
    elif option == 3:
        # Japanese
        reader = easyocr.Reader(['ja', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)
    elif option == 4:
        # Russian
        reader = easyocr.Reader(['ru', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)
    elif option == 5:
        # Bengali
        reader = easyocr.Reader(['bn', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)
    elif option == 6:
        # Korean
        reader = easyocr.Reader(['ko', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)
    else:
        reader = easyocr.Reader(['es', 'fr', 'it', 'pt', 'vi', 'de', 'en'], model_storage_directory=model_directory, gpu=False, download_enabled=True, detector=False)
    app.run(port=5000)
