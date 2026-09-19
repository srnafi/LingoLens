# LingoLens Architecture (Pure Python Version)

## Overview
LingoLens is now a pure Python desktop application combining a **PyQt5 Control Center** UI, a persistent **Flask OCR backend server**, and **PyQt5/Tkinter screen snipping and translation overlays**.

## Architecture Components

### 1. PyQt5 Control Center (`app_main.py`)
- Replaces the Electron frontend (`index.html`, `main.js`, `renderer.js`).
- Provides native UI controls for:
  - Source Language selection (mapping to EasyOCR language reader options 1–6).
  - Destination Language selection (`en`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `vi`, `bn`).
  - Capture window settings (Fill color, opacity, line width).
  - Overlay & Font settings (Window alpha, font size).
- Manages lifecycle of background processes (Flask OCR server and snipping tool).
- Registers global hotkeys (`Alt+Shift+M`) via native Windows API (`RegisterHotKey`).

### 2. Persistent Flask OCR Backend (`python/eocr_server.py`)
- Spawned by `app_main.py` on startup.
- Loads the EasyOCR model **once** into memory upon startup based on the selected source language option and reuses it across recognition requests.
- Exposes REST API endpoint `/ocr` (POST) accepting image folder locations and returning detected text coordinates and strings.

### 3. Screen Snipping & Translation Overlays (`python/snip0.py`, `python/text_detector_text.py`, `python/text_displayer.py`)
- Triggered via global hotkey (`Alt+Shift+M`) or Control Center button.
- PyQt5 transparent overlay enables region selection.
- OpenVINO text detector (`horizontal-text-detection-0001`) detects text boxes, crops words/lines.
- OCR processed via Flask server and EasyOCR.
- Translations generated via `deep_translator` and rendered via transparent Tkinter `tk.Toplevel` overlay windows at exact screen coordinates.
