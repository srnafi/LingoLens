"""settings.json persistence — stdlib only, headless-testable.

Single source of truth for user preferences. The window and the Settings
dialog both read/write :attr:`SettingsStore.settings`; there is no second
copy of this state anywhere in the UI layer.
"""
import json
from dataclasses import asdict, dataclass, field

from ui import languages


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
