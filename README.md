# 🔍 LingoLens

**LingoLens** is a next-generation, high-performance desktop screen snipping, OCR, and real-time translation tool built in **Python** (PyQt5, Flask, EasyOCR, and OpenVINO). 

Originally developed with Electron, LingoLens has been fully refactored into a **pure Python application** featuring a sleek modern dark-themed Control Center, persistent background OCR server architecture, and native transparent screen overlay windows.

---

## 🌟 Key Features

- **Native PyQt5 Control Center**: Minimal frameless glass window (Aurora/Dusk/Daylight themes) for source/destination languages, recent pairs, and one-click snipping — capture appearance, overlay opacity, and font styling live in the in-window Settings page (gear button).
- **🌐 Expanded Global Language Support**: Supports OCR and translation across 20+ languages including English, Spanish, French, German, Italian, Portuguese, Russian, Vietnamese, Bengali, Hindi, Simplified Chinese, Japanese, Korean, Arabic, Urdu, Dutch, Turkish, Polish, Indonesian, and Thai.
- **🔄 Robust Multi-Service Fallback Translation**: Tiered fallback system (`deep_translator` Google → `deep_translator` MyMemory) ensures zero-failure offline/online translation resilience. `googletrans` is intentionally excluded: it is not in `requirements.txt` and its current PyPI release (4.0.2) is async-incompatible with this synchronous pipeline.
- **🧠 Persistent OCR Model Architecture**: Flask OCR backend runs locally, loading the heavy EasyOCR model **once** into memory upon startup to guarantee lightning-fast response times on every screen snip.
- **🪟 Transparent Screen Overlays**: Frameless, always-on-top PyQt5 overlay windows render translated text precisely at original screen coordinates. Source background is preserved via pixel-accurate inpainting (ring-median fill for flat backgrounds, single-pass inpaint for textured ones). `alpha` settings control the selection-tint overlay, not patches.
- **⌨️ Global Hotkeys**: Press `Alt+Shift+M` anywhere on your screen to instantly trigger screen capture and OCR translation.

---

## 📂 Project Architecture

```
LingoLens/
├── app.py                      # PyQt5 Control Center (Main UI & Process Manager)
├── ui/                         # Control Center UI: main_window, theme, prism_widgets,
│                               # backend (Flask/snip/hotkey), settings_store, languages,
│                               # dpi bootstrap, code-generated logo (logo.py)
├── python/
│   ├── ocr_server.py           # Persistent Flask OCR REST API server
│   ├── capture.py              # PyQt5 Screen Capture Widget (freeze-frame, DPI-aware)
│   ├── detector.py             # OpenVINO Text Detection & Cropping Engine
│   ├── blocks.py               # Word/Line/Block grouping, text joining (pure, headless)
│   ├── blend.py                # Background removal, colour fitting, RGBA overlay render (pure, headless)
│   ├── overlay.py              # OverlayWindow, registry, dismissal, show_translations()
│   ├── debug_dump.py           # Writes debug/<stamp>/ artifacts when LINGOLENS_DEBUG=1
│   └── translator.py           # Multi-service fallback translation (deep_translator Google → MyMemory)
├── run.py                      # Python launcher script
├── run.bat                     # Windows batch launcher
├── settings.json               # User settings (gitignored)
├── AGENTS.md                   # Agent instructions (local only)
├── docs/
│   ├── OVERLAY_SPEC.md         # Full design spec, algorithms, acceptance criteria
│   ├── PROGRESS.md             # Phase progress tracker
│   └── reference/
│       ├── blend_reference.py  # Tested reference of the blending core
│       └── qt_lifecycle_repro.py # Reproduces the "overlay never appears" bug
└── debug/                      # Rendered debug artifacts (gitignored, created at runtime)
```

---

## ⚙️ Model Weights & Setup

LingoLens relies on **EasyOCR** for text recognition and **OpenVINO** for text detection. Because model weight files are large, they are excluded from the git repository.

1. **EasyOCR Models**: EasyOCR will automatically download required language model weights (e.g., English, Chinese, Japanese, etc.) on first run when `download_enabled=True`. Alternatively, you can download pre-trained weights from the [EasyOCR GitHub Repository](https://github.com/JaidedAI/EasyOCR) and place them in `python/EasyOCR/model/`.
2. **OpenVINO Models**: Download the required text detection model weights (`.xml` and `.bin`) from the [OpenVINO Open Model Zoo](https://github.com/openvinotoolkit/open_model_zoo) and place them in `python/models/`:
   - `horizontal-text-detection-0001.xml` & `.bin`
   - `text-detection-0004.xml` & `.bin`

---

## 🚀 Installation & Quick Start

### 1. Prerequisites
- Python 3.10+ installed on your system.

### 2. Clone & Setup Virtual Environment
```bash
git clone https://github.com/srnafi/LingoLens.git
cd LingoLens
python -m venv .venv
```

### 3. Activate Virtual Environment & Install Dependencies
- **Windows (Git Bash / CMD / PowerShell)**:
  ```bash
  source .venv/Scripts/activate   # or .venv\Scripts\activate
  pip install -r python/requirements.txt
  ```

### 4. Run LingoLens
```bash
python run.py
```
*(Or simply double-click `run.bat` on Windows)*

---

## ⌨️ Usage
1. Open the LingoLens Control Center.
2. Select your **Source OCR Language** and **Destination Translation Language**.
3. Customize your selection box fill color, opacity, text color, and font size in Settings (gear button).
4. Press **`Alt+Shift+M`** (or click **Snip & Translate**), drag a box around any text on your screen, and watch the instant translation render in place!

The Flask OCR server starts automatically. On first run, EasyOCR downloads its model weights.

---

## 🐛 Debug Mode

Set `LINGOLENS_DEBUG=1` to write per-snip artifacts under `debug/<timestamp>/`:
`capture.png`, `boxes.png`, `blocks.png`, `removed.png`, `overlay_rgba.png`, `composite.png`, `metrics.json`, `timings.json`, and `env.json`. These are for diagnosing translation placement, background removal, and overlay issues. Add `LINGOLENS_DEBUG_OUTLINE=1` to draw a cyan outline around the snip region and magenta outlines around detected text blocks.

---

## 🧪 Testing

```bash
# Compile check
.venv/Scripts/python.exe -m py_compile app.py python/*.py

# Headless test suite (QT_QPA_PLATFORM=offscreen)
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python -q

# Reference blend acceptance table
.venv/Scripts/python.exe docs/reference/blend_reference.py

# Replay a real debug dump offline
.venv/Scripts/python.exe python/tools/replay.py debug/<timestamp>
```

Tests live under `python/tests/` and `python/` (local only, not committed). See `docs/OVERLAY_SPEC.md` for full acceptances and `docs/PROGRESS.md` for the phase-by-phase status.

---

