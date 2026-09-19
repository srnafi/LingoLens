import os
import sys
import json
import time
import logging
from flask import Flask, jsonify, request
import easyocr

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global reader — initialized once in __main__, reused for all requests
reader = None

script_directory = os.path.dirname(os.path.abspath(__file__))
model_directory = os.path.join(script_directory, "EasyOCR", "model")


def process_folder(folder_location):
    """Run OCR on all images in a folder, delete processed crops, return {coords: text}."""
    detected_texts = {}

    for file_name in os.listdir(folder_location):
        file_path = os.path.join(folder_location, file_name)

        if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            logger.info(f"Processing image: {file_path}")
            try:
                result = reader.recognize(file_path)
                detected_text = ' '.join([box[1] for box in result])
                coordinates = file_name.replace(".png", "")
                detected_texts[coordinates] = detected_text
                os.remove(file_path)
            except Exception as e:
                logger.error(f"OCR failed for {file_path}: {e}")

    return detected_texts


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint — returns OK when the server is ready."""
    if reader is not None:
        return jsonify({"status": "ready"}), 200
    return jsonify({"status": "initializing"}), 503


@app.route('/ocr', methods=['POST'])
def ocr():
    """Run OCR on all crops in the given folder."""
    start = time.time()
    folder_location = request.json.get('folder_location', '')

    if not folder_location or not os.path.isdir(folder_location):
        return jsonify({"error": "Invalid folder location"}), 400

    if reader is None:
        return jsonify({"error": "OCR engine not ready"}), 503

    results = process_folder(folder_location)

    output_file = os.path.join(folder_location, 'ocr_results.json')
    with open(output_file, 'w', encoding='utf-8') as json_file:
        json.dump(results, json_file, ensure_ascii=False, indent=4)

    elapsed = time.time() - start
    logger.info(f"OCR completed in {elapsed:.2f}s — {len(results)} regions processed")
    return jsonify(results)


@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Graceful shutdown endpoint."""
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        import os
        os._exit(0)
    func()
    return jsonify({"status": "shutting_down"}), 200


# Language option -> EasyOCR language list mapping
LANGUAGE_MAP = {
    1: ['es', 'fr', 'it', 'pt', 'vi', 'de', 'en'],       # European / Multilingual
    2: ['ch_sim', 'en'],                                     # Simplified Chinese
    3: ['ja', 'en'],                                         # Japanese
    4: ['ru', 'en'],                                         # Russian
    5: ['bn', 'en'],                                         # Bengali
    6: ['ko', 'en'],                                         # Korean
}


def create_reader(option):
    """Create an EasyOCR Reader for the given language option."""
    langs = LANGUAGE_MAP.get(option, LANGUAGE_MAP[1])
    logger.info(f"Initializing EasyOCR Reader for languages: {langs}")
    r = easyocr.Reader(
        langs,
        model_storage_directory=model_directory,
        gpu=False,
        download_enabled=True,
        detector=False,
    )
    logger.info("EasyOCR Reader ready")
    return r


if __name__ == '__main__':
    option = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    reader = create_reader(option)
    logger.info(f"Flask OCR server starting on port 5000 (language option={option})")
    app.run(port=5000)
