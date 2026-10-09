"""Main window — frameless rounded Control Center (action only).

Owns NO state of its own: languages come from ui.languages, preferences
from SettingsStore, processes from Backend. The window is a view —
it reads the store, writes the store, and tells the backend what to do.
"""
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from ui import ROOT, icons, languages
from ui.backend import Backend, register_hotkey, unregister_hotkey
from ui.settings_dialog import open_settings
from ui.settings_store import SettingsStore
from ui.theme import STATUS_STYLE


class LingoLensControlCenter(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # Frameless + translucent: rounded outer corners and a dark custom
        # titlebar. (Native Win32 chrome is square and light — the old look.)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("LingoLens")
        self._drag_pos = None

        self.store = SettingsStore(ROOT / "settings.json")
        self.backend = Backend(ROOT, on_health=self._set_status)
        self.nativeEventFilter = None

        self.init_ui()
        # Window hugs its content — no dead space, no manual resize().
        self.layout().setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.store.load()
        self._reflect_settings()
        self.backend.start_flask_server(
            self.store.settings.source_lang_option)
        self.nativeEventFilter = register_hotkey(self.trigger_snip)

    # ---------- settings <-> combos ----------
    def _reflect_settings(self):
        """Push stored prefs into the combos without firing handlers."""
        s = self.store.settings
        from_idx = languages.find_from_index(
            s.source_lang_name, s.source_lang_option)
        to_idx = languages.find_to_index(s.dest_lang)
        self.from_combo.blockSignals(True)
        self.from_combo.setCurrentIndex(from_idx)
        self.from_combo.blockSignals(False)
        self.to_combo.blockSignals(True)
        self.to_combo.setCurrentIndex(to_idx)
        self.to_combo.blockSignals(False)
        s.source_lang_name = languages.FROM_LANGS[from_idx][0]
        s.source_lang_option = languages.FROM_LANGS[from_idx][1]
        s.dest_lang = languages.TO_LANGS[to_idx][1]
        s.dest_lang_name = languages.TO_LANGS[to_idx][0]
        self._update_swap_state()
        self._refresh_recent_chips()

    def _reset_to_defaults(self):
        self.store.reset()
        self.from_combo.blockSignals(True)
        self.from_combo.setCurrentIndex(0)
        self.from_combo.blockSignals(False)
        self.to_combo.blockSignals(True)
        self.to_combo.setCurrentIndex(0)
        self.to_combo.blockSignals(False)
        self.store.settings.source_lang_name = languages.FROM_LANGS[0][0]
        self.store.settings.source_lang_option = languages.FROM_LANGS[0][1]
        self.store.settings.dest_lang = languages.TO_LANGS[0][1]
        self.store.settings.dest_lang_name = languages.TO_LANGS[0][0]
        self._update_swap_state()

    # ---------- main UI ----------
    def init_ui(self):
        # Outer transparent layer: room for the card's drop shadow.
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        card = QtWidgets.QWidget()
        card.setObjectName("card")
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 5)
        shadow.setColor(QtGui.QColor(0, 0, 0, 180))
        card.setGraphicsEffect(shadow)
        root.addWidget(card)

        body = QtWidgets.QVBoxLayout(card)
        body.setContentsMargins(20, 14, 20, 18)
        body.setSpacing(13)

        # ---- custom dark titlebar: icon + wordmark ... status, gear, min, close
        bar_wrap = QtWidgets.QWidget()
        bar = QtWidgets.QHBoxLayout(bar_wrap)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)

        self.title_icon_lbl = QtWidgets.QLabel()
        icon_path = ROOT / "icon.png"
        if icon_path.exists():
            pm = QtGui.QPixmap(str(icon_path)).scaled(
                20, 20, QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation)
            self.title_icon_lbl.setPixmap(pm)
        bar.addWidget(self.title_icon_lbl)

        app_title = QtWidgets.QLabel(
            '<span style="color:#f4f4f8">Lingo</span>'
            '<span style="color:#7c86e6">Lens</span>')
        app_title.setObjectName("appTitle")
        app_title.setTextFormat(QtCore.Qt.RichText)
        bar.addWidget(app_title)
        bar.addStretch()

        self.status_button = QtWidgets.QPushButton()
        self.status_button.setObjectName("statusButton")
        self.status_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.status_button.setToolTip(
            "OCR engine status — click to re-check / restart")
        self.status_button.clicked.connect(self._on_status_clicked)
        self.status_button.setMaximumWidth(230)  # pill hugs its text
        self._set_status("starting")
        bar.addWidget(self.status_button)

        gear_btn = QtWidgets.QPushButton()
        gear_btn.setObjectName("winButton")
        gear_btn.setIcon(icons.paint_icon("gear", 18))
        gear_btn.setIconSize(QtCore.QSize(18, 18))
        gear_btn.setCursor(QtCore.Qt.PointingHandCursor)
        gear_btn.setToolTip("Overlay & capture settings")
        gear_btn.clicked.connect(self.open_settings)
        bar.addWidget(gear_btn)

        min_btn = QtWidgets.QPushButton("\u2013")
        min_btn.setObjectName("winButton")
        min_btn.setCursor(QtCore.Qt.PointingHandCursor)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)
        bar.addWidget(min_btn)

        close_btn = QtWidgets.QPushButton("\u00d7")
        close_btn.setObjectName("closeButton")
        close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        close_btn.setToolTip("Quit LingoLens")
        close_btn.clicked.connect(self.close)
        bar.addWidget(close_btn)

        # Drag the frameless window by the titlebar background.
        bar_wrap.mousePressEvent = lambda e: self._title_press(e)
        bar_wrap.mouseMoveEvent = lambda e: self._title_move(e)
        bar_wrap.mouseReleaseEvent = lambda e: self._title_release(e)
        body.addWidget(bar_wrap)

        # ---- hero action (note: && renders a literal &)
        self.snip_button = QtWidgets.QPushButton(
            "Snip && Translate    \u00b7    Alt+Shift+M")
        self.snip_button.setObjectName("ctaButton")
        self.snip_button.setIcon(icons.paint_icon("bolt", 22, "#ffffff"))
        self.snip_button.setIconSize(QtCore.QSize(22, 22))
        self.snip_button.setMinimumHeight(60)
        self.snip_button.setCursor(QtCore.Qt.PointingHandCursor)
        # Stretch to fill, but never dictate the window width.
        self.snip_button.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.snip_button.setToolTip(
            "Capture a screen region and translate it in place (Alt+Shift+M)")
        self.snip_button.clicked.connect(self.trigger_snip)
        body.addWidget(self.snip_button)

        # ---- language row: From, swap, To
        lang_row = QtWidgets.QHBoxLayout()
        lang_row.setSpacing(8)

        from_col = QtWidgets.QVBoxLayout()
        from_col.setSpacing(5)
        from_cap = QtWidgets.QLabel("FROM")
        from_cap.setObjectName("captionLabel")
        from_col.addWidget(from_cap)
        self.from_combo = QtWidgets.QComboBox()
        for name, _opt in languages.FROM_LANGS:
            self.from_combo.addItem(name)
        # Hug content: never stretch to the longest item name.
        self.from_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.from_combo.setMinimumContentsLength(9)
        self.from_combo.setMinimumWidth(150)
        self.from_combo.currentIndexChanged.connect(self._on_from_changed)
        from_col.addWidget(self.from_combo)
        lang_row.addLayout(from_col, 1)

        # Swap glyph only (text ⇄ renders in Segoe UI; emoji don't).
        self.swap_button = QtWidgets.QPushButton("\u21c4")
        self.swap_button.setObjectName("toolButton")
        self.swap_button.setFixedSize(40, 40)
        self.swap_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.swap_button.setToolTip("Swap languages")
        self.swap_button.clicked.connect(self._swap_languages)
        lang_row.addWidget(self.swap_button, 0, QtCore.Qt.AlignBottom)

        to_col = QtWidgets.QVBoxLayout()
        to_col.setSpacing(5)
        to_cap = QtWidgets.QLabel("TO")
        to_cap.setObjectName("captionLabel")
        to_col.addWidget(to_cap)
        self.to_combo = QtWidgets.QComboBox()
        for name, _code in languages.TO_LANGS:
            self.to_combo.addItem(name)
        # Hug content: never stretch to the longest item name.
        self.to_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.to_combo.setMinimumContentsLength(9)
        self.to_combo.setMinimumWidth(150)
        self.to_combo.currentIndexChanged.connect(self._on_to_changed)
        to_col.addWidget(self.to_combo)
        lang_row.addLayout(to_col, 1)
        body.addLayout(lang_row)

        # ---- recent pairs (chips are actions: click to re-apply)
        self.recents_chips = QtWidgets.QHBoxLayout()
        self.recents_chips.setSpacing(7)
        recents_row = QtWidgets.QHBoxLayout()
        recents_row.setSpacing(7)
        recents_caption = QtWidgets.QLabel("RECENT")
        recents_caption.setObjectName("captionLabel")
        recents_row.addWidget(recents_caption)
        recents_row.addLayout(self.recents_chips)
        recents_row.addStretch()
        self.recents_wrap = QtWidgets.QWidget()
        self.recents_wrap.setLayout(recents_row)
        body.addWidget(self.recents_wrap)

    # ---------- frameless drag ----------
    def _title_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = (event.globalPos()
                              - self.frameGeometry().topLeft())
            event.accept()

    def _title_move(self, event):
        if (event.buttons() & QtCore.Qt.LeftButton
                and self._drag_pos is not None):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def _title_release(self, event):
        self._drag_pos = None
        event.accept()

    # ---------- language selection ----------
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
        self.swap_button.setEnabled(ok)
        if ok:
            self.swap_button.setToolTip("Swap languages")
        else:
            self.swap_button.setToolTip(
                f"No OCR model for '{s.dest_lang_name}' — can't swap")

    def _swap_languages(self):
        s = self.store.settings
        from_name = s.source_lang_name
        to_name = languages.TO_LANGS[self.to_combo.currentIndex()][0]
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
        self.from_combo.setCurrentIndex(new_from)  # fires handler
        self.to_combo.setCurrentIndex(new_to)      # fires handler

    # ---------- recents ----------
    def _push_recent(self):
        s = self.store.settings
        entry = {"from": s.source_lang_name, "to": s.dest_lang}
        s.recent_pairs = [e for e in s.recent_pairs if e != entry]
        s.recent_pairs.insert(0, entry)
        s.recent_pairs = s.recent_pairs[:languages.MAX_RECENTS]
        self.store.save()
        self._refresh_recent_chips()

    def _refresh_recent_chips(self):
        while self.recents_chips.count():
            item = self.recents_chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for entry in self.store.settings.recent_pairs:
            from_short = languages.FROM_SHORT[
                languages.find_from_index(entry["from"], 1)]
            to_short = entry["to"].split("-")[0].upper()
            chip = QtWidgets.QPushButton(f"{from_short} \u2192 {to_short}")
            chip.setObjectName("chipButton")
            chip.setCursor(QtCore.Qt.PointingHandCursor)
            chip.setToolTip(f"{entry['from']} → "
                            f"{languages.to_display_name(entry['to'])}")
            chip.clicked.connect(
                lambda _c, e=dict(entry): self._apply_recent(e))
            self.recents_chips.addWidget(chip)
        self.recents_wrap.setVisible(bool(self.store.settings.recent_pairs))

    def _apply_recent(self, entry):
        s = self.store.settings
        self.from_combo.setCurrentIndex(
            languages.find_from_index(entry["from"], s.source_lang_option))
        self.to_combo.setCurrentIndex(
            languages.find_to_index(entry["to"]))

    # ---------- OCR status pill (live Flask /health) ----------
    def _set_status(self, state):
        text, accent = STATUS_STYLE[state]
        dot = "\u25cc" if state == "starting" else "\u25cf"
        self.status_button.setText(f"{dot}  {text}")
        self.status_button.setStyleSheet(
            f"QPushButton#statusButton {{"
            f" background-color: #14161d;"
            f" color: {accent};"
            f" border: 1px solid {accent};"
            f" border-radius: 13px;"
            f" padding: 6px 14px;"
            f"}}")

    def _on_status_clicked(self):
        """Manual re-check; restart the server if it is down."""
        if self.backend.recheck_health() == "restart":
            self.backend.restart_flask_server(
                self.store.settings.source_lang_option)

    # ---------- settings + actions ----------
    def open_settings(self):
        """All appearance knobs live in the dialog.

        The dialog edits appearance in place. A reset inside the dialog
        reports back through on_change, which re-reflects the combos and
        restarts the OCR server for the default language bundle.
        """
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
            QtWidgets.QMessageBox.warning(
                self, "Warning",
                f"Failed to launch screen snipper script: {err}")

    def closeEvent(self, a0):
        self.backend.stop()
        unregister_hotkey()
        a0.accept()
