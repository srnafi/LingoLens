# LingoLens Development Log

## Current Architecture (Pure Python, PyQt5)

```
app.py (root)
  ├── spawns ──→ python/ocr_server.py  (Flask OCR server, EasyOCR persistent Reader)
  └── spawns ──→ python/capture.py      (PyQt5 screen region selection)
                    │
                    └── detector.py     (OpenVINO text detection, crops words)
                          │
                          └── overlay.py (PyQt5 single-window overlay)
                                ├── Flask OCR (EasyOCR via HTTP POST)
                                ├── Word → Line → Paragraph grouping
                                ├── Paragraph-level translation (ThreadPoolExecutor, parallel)
                                ├── OpenCV inpainting (remove source text)
                                ├── Source-relative coordinate rendering
                                └── Single transparent overlay window
```

## Component Overview

| File | Responsibility |
|---|---|
| `app.py` | PyQt5 Control Center, process management, hotkeys, settings persistence |
| `python/capture.py` | PyQt5 full-screen region selection overlay, DPI-aware, saves snip to image1.png |
| `python/detector.py` | OpenVINO text detection (horizontal-text-detection-0001), singleton, crops words to `python/crops/` |
| `python/ocr_server.py` | Flask REST API on port 5000, EasyOCR Reader loaded once, `/ocr` + `/health` endpoints |
| `python/overlay.py` | Single PyQt5 overlay window, OpenCV inpainting, line/paragraph grouping, paragraph translation |
| `python/translator.py` | Tiered fallback: googletrans → deep_translator Google → MyMemory |
| `run.py` / `run.bat` | Virtualenv launcher (uses `.venv/Scripts/python.exe`) |
| `python/benchmark.py` | Pipeline timing benchmark, parallel speedup verification |

## Key Design Decisions

- **Single overlay window**: One `OverlayWindow` (QWidget) covers the entire snipped region. All translated text is drawn on a single canvas at image-relative coordinates.
- **Flask OCR retained**: EasyOCR Reader is expensive to load; keeping it as a persistent Flask process avoids repeated initialization.
- **Singleton OpenVINO model**: `_detector_instance` lazy-loaded once, reused across snips.
- **DPI awareness**: `SetProcessDpiAwareness(2)` called at process start in `capture.py` and `overlay.py` before any Qt/PIL imports.
- **Source-aware font sizing**: Estimated from median OCR bounding box height × 0.75.
- **Paragraph-level translation**: Words grouped into lines, lines into paragraphs, each paragraph translated as a complete unit for natural, contextually correct output.
- **Settings persistence**: `settings.json` (gitignored) stores user preferences.

## Testing

- `python/test_overlay.py` — 11 unit tests for OCR parsing, grouping, font estimation, bbox calculations (all passing).
- `python/test_pipeline.py` — 16 integration tests for the full pipeline with synthetic OCR data (all passing).
- `python/benchmark.py` — Timing benchmark verifying parallel translation speedup.
- `py_compile` passes for all 7 Python files.

## Bug Fixes (Current Session)

1. **Fixed `as_completed` import**: `from concurrent.futures import ThreadPoolExecutor, as_completed` — missing import caused `NameError` in `show_translations`.
2. **Fixed `font_size` type coercion**: CLI args arrive as strings; converted to `int`/`float` at entry points in `capture.py` and `overlay.py`.
3. **Fixed paragraph flattening in `translate_para`**: `for line in para for w in line` instead of `for w in para` (paragraphs are lists of lines, not lists of words).
4. **Fixed `setPalette` call**: `setPalette(Qt.black)` → `setPalette(QPalette(Qt.black))` (requires QPalette, not GlobalColor).
5. **Fixed `keyPressEvent` return**: Returns `True` to accept the event.
6. **Fixed `_reconstruct_background` mask**: Created mask with correct `shape[:2]` dimensions.
7. **Fixed `_DismissFilter` class**: Inherits `QObject` with `super().__init__()` for `installEventFilter` to work.
8. **Fixed `update_overlay` regions dict**: Added `width` and `height` keys used by `_reconstruct_background`.
9. **Fixed model path in `detector.py`**: Changed from relative `"models/..."` to absolute `str(_this_dir / "models" / "...")` — was the root cause of the overlay not appearing (model not found → FileNotFoundError → image deleted → pipeline broken).

## Runtime State

- **Working**: Flask OCR server startup, OpenVINO detection, EasyOCR recognition, paragraph grouping, parallel translation, overlay rendering (verified via unit + integration tests).
- **Not yet verified at runtime**: Full end-to-end snip → OCR → translate → overlay display on actual desktop (requires interactive GUI testing).

## Migration History

- Electron + Flask (JavaScript/Flask) → Pure Python (PyQt5/Flask) migration completed.
- All Electron artifacts removed (package.json, main.js, renderer.js, index.html, etc.).
- Large model weights excluded from git, auto-downloaded at runtime.

## Current Git Log (recent)

```
84e4ea9  Add integration tests for overlay pipeline
0d53694  Fix: _DismissFilter must inherit QObject for installEventFilter
cc43f16  Fix: KeyError in _reconstruct_background - add width/height to regions dict
fc7be72  Fix: setPalette needs QPalette, not GlobalColor
be327c1  Fix: pass image_path through pipeline to prevent deletion-before-use
6f4b043  Add _paragraph_bbox, fix unit tests for grouping algorithm
b76f5ee  Fix: paragraph text flattening in translate_para, update benchmark imports
618239f  Fix: add as_completed to concurrent.futures imports
3c04923  Replace Tk overlay with PyQt5 image compositing architecture
```