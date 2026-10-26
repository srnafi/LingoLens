"""settings.json persistence — stdlib only, headless-testable.

Single source of truth for user preferences. The window and the Settings
dialog both read/write :attr:`SettingsStore.settings`; there is no second
copy of this state anywhere in the UI layer.
"""
import json
from dataclasses import asdict, dataclass, field

from ui import languages

# Choose the text-recognition backend. "easyocr" is the original pipeline
# (OpenVINO detector + EasyOCR on Flask); "ppocr" is the optional PP-OCRv6
# detector + recogniser in python/ppocr.py. Keep ids stable - they are persisted.
OCR_ENGINES = (
    ("easyocr", "EasyOCR"),
    ("ppocr", "PP-OCRv6"),
)
OCR_ENGINE_IDS = {key for key, _label in OCR_ENGINES}
DEFAULT_OCR_ENGINE = "easyocr"


@dataclass
class Settings:
    source_lang_option: int = 1
    source_lang_name: str = "English"
    dest_lang: str = "en"
    dest_lang_name: str = "English"
    fill_color: str = "#ff0000"
    text_color: str = "#000000"
    opacity: float = 0.3
    line_width: int = 3
    alpha: float = 0.7
    font_size: int = 12
    recent_pairs: list = field(default_factory=list)
    theme: str = "aurora"  # Prism theme name; see ui.theme.THEME_ORDER
    ocr_engine: str = DEFAULT_OCR_ENGINE  # see OCR_ENGINES above


# Settings written before the rename; migrate instead of resetting the choice.
_ENGINE_ALIASES = {"lingolens": "easyocr", "overtranslate": "ppocr"}


def _canonical_engine(value):
    """Map legacy ids onto the current ones, unknown values onto the default."""
    if not isinstance(value, str):
        return DEFAULT_OCR_ENGINE
    value = _ENGINE_ALIASES.get(value.strip().lower(), value.strip().lower())
    return value if value in OCR_ENGINE_IDS else DEFAULT_OCR_ENGINE


class SettingsStore:
    def __init__(self, path):
        self.path = path
        self.settings = Settings()

    def save(self):
        """Persist current preferences to disk."""
        try:
            with open(self.path, "w") as f:
                json.dump(asdict(self.settings), f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def load(self):
        """Load preferences from disk; unknown/missing keys keep defaults."""
        if not self.path.exists():
            return self.settings
        try:
            with open(self.path, "r") as f:
                raw = json.load(f)
            s = self.settings
            s.source_lang_option = raw.get("source_lang_option", 1)
            s.source_lang_name = raw.get("source_lang_name", "English")
            s.dest_lang = raw.get("dest_lang", "en")
            s.dest_lang_name = raw.get("dest_lang_name", "English")
            s.fill_color = raw.get("fill_color", "#ff0000")
            s.text_color = raw.get("text_color", "#000000")
            s.opacity = raw.get("opacity", 0.3)
            s.line_width = raw.get("line_width", 3)
            s.alpha = raw.get("alpha", 0.7)
            s.font_size = raw.get("font_size", 12)
            s.recent_pairs = languages.sanitize_recents(
                raw.get("recent_pairs", []))
            theme = raw.get("theme", "aurora")
            s.theme = theme if isinstance(theme, str) and theme else "aurora"
            engine = _canonical_engine(raw.get("ocr_engine", DEFAULT_OCR_ENGINE))
            s.ocr_engine = engine
            # Canonicalize against the language tables (survives renames).
            from_idx = languages.find_from_index(
                s.source_lang_name, s.source_lang_option)
            to_idx = languages.find_to_index(s.dest_lang)
            s.source_lang_name = languages.FROM_LANGS[from_idx][0]
            s.source_lang_option = languages.FROM_LANGS[from_idx][1]
            s.dest_lang = languages.TO_LANGS[to_idx][1]
            s.dest_lang_name = languages.TO_LANGS[to_idx][0]
            print(f"Settings loaded from {self.path}")
        except Exception as e:
            print(f"Failed to load settings: {e}")
        return self.settings

    def reset(self):
        """Restore factory defaults. Recent pairs are kept (history, not config)."""
        recents = self.settings.recent_pairs
        self.settings = Settings()
        self.settings.recent_pairs = recents
        self.save()
        print("Settings reset to defaults")
