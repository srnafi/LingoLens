"""Main window — LingoLens Control Center built on ui_kit.

FramelessWindow shell + kit parts only (SnipButton hero CTA, Pill
status, QComboBox pair, chip Buttons, IconButtons). Owns NO state:
languages from ui.languages, prefs from SettingsStore, processes
from Backend. The window is a view.
"""
import sys

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QShortcut,
                             QVBoxLayout, QWidget)

from ui import ROOT, languages
from ui.backend import Backend, register_hotkey, unregister_hotkey
from ui.settings_dialog import open_settings
from ui.settings_store import SettingsStore
from ui.ui_kit import (TOKENS, Button, FramelessWindow, IconButton, LogoMark,
                       Pill, apply_theme, caption, enable_hidpi, icon,
                       lint, polish_combo, snapshot)

HEALTH = {  # backend state -> (pill text, pill state)
    "ready": ("OCR ready", "ok"),
    "starting": ("OCR starting", "busy"),
    "offline": ("OCR offline - retry", "error"),
}


class StatusPill(Pill):
    """Kit Pill that emits clicked (re-check / restart the OCR server)."""

    clicked = pyqtSignal()

    def __init__(self, text="", state="ok", parent=None):
        super().__init__(text, state, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("OCR engine status - click to re-check / restart")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class SnipButton(QPushButton):
    """Big primary call-to-action: [camera] Snip & Translate [Alt][Shift][M]."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("variant", "primary")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(60)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(10)
        lay.addStretch()
        ic = QLabel()
        ic.setPixmap(icon("camera", "#ffffff", 20).pixmap(20, 20))
        lay.addWidget(ic)
        txt = QLabel("Snip & Translate")
        txt.setStyleSheet("font-size: 15px; font-weight: 700; color: white;")
        lay.addWidget(txt)
        lay.addSpacing(10)
        for k in ("Alt", "Shift", "M"):
            cap = QLabel(k, objectName="Keycap")
            cap.setFixedHeight(22)
            lay.addWidget(cap, 0, Qt.AlignVCenter)
        lay.addStretch()
        for w in self.findChildren(QLabel):          # clicks go to the button
            w.setAttribute(Qt.WA_TransparentForMouseEvents)


class LingoLensControlCenter(FramelessWindow):
    def __init__(self):
        # ---- header: logo + brand + status pill, gear action -------------
        brand = QWidget()
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        _logo = ROOT / "logo.png"
        if _logo.exists():
            _pm = QPixmap(str(_logo)).scaled(
                36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            _logo_lbl = QLabel()
            _logo_lbl.setPixmap(_pm)
            bl.addWidget(_logo_lbl)
        else:
            bl.addWidget(LogoMark(36))
        bl.addWidget(QLabel(f'Lingo <span style="color:{TOKENS["teal"]}">Lens</span>',
                            objectName="Brand"))
        bl.addSpacing(6)
        pill = StatusPill("OCR starting", "busy")
        bl.addWidget(pill)
        gear = IconButton("settings", tooltip="Settings")

        super().__init__("LingoLens", width=470, minimize=True,
                         header=brand, actions=[gear])
        self.pill = pill
        self.store = SettingsStore(ROOT / "settings.json")
        self.backend = Backend(ROOT, on_health=self._set_status)
        self.nativeEventFilter = None

        gear.clicked.connect(self.open_settings)
        self.pill.clicked.connect(self._on_status_clicked)

        # ---- primary action ------------------------------------------------
        self.snip = SnipButton()
        self.snip.clicked.connect(self.trigger_snip)
        self.body.addWidget(self.snip)
        QShortcut(QKeySequence("Alt+Shift+M"), self,
                  activated=self.trigger_snip)

        # ---- languages ------------------------------------------------------
        self.src = self._combo([n for n, _o in languages.FROM_LANGS])
        self.dst = self._combo([n for n, _c in languages.TO_LANGS])
        self.src.currentIndexChanged.connect(self._on_from_changed)
        self.dst.currentIndexChanged.connect(self._on_to_changed)
        swap = QPushButton(objectName="SwapBtn")
        swap.setIcon(icon("swap", TOKENS["text_dim"], 18))
        swap.setFixedSize(44, 44)
        swap.setCursor(Qt.PointingHandCursor)
        swap.setToolTip("Swap languages")
        swap.clicked.connect(self._swap_languages)
        self.swap = swap

        row = QHBoxLayout()
        row.setSpacing(10)
        for label, combo, first in (("From", self.src, True),
                                    ("To", self.dst, False)):
            col = QVBoxLayout()
            col.setSpacing(6)
            col.addWidget(caption(label))
            col.addWidget(combo)
            row.addLayout(col, 1)
            if first:
                sw = QVBoxLayout()
                sw.setSpacing(6)
                spacer = caption("From")               # invisible alignment row
                spacer.setStyleSheet("color: transparent;")
                sw.addWidget(spacer)
                sw.addWidget(swap)
                row.addLayout(sw)
        self.body.addLayout(row)

        # ---- recent pairs ----------------------------------------------------
        self.recent_row = QHBoxLayout()
        self.recent_row.setSpacing(8)
        self.recents_wrap = QWidget()
        self.recents_wrap.setLayout(self.recent_row)
        self.body.addWidget(self.recents_wrap)

        # ---- boot -------------------------------------------------------------
        self.store.load()
        self._reflect_settings()
        self.backend.start_flask_server(
            self.store.settings.source_lang_option)
        self.nativeEventFilter = register_hotkey(self.trigger_snip)

    # ---------------------------------------------------------------- helpers
    def _combo(self, names):
        c = QComboBox()
        c.addItems(names)
        return polish_combo(c)

    def _reflect_settings(self):
        """Push stored prefs into the combos without firing handlers."""
        s = self.store.settings
        from_idx = languages.find_from_index(
            s.source_lang_name, s.source_lang_option)
        to_idx = languages.find_to_index(s.dest_lang)
        self.src.blockSignals(True)
        self.src.setCurrentIndex(from_idx)
        self.src.blockSignals(False)
        self.dst.blockSignals(True)
        self.dst.setCurrentIndex(to_idx)
        self.dst.blockSignals(False)
        s.source_lang_name = languages.FROM_LANGS[from_idx][0]
        s.source_lang_option = languages.FROM_LANGS[from_idx][1]
        s.dest_lang = languages.TO_LANGS[to_idx][1]
        s.dest_lang_name = languages.TO_LANGS[to_idx][0]
        self._update_swap_state()
        self._refresh_recent_chips()

    def _reset_to_defaults(self):
        self.store.reset()  # keeps recent pairs (history, not config)
        self._reflect_settings()

    # ------------------------------------------------------------- languages
    def _on_from_changed(self, idx):
        name, opt = languages.FROM_LANGS[idx]
        s = self.store.settings
        option_changed = (opt != s.source_lang_option)
        s.source_lang_name = name
        s.source_lang_option = opt
        self.store.save()
        # Languages sharing one model bundle need no server restart.
        if option_changed:
            self.backend.restart_flask_server(opt)
        else:
            print(f"Source language updated: {name} (same OCR model, no restart)")
        self._update_swap_state()

    def _on_to_changed(self, idx):
        name, code = languages.TO_LANGS[idx]
        s = self.store.settings
        s.dest_lang_name = name
        s.dest_lang = code
        print(f"Destination language updated: {name}")
        self.store.save()
        self._update_swap_state()

    def _update_swap_state(self):
        s = self.store.settings
        ok = languages.is_swappable(s.source_lang_name, s.dest_lang_name)
        self.swap.setEnabled(ok)
        if ok:
            self.swap.setToolTip("Swap languages")
        else:
            self.swap.setToolTip(
                f"No OCR model for '{s.dest_lang_name}' - can't swap")

    def _swap_languages(self):
        s = self.store.settings
        from_name = s.source_lang_name
        to_name = languages.TO_LANGS[self.dst.currentIndex()][0]
        if not languages.is_swappable(from_name, to_name):
            return
        new_from = 0
        for i, (n, _o) in enumerate(languages.FROM_LANGS):
            if languages.base_name(n) == languages.base_name(to_name):
                new_from = i
                break
        new_to = languages.find_to_index(
            next(c for n, c in languages.TO_LANGS
                 if languages.base_name(n) == languages.base_name(from_name)))
        self.src.setCurrentIndex(new_from)  # fires handler
        self.dst.setCurrentIndex(new_to)    # fires handler

    # ---------------------------------------------------------------- recents
    def _push_recent(self):
        s = self.store.settings
        entry = {"from": s.source_lang_name, "to": s.dest_lang}
        s.recent_pairs = [e for e in s.recent_pairs if e != entry]
        s.recent_pairs.insert(0, entry)
        s.recent_pairs = s.recent_pairs[:languages.MAX_RECENTS]
        self.store.save()
        self._refresh_recent_chips()

    def _refresh_recent_chips(self):
        while self.recent_row.count():
            item = self.recent_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.recent_row.addWidget(caption("Recent"))
        self.recent_row.addSpacing(6)
        for entry in self.store.settings.recent_pairs:
            from_short = languages.FROM_SHORT[
                languages.find_from_index(entry["from"], 1)]
            to_short = entry["to"].split("-")[0].upper()
            chip = Button(f"{from_short} → {to_short}", "chip")
            chip.setToolTip(f"{entry['from']} → "
                            f"{languages.to_display_name(entry['to'])}")
            chip.clicked.connect(
                lambda _c, e=dict(entry): self._apply_recent(e))
            self.recent_row.addWidget(chip)
        self.recent_row.addStretch()
        self.recents_wrap.setVisible(bool(self.store.settings.recent_pairs))

    def _apply_recent(self, entry):
        s = self.store.settings
        self.src.setCurrentIndex(
            languages.find_from_index(entry["from"], s.source_lang_option))
        self.dst.setCurrentIndex(
            languages.find_to_index(entry["to"]))

    # ------------------------------------------------------------------ status
    def _set_status(self, state):
        text, pill_state = HEALTH.get(state, HEALTH["starting"])
        self.pill.setState(text, pill_state)

    def _on_status_clicked(self):
        """Manual re-check; restart the server if it is down."""
        if self.backend.recheck_health() == "restart":
            self.backend.restart_flask_server(
                self.store.settings.source_lang_option)

    # ------------------------------------------------------------ settings ++
    def open_settings(self):
        """All appearance knobs live in the dialog."""
        def on_change(kind):
            if kind == "appearance":
                self._reset_to_defaults()
                self.backend.restart_flask_server(
                    self.store.settings.source_lang_option)

        open_settings(self.store, on_change, self)

    def trigger_snip(self):
        self._push_recent()
        s = self.store.settings
        err = self.backend.launch_snip(
            s.dest_lang, s.fill_color, s.opacity, s.line_width,
            s.alpha, s.font_size, s.text_color)
        if err:
            QMessageBox.warning(
                self, "Warning",
                f"Failed to launch screen snipper script: {err}")

    def closeEvent(self, a0):
        self.backend.stop()
        unregister_hotkey()
        a0.accept()


if __name__ == "__main__":  # headless check: QT_QPA_PLATFORM=offscreen
    from ui.backend import Backend as _Backend

    _Backend.start_flask_server = lambda self, opt: None
    enable_hidpi()
    _app = QApplication(sys.argv)
    apply_theme(_app)
    _win = LingoLensControlCenter()
    import os as _os
    _out = _os.environ.get("LINGOLENS_SNAP",
                           "C:/Users/sezar/AppData/Local/hermes/profiles"
                           "/lingolens-dev/cache/scratch/kit_main.png")
    print(snapshot(_win, _out))
    print("lint:", lint(_win))
