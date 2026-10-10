# 🔍 LingoLens

**LingoLens** is a next-generation, high-performance desktop screen snipping, OCR, and real-time translation tool built in **Python** (PyQt5, Flask, EasyOCR, and OpenVINO). 

Originally developed with Electron, LingoLens has been fully refactored into a **pure Python application** featuring a sleek modern Control Center (dark/light themes), persistent background OCR server architecture, and native transparent screen overlay windows.

![LingoLens demo](assets/demo.gif)

*Real pipeline output: snip a region → OCR detects text → source text removed → translation rendered in place.*

---

## 🌟 Key Features

- **Native PyQt5 Control Center**: Minimal frameless glass window (Dark/Light themes) for source/destination languages, recent pairs, and one-click snipping — capture appearance lives in the in-window Settings page (gear button).
- **🌐 Expanded Global Language Support**: OCR in **12 languages** (English, Spanish, French, Italian, Portuguese, Vietnamese, German, Chinese, Japanese, Russian, Bengali, Korean); translate into **20 languages** (adds Hindi, Arabic, Urdu, Dutch, Turkish, Polish, Indonesian, Thai, and more).
- **🔄 Robust Multi-Service Fallback Translation**: Tiered fallback system (`deep_translator` Google → `deep_translator` MyMemory) for resilient online translation. `googletrans` is intentionally excluded: it is not in `requirements.txt` and its current PyPI release (4.0.2) is async-incompatible with this synchronous pipeline.
- **🧠 Persistent OCR Model Architecture**: Flask OCR backend runs locally, loading the heavy EasyOCR model **once** into memory upon startup to guarantee lightning-fast response times on every screen snip.
- **🪟 Transparent Screen Overlays**: Frameless, always-on-top PyQt5 overlay windows render translated text precisely at original screen coordinates. Source background is preserved via pixel-accurate inpainting (ring-median fill for flat backgrounds, single-pass inpaint for textured ones). `alpha` settings control the selection-tint overlay, not patches.
- **⌨️ Global Hotkeys**: Press `Alt+Shift+M` anywhere on your screen to instantly trigger screen capture and OCR translation.

---

## 💻 Platform Support

**Windows 10/11 x64 only.** The global hotkey hook is win32-only, screen capture is DPI-aware Windows, and install/run instructions below assume Windows. Other platforms are untested and unsupported.

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
│   ├── benchmark.py            # Per-stage pipeline timings
│   └── translator.py           # Multi-service fallback translation (deep_translator Google → MyMemory)
├── assets/
│   └── demo.gif                # Pipeline demo (built from a real debug dump)
├── run.py                      # Python launcher script
├── run.bat                     # Windows batch launcher
├── icon.png / logo.png         # App icons
└── LICENSE                     # GPL-3.0
```

---

## ⚙️ Model Weights & Setup

LingoLens relies on **EasyOCR** for text recognition and **OpenVINO** for text detection. Because model weight files are large, they are excluded from the git repository — **both** sets of weights are needed at runtime.

1. **EasyOCR Models**: EasyOCR will automatically download required language model weights (e.g., English, Chinese, Japanese, etc.) on first run when `download_enabled=True`. Alternatively, you can download pre-trained weights from the [EasyOCR GitHub Repository](https://github.com/JaidedAI/EasyOCR) and place them in `python/EasyOCR/model/`.
2. **OpenVINO Models**: Download the required text detection model weights (`.xml` and `.bin`) from the [OpenVINO Open Model Zoo](https://github.com/openvinotoolkit/open_model_zoo) and place them in `python/models/`:
   - `horizontal-text-detection-0001.xml` & `.bin`
   - `text-detection-0004.xml` & `.bin`

---

## 🚀 Installation & Quick Start

### 1. Prerequisites
- Python 3.10+ installed on your system (developed and tested on **3.13**).
- Note: `easyocr` pulls in PyTorch, so the first `pip install` downloads **multiple GB** — allow time and disk space.

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
3. Customize your selection box fill colour, opacity, and border width in Settings (gear button).
4. Press **`Alt+Shift+M`** (or click **Snip & Translate**), drag a box around any text on your screen, and watch the instant translation render in place!

The Flask OCR server starts automatically. On first run, EasyOCR downloads its model weights.

---

## 🐛 Debug Mode

Set `LINGOLENS_DEBUG=1` to write per-snip artifacts under `debug/<timestamp>/`:
`capture.png`, `boxes.png`, `blocks.png`, `removed.png`, `overlay_rgba.png`, `composite.png`, `detections.json`, `ocr.json`, `blocks.json`, `translations.json`, `metrics.json`, `timings.json`, and `env.json`. These are for diagnosing translation placement, background removal, and overlay issues. Add `LINGOLENS_DEBUG_OUTLINE=1` to draw a cyan outline around the snip region and magenta outlines around detected text blocks.

---

## 🧪 Testing

```bash
# Compile check
.venv/Scripts/python.exe -m py_compile app.py python/*.py ui/*.py
```

The headless unit suite and pipeline tools live under `python/tests/` and `python/tools/` — these are local development files and are not shipped in the public repo.

---

## 🛠 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Overlay is blank / nothing renders | Model weights missing | Complete both steps in Model Weights & Setup, then restart |
| `Alt+Shift+M` does nothing | Hotkey already taken by another app | Close or rebind the conflicting app, then restart LingoLens |
| First snip is very slow | EasyOCR downloading weights on first run | Wait for the download to finish; later snips are fast |
| Translation looks wrong / untranslated | Rate-limited or unreachable translation service | Retry the snip; the Google → MyMemory fallback needs network |

---

## 📄 License

LingoLens is released under the **GNU General Public License v3.0** — see [LICENSE](LICENSE) for details.

---

