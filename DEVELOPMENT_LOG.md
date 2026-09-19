# LingoLens Development & Recovery Log

## Architecture (Pure Python)

- **`app.py`** — PyQt5 Control Center: dark theme, sidebar navigation, settings pages, Flask process manager
- **`python/capture.py`** — PyQt5 full-screen overlay for screen region selection
- **`python/detector.py`** — OpenVINO text detection (horizontal-text-detection-0001), singleton lazy-loaded, crops detected words
- **`python/ocr_server.py`** — Flask REST API with EasyOCR, persistent Reader loaded once at startup
- **`python/overlay.py`** — Groups OCR words into lines → paragraphs, translates each paragraph as a unit, displays overlays
- **`python/translator.py`** — Tiered fallback: googletrans → deep_translator Google → MyMemory
- **`run.py` / `run.bat`** — Virtual environment launcher

## Pipeline Flow

```
app.py → (subprocess) capture.py → detector.py → overlay.py → ocr_server.py (Flask)
                screenshot    OpenVINO detect    EasyOCR via Flask
                              + crop words        + group into paragraphs
                                                  + translate full paragraphs
                                                  + display overlays
```

## Key Design: Paragraph-Level Translation

Instead of translating each OCR word individually (which loses context and
produces unnatural output), LingoLens:

1. Detects text regions with OpenVINO
2. Crops each word and sends to EasyOCR via Flask
3. **Groups words into lines** by vertical proximity (words with overlapping Y ranges)
4. **Groups lines into paragraphs** by vertical spacing (gaps < 1.5x line height)
5. **Translates each paragraph as a complete text unit** — giving the translation
   engine full context for natural, grammatically correct output
6. Displays one overlay per paragraph with word-wrapping

## Key Architectural Decisions

- **Flask retained** for OCR persistence: EasyOCR Reader loaded once at startup
- **Singleton OpenVINO model**: lazy-loaded once, reused across snips
- **Shared Tk root**: text measurement uses one hidden Tk root
- **Settings persistence**: saved to `settings.json`, restored on launch
- **Global hotkey**: `Alt+Shift+M` via Windows API

## Bug Fixes (session)

- Fixed `capture.py` globals crash (r,g,b,op,lw used before assignment)
- Fixed `ocr_server.py` double EasyOCR Reader initialization
- Fixed missing `text_color` passthrough from UI to overlay
- Added Flask `/health` endpoint and readiness check
- Added Escape/Q to dismiss translation overlays
- Added error handling for missing OpenVINO models
- Removed stale files: `app_main.py`, `width.py`

## Migration History

- Electron → Pure Python (PyQt5) migration completed
- All Electron artifacts removed
- Repository cleaned: large model weights excluded from git
