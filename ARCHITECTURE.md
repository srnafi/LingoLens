# LingoLens Architecture (Pure Python)

## Overview

LingoLens is a pure Python desktop application combining a **PyQt5 Control Center** UI, a persistent **Flask OCR backend server**, and PyQt5-based **screen snipping and translation overlays**.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ app.py (root — PyQt5 Control Center)                │
│  - Sidebar navigation, dark theme                   │
│  - Language settings, color/alpha/font pickers      │
│  - Settings persistence (settings.json)             │
│  - Flask process manager + health status bar        │
│  - Global hotkey: Alt+Shift+M (RegisterHotKey)      │
├──────────────────┬──────────────────────────────────┤
│ Spawns           │                                  │
│ python/ocr_server │ Spawns                          │
│  - Flask REST     │ python/capture.py                │
│  - EasyOCR Reader │  - PyQt5 region selection        │
│    (persistent)   │  - Saves image1.png              │
│  - /ocr, /health  │  - DPI awareness at startup      │
└──────────────────┴── detector.py ──→ overlay.py ──→ ocr_server.py
                      │  - OpenVINO                   │  - Flask OCR
                      │    text detect                │  - EasyOCR
                      │  - Crop words to crops/       │  - Returns OCR
                      │  - Singleton                  │    JSON results
                      │                              │
                      └─ show_translations() ────────→
                           - Wait for Flask /health
                           - OCR via Flask POST
                           - Group: words → lines → paragraphs
                           - Translate paragraphs (parallel)
                           - OpenCV inpaint (remove source text)
                           - Render on single overlay window
                           - Show translucent QWidget
```

## Component Details

### 1. PyQt5 Control Center (`app.py`)
- **File**: `app.py` (root)
- Replaces the Electron frontend (index.html, main.js, renderer.js).
- Provides native UI for: source language selection (EasyOCR options 1-6), destination language selection (20+ languages), capture settings (fill color, opacity, line width), overlay settings (alpha, font size, text color).
- Manages Flask subprocess lifecycle via `subprocess.Popen`.
- Registers global hotkey via Windows API `RegisterHotKey` + `QAbstractNativeEventFilter`.
- Settings persisted to `settings.json` (gitignored).

### 2. Flask OCR Backend (`python/ocr_server.py`)
- Spawned by `app.py` with language option as CLI arg.
- EasyOCR `Reader` loaded **once** at startup and reused across all `/ocr` requests.
- Endpoints: `/health` (GET), `/ocr` (POST with folder_location).
- Returns JSON: `{ "x_min,x_max,y_min,y_max": "recognized text" }` per crop.
- Deletes processed crop images after OCR.

### 3. Screen Snipping (`python/capture.py`)
- PyQt5 transparent overlay for region selection.
- DPI awareness set at process start (`SetProcessDpiAwareness(2)`).
- Uses `QApplication.desktop()` for screen geometry (no pyautogui dependency).
- Saves screenshot to `python/image1.png`.
- Passes user settings (destination language, colors, alpha, font, text_color) to `detector.main()`.

### 4. Text Detection (`python/detector.py`)
- OpenVINO `horizontal-text-detection-0001` model for text region detection.
- Singleton: lazy-loaded once, reused across snips.
- Crops detected words to `python/crops/` folder as PNG files.
- Hand off to `overlay.show_translations()` with full image path.
- Cleans up `image1.png` and crops after overlay is shown.

### 5. Overlay Rendering (`python/overlay.py`)
- Single `OverlayWindow` (QWidget) covering the entire snipped region.
- Uses OpenCV for background reconstruction (text removal via `cv2.inpaint`).
- Draws translated text at source-relative coordinates.
- Font size estimated from median OCR bounding box height × 0.75.
- Paragraph-level translation (parallel via `ThreadPoolExecutor`).
- Key event handlers: Escape/Q for dismissal, click-to-dismiss.

### 6. Translation (`python/translator.py`)
- Tiered fallback: `googletrans` → `deep_translator.GoogleTranslator` → `deep_translator.MyMemoryTranslator`.
- Parallelized with `ThreadPoolExecutor` + `as_completed`.

## Data Flow

1. User presses `Alt+Shift+M` → global hotkey fires
2. `app.py` spawns `capture.py` subprocess with user settings as CLI args
3. `capture.py` shows PyQt5 selection overlay, user drags a region
4. On release: saves screenshot to `python/image1.png`, calls `detector.main()`
5. `detector.main()` → `TextDetector.detect()` → OpenVINO finds text boxes → crops saved to `python/crops/`
6. `detector.main()` → `overlay.show_translations(image_path=...)`
7. `show_translations()`:
   - Waits for Flask `/health`
   - POSTs crops folder → Flask runs EasyOCR → returns coordinates + text
   - Parses results: `_parse_ocr_results()` → `_group_words_into_lines()` → `_group_lines_into_paragraphs()`
   - Translates each paragraph in parallel via `ThreadPoolExecutor`
   - Loads `image1.png` into numpy array (BGR)
   - Creates `OverlayWindow` sized to snip region
   - `update_overlay()`: inpaint source text, draw translations at source positions
   - Calls `overlay.show()`
8. `detector.main()` → deletes `image1.png` and crops
9. Overlay window stays visible until dismissed (Escape/Q/click)

## Communication

- **app.py ↔ capture.py**: Subprocess spawn with CLI arguments (destination, fill_color, opacity, line_width, alpha, font_size, text_color)
- **capture.py ↔ detector.py**: Python import, `detector.main(image_path, x1, y1, ...)` called synchronously
- **overlay.py ↔ ocr_server.py**: HTTP POST to `http://localhost:5000/ocr` with folder location
- **overlay.py ↔ translator.py**: Python import, `translate_text(text, dest)` calls
- **app.py ↔ Flask**: HTTP GET to `http://localhost:5000/health` (status bar polling)

## Models & Weights

| Model | Location | Auto-download |
|---|---|---|
| EasyOCR language models | `python/EasyOCR/model/` | Yes (EasyOCR handles) |
| OpenVINO text detection | `python/models/horizontal-text-detection-0001.{xml,bin}` | No (download separately, see README) |

## Configuration

- **Settings**: `settings.json` (gitignored) — source language, dest language, colors, alpha, font size, text color
- **.gitignore**: venv, pycache, model weights, logs, crops, image1.png, settings.json, IDE files