# Migration Plan: Electron to Pure Python (Pure Python Version

## Status: Completed — Pure Python

LingoLens has been fully migrated from an Electron + JavaScript application
to a pure Python desktop application using PyQt5. All Electron artifacts
have been removed. The application is now: app.py (PyQt5 Control Center) →
capture.py (PyQt5 screen snipping) → detector.py (OpenVINO text detection)
→ overlay.py (PyQt5 overlay compositing) ↔ ocr_server.py (Flask OCR with
EasyOCR).

## Migration Steps Executed

1. **Replaced Electron frontend**: All HTML/JS/CSS files (index.html,
   main.js, renderer.js, shortcut.js, config.js, styles.css, output.css,
   tailwind.config.js, electron-builder.json, electron.zip) replaced by
   `app.py` — a PyQt5 application with sidebar navigation, dark theme,
   sliders, color pickers, and settings persistence.

2. **Preserved Flask OCR server**: Retained Flask + EasyOCR with persistent
   Reader (loaded once at startup). The `/ocr` and `/health` endpoints remain
   unchanged in API contract.

3. **Replaced Tkinter/Tk snip with PyQt5**: The old `snip0.py` (Tkinter-based
   region selection) was rewritten as `capture.py` using PyQt5
   `FramelessWindowHint | WindowStaysOnTopHint` with native cursor handling.
   DPI awareness (`SetProcessDpiAwareness(2)`) is applied at process start
   before Qt/PIL imports to ensure coordinate consistency.

4. **Replaced Tkinter overlay with PyQt5 compositing**: The old
   `text_displayer.py` (Tkinter Toplevel overlays, one window per word) was
   rewritten as `overlay.py` — a single PyQt5 `QWidget` overlay with OpenCV
   inpainting for background reconstruction, paragraph-level translation,
   and source-relative coordinate rendering.

5. **Removed Electron artifacts**: All package.json, node_modules, main.js,
   renderer.js, and HTML/CSS files deleted. No Electron dependencies remain.

6. **Renamed files for clarity**:
   - `eocr_server.py` → `ocr_server.py`
   - `text_detector_text.py` → `detector.py`
   - `text_displayer.py` → `overlay.py`
   - `translate.py` → `translator.py`
   - `snip0.py` → `capture.py`
   - `lingolens_control_center.py` → `app.py` (moved to root)

7. **Removed stale code**: Deleted `app_main.py`, `width.py`, `backupeocr.py`
   — all obsolete.

8. **Added .gitignore**: Comprehensive exclusions for venv, pycache, model
   weights (*.pth, *.bin, *.xml), logs, crops, image1.png, settings.json,
   IDE files, and build artifacts.

9. **Purged large model weights from git history**: Used orphaned clean
   branch + force push to remove bengali.pth and craft_mlt_25k.pth (>100MB).

## Current Runtime

- Launch via `python run.py` or `run.bat` (uses `.venv/Scripts/python.exe`)
- Hotkey: `Alt+Shift+M`
- Flask: `http://localhost:5000` (OCR) + `/health`
- Models: `python/models/` (OpenVINO), `python/EasyOCR/model/` (EasyOCR)

## Lessons Learned

- PyQt5's `setPalette()` requires a `QPalette` object, not `GlobalColor`.
- OpenCV `inpaint()` mask must match the image's 2D shape, not 3D.
- `installEventFilter` requires the filter to inherit `QObject`.
- OpenVINO model paths must be absolute (relative paths break when CWD differs).
- CLI arguments arrive as strings — must convert to int/float at entry points.
- `concurrent.futures.as_completed` must be explicitly imported from
  `concurrent.futures` (not available as bare name).
- Image files used by overlay must not be deleted before overlay loading completes.
- PyQt5 event filters and event handlers must `return True/False` explicitly.

## Future Considerations

- Consider QThread-based OCR instead of Flask HTTP for lower latency.
- Consider PySide6 as alternative to PyQt5 (same API, different licensing).
- Add real end-to-end GUI test for overlay visibility verification.