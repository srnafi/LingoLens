# 🔍 LingoLens

**LingoLens** is a next-generation, high-performance desktop screen snipping, OCR, and real-time translation tool built in **Python** (PyQt5, Flask, EasyOCR, and OpenVINO). 

Originally developed with Electron, LingoLens has been fully refactored into a **pure Python application** featuring a sleek modern dark-themed Control Center, persistent background OCR server architecture, and native transparent screen overlay windows.

---

## 🌟 Key Features

- **⚡ Native PyQt5 Control Center**: Modern dark-themed dashboard (Catppuccin Mocha aesthetic) for complete control over source/destination languages, capture window appearance, overlay opacity, and font styling.
- **🌐 Expanded Global Language Support**: Supports OCR and translation across 20+ languages including English, Spanish, French, German, Italian, Portuguese, Russian, Vietnamese, Bengali, Hindi, Simplified Chinese, Japanese, Korean, Arabic, Urdu, Dutch, Turkish, Polish, Indonesian, and Thai.
- **🔄 Robust Multi-Service Fallback Translation**: Tiered fallback system (`googletrans` → `deep_translator` Google → `deep_translator` MyMemory) ensures zero-failure offline/online translation resilience.
- **🧠 Persistent OCR Model Architecture**: Flask OCR backend runs locally, loading the heavy EasyOCR model **once** into memory upon startup to guarantee lightning-fast response times on every screen snip.
- **🪟 Transparent Screen Overlays**: Frameless, always-on-top PyQt5 and Tkinter overlay windows render translated text precisely at original screen coordinates with customizable box fill, border width, text color, and background alpha transparency.
- **⌨️ Global Hotkeys**: Press `Alt+Shift+M` anywhere on your screen to instantly trigger screen capture and OCR translation.

---

## 📂 Project Architecture

```
LingoLens/
├── lingolens_control_center.py # PyQt5 Control Center (Main UI & Process Manager)
├── python/
│   ├── eocr_server.py          # Persistent Flask OCR REST API server
│   ├── screen_snipper.py       # PyQt5 Screen Snipping & Overlay Widget
│   ├── text_detector_text.py   # OpenVINO Text Detection & Cropping Engine
│   ├── text_displayer.py       # Multi-threaded Translation & Tkinter Overlay Renderer
│   └── translate.py            # Multi-service fallback translation module
├── run.py                      # Python launcher script
├── run.bat                     # Windows batch launcher
├── ARCHITECTURE.md             # Technical architecture documentation
├── DEVELOPMENT_LOG.md          # Development recovery & migration log
└── MIGRATION_PLAN.md           # Electron-to-Python migration plan
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
3. Customize your selection box fill color, opacity, text color, and font size in the settings tabs.
4. Press **`Alt+Shift+M`** (or click **⚡ Snip & Translate Now**), drag a box around any text on your screen, and watch the instant translation render in place!

---

## 📄 License
MIT License
