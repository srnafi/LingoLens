# LingoLens Development & Recovery Log

## Architecture (Pure Python)

- **`app.py`** — PyQt5 Control Center: dark theme, sidebar navigation, settings pages, Flask process manager
- **`python/capture.py`** — PyQt5 full-screen overlay for screen region selection
- **`python/detector.py`** — OpenVINO text detection (horizontal-text-detection-0001), singleton lazy-loaded, crops detected words
- **`python/ocr_server.py`** — Flask REST API with EasyOCR, persistent Reader loaded once at startup
- **`python/overlay.py`** — Single-window overlay: groups words → lines → paragraphs, translates paragraphs with context, renders all translated text on ONE transparent canvas
- **`python/translator.py`** — Tiered fallback: googletrans → deep_translator Google → MyMemory
- **`run.py` / `run.bat`** — Virtual environment launcher

## Pipeline Flow

```
app.py → (subprocess) capture.py → detector.py → overlay.py → ocr_server.py (Flask)
                screenshot    OpenVINO detect    EasyOCR via Flask
                              + crop words        + group into lines/paragraphs
                                                  + translate paragraphs
                                                  + render on single canvas
```

## Key Design: Single-Window Overlay

The overlay architecture creates ONE transparent window covering the entire
snipped region. All translated text is drawn on a single canvas at
image-relative coordinates — no coordinate conversion per text item.

Pipeline:
1. User snips a screen region
2. OpenVINO detects text bounding boxes in the captured image
3. Each word crop is sent to EasyOCR via Flask
4. **Words are grouped into lines** (vertical center proximity, 50% threshold)
5. **Lines are grouped into paragraphs** (gap < 1.2x line height)
6. **Each paragraph is translated as a complete unit** — giving the translation
   engine full context for natural, grammatically correct output
7. **Font size is estimated** from median OCR bounding box height
8. **Adaptive text fitting** — scales down if translation exceeds source width
9. **Text outline** for visibility over arbitrary backgrounds
10. All rendered on ONE canvas inside a single transparent overlay window

Coordinate system:
- Overlay window positioned at snip's top-left + screen offset
- All text drawn at image-relative coordinates (no per-item conversion)
- Every OCR result traceable to its original position in the snipped region

## Key Architectural Decisions

- **Single overlay window**: one Toplevel for entire snip, not N windows per line
- **Flask retained** for OCR persistence: EasyOCR Reader loaded once at startup
- **Singleton OpenVINO model**: lazy-loaded once, reused across snips
- **Shared Tk root**: text measurement uses one hidden Tk root
- **Settings persistence**: saved to `settings.json`, restored on launch
- **Global hotkey**: `Alt+Shift+M` via Windows API
- **DPI awareness**: SetProcessDpiAwareness(2) called at process start (capture.py) before any Qt/PIL
- **Source-aware font sizing**: estimated from OCR geometry, adapts to source text scale

## Bug Fixes (session)

- Fixed `capture.py` globals crash (r,g,b,op,lw used before assignment)
- Fixed `ocr_server.py` double EasyOCR Reader initialization
- Fixed missing `text_color` passthrough from UI to overlay
- Added Flask `/health` endpoint and readiness check
- Added Escape/Q to dismiss translation overlays
- Added error handling for missing OpenVINO models
- Fixed DPI awareness timing — moved to process start
- Removed stale files: `app_main.py`, `width.py`

## Migration History

- Electron → Pure Python (PyQt5) migration completed
- All Electron artifacts removed
- Repository cleaned: large model weights excluded from git
