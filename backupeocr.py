import tkinter as tk
import ctypes
import requests
import json
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt
import time
from translate import translate_word
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from width import get_text_width
import logging
# Configure logging
logging.basicConfig(
    filename='eocr_server.log',  # Log file name
    level=logging.DEBUG,         # Log level: DEBUG for detailed information
    format='%(asctime)s - %(levelname)s - %(message)s'  # Log message format
)

def main(x1,y1, dest):
    x = x1
    y = y1
    dest_lang = dest
    print(dest_lang)
    # If your Windows version is >= 8.1
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  
    except:
        ctypes.windll.user32.SetProcessDPIAware()  # for Windows 8.0 or lower

    # Function to make the OCR request to the server
    def run_ocr_request(folder_location):
        start = time.time()
        # URL of the Flask server
        url = 'http://localhost:5000/ocr'
        # Prepare the data to send in JSON format
        data = {
            'folder_location': folder_location
        }

        # Send the POST request with the folder location
        response = requests.post(url, json=data)

        # Check if the request was successful
        if response.status_code == 200:
            print("OCR Results:")
            ocr_results = response.json()  # This should return a dictionary of OCR results
            end = time.time()
            print("Time taken:", end - start)  # The server's response (OCR results)
            return ocr_results
        else:
            print(f"Error: {response.status_code}, {response.text}")
            return {}

    # Create a dummy root window and immediately withdraw it
    root = tk.Tk()
    root.withdraw()
    def translate_batch_words(word):
        try:        # Remove only the unwanted symbols
                    # This will remove ALL symbols, including underscores and parentheses
            cleaned_word = re.sub(r'[^\w\s]', '', word)  # Remove unwanted symbols
            return translate_word(cleaned_word,dest_lang)
        except Exception as e:
            logging.info(f"Error during batch translation: {str(e)}")
            print(f"Error during batch translation: {str(e)}")
            return word  # Return the original words in case of an error
    # Example folder location
    folder_location = "F:/Final Product/test/python/crops"  # You can change this dynamically
    
    # Fetch the OCR results from the server
    ocr_results = run_ocr_request(folder_location)
    
    # Extract all the words from the OCR results into a list
    # words_to_translate = list(ocr_results.values())

    # Translate all words at once
    #translated_words = translate_batch_words(words_to_translate)

    translated_words = {}

    total_threads = min(32, (os.cpu_count() or 4) * 5)  # Dynamically set threads, max 32

    with ThreadPoolExecutor(max_workers=total_threads) as executor:
        # Submit translation tasks for each word
        futures = {
            executor.submit(translate_batch_words, word): coords
            for coords, word in ocr_results.items()
        }

        # Process results as they complete
        for future in as_completed(futures):
            coords = futures[future]
            translated_words[coords] = future.result()



    print(translated_words)
    translated_words = dict(
        sorted(translated_words.items(), key=lambda item: int(item[0].split(',')[0]))
    )
    print(translated_words)
    # Create a new dictionary with the translated words
    #translated_results = {coords: translated_words[i] for i, coords in enumerate(ocr_results.keys())}

    # Print the translated OCR results
    # print("Translated OCR Results:")
    # for coords, tr_word in translated_results.items():
    #     print(f"Coordinates: {coords}, Translated Word: {tr_word}")
    

    # Base coordinates for placing the windows
    rightmost_cord, old_y = 0, 0  # To track the rightmost coordinate and previous Y for overlap handling
    old_y_min, old_y_max = 0, 0
# Dictionary to store rightmost_x and Y bounds for each line
    line_info = []  # Key: line_index (y_min), Value: (rightmost_x, y_min, y_max)

    # Iterate through the dictionary of OCR results
    for coords, text in translated_words.items():
    # Parse the coordinates from the OCR result (format: 'x_min,x_max,y_min,y_max')
        x_min, x_max, y_min, y_max = map(int, coords.split(','))
        word_width = x_max - x_min  # Adjust width
        
        tr_word = text
        new_width, new_height = get_text_width(tr_word)
        
        # Check for overlaps with previously processed words
        for prev_x_min, prev_x_max, prev_y_min, prev_y_max, rightmost_x in line_info:
            if not (y_max < prev_y_min or y_min > prev_y_max):  # Check vertical overlap
                if x_min < rightmost_x:  # Check horizontal overlap
                    x_min = rightmost_x + 1  # Adjust X position to avoid overlap

        # Update the rightmost X position for this word
        rightmost_x = x_min + new_width
        line_info.append((x_min, rightmost_x, y_min, y_max, rightmost_x))

        # Debug print to check output
        print(f"Word: {tr_word}, X_min: {x_min}, Line_Y: {y_min}")

        # Here, you can add logic to place the word in your output system


        print(new_width, rightmost_cord, x_min)
        print(old_y_min, old_y_max, y_min,y_max)

        old_y_min = y_min
        old_y_max = y_max

        # if old_y != 0 and -30 > old_y - y_min > 30:
        #     overlapping = 0

        # if overlapping > 0 and old_y != 0 and -30 < old_y - y_min < 30:
        #     x_min = x_min + overlapping


        # if rightmost_cord > x_min:
        #     overlapping = rightmost_cord - x_min



        # Update the Y position for the next word

        # # Update the rightmost coordinate
        # rightmost_cord = x_min + new_width

        # Create a Toplevel window for each word
        word_window = tk.Toplevel()
        word_window.geometry(f'+{x_min + x}+{y_min + y}')  # Position the window using base coordinates
        #print(f'Window position: {x_min + x}, {y_min + y}')
        word_window.overrideredirect(True)  # Remove window decorations (e.g., title bar)
        word_window.attributes('-alpha', 0.7)  # Set transparency
        word_window.attributes('-topmost', True)  # Keep the window on top
        word_window.wm_attributes('-transparentcolor', 'white')  # Make the background transparent

        # Create the canvas for displaying the translated word
        canvas = tk.Canvas(word_window, width=new_width, height=new_height, highlightthickness=0)
        canvas.pack()

        # Display the translated text on the canvas
        canvas.create_text(2, -1, anchor='nw', text=tr_word, font=("fixedsys", 12), fill='black')

        rightmost_cord = x_min + new_width
    # Start the Tkinter event loop
    tk.mainloop()


    

if __name__ == "__main__":
    main()