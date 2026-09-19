# LingoLens Development & Recovery Log

## Architecture (Pure Python)

- **UI**: `lingolens_control_center.py` — PyQt5 Control Center with dark theme, sidebar navigation, 3 settings pages
- **Screen Capture**: `python/screen_snipper.py` — PyQt5 full-screen overlay for region selection
- **Text Detection**: `python/text_detector_text.py` — OpenVINO horizontal-text-detection-0001 model, singleton lazy-loaded
- **OCR Server**: `python/eocr_server.py` — Flask REST API with EasyOCR, persistent Reader loaded once at startup
- **Translation Display**: `python/text_displayer.py` — Multi-threaded translation + Tkinter overlay windows
- **Translation Engine**: `python/translate.py` — Tiered fallback: googletrans → deep_translator Google → MyMemory
- **Launcher**: `run.py` / `run.bat` — Virtual environment activation + app launch

## Key Architectural Decisions

- **Flask retained** for OCR persistence: EasyOCR Reader loaded once at startup, reused across all requests
- **Singleton OpenVINO model**: TextDetector lazy-loaded once, reused across snips (previously reloaded every time)
- **Shared Tk root**: Text width measurement uses a single hidden Tk root instead of creating/destroying per word
- **Settings persistence**: User preferences saved to `settings.json`, restored on launch
- **Global hotkey**: `Alt+Shift+M` via Windows API `RegisterHotKey` + `QAbstractNativeEventFilter`

## Bug Fixes

- Fixed `screen_snipper.py` module-global crash (r,g,b,op,lw used before assignment)
- Fixed `eocr_server.py` double EasyOCR Reader initialization (wasted ~30s startup)
- Fixed missing `text_color` passthrough from UI to overlay
- Added Flask `/health` endpoint and readiness check before OCR requests
- Added Escape/Q key to dismiss translation overlays
- Removed stale `python/app_main.py` and unused `python/width.py`
- Added error handling for Flask being down, OCR failures, translation failures

## Migration History

- Electron → Pure Python (PyQt5) migration completed
- All Electron artifacts removed (main.js, renderer.js, index.html, package.json, node_modules/)
- Repository cleaned: large model weights excluded from git, comprehensive .gitignore
