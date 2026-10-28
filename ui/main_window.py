"""Main window — LingoLens Control Center in the Prism shell.

One :class:`GlassWindow` (flat custom-painted body, full-body drag)
+ a :class:`QStackedWidget` with two pages:

- :class:`MainPage` — hero snip button, From/To language selectors,
  recent-pair chips, engine status in the logo.
- :class:`SettingsPage` — live capture-box preview and capture-box
  knobs, all writing straight into ``SettingsStore``.

The window owns no domain state: languages from ``ui.languages``,
prefs from ``SettingsStore``, processes from ``Backend``.
"""

import sys
import time

from PyQt5.QtCore import (QEasingCurve, QEvent, Qt, QPropertyAnimation,
                          QRectF, QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QApplication, QGraphicsOpacityEffect,
                             QHBoxLayout, QLabel, QShortcut,
                             QStackedWidget, QVBoxLayout, QWidget)

from ui import ROOT, languages
from ui.backend import (Backend, hotkey_supported, is_autostart_enabled,
                        register_hotkey, set_autostart, unregister_hotkey)
from ui.settings_store import (DEFAULT_HOTKEY, OCR_ENGINES,
                               TRANSLATE_PROVIDERS, SettingsStore,
                               canonical_hotkey)
from ui.theme import (PALETTES, RADIUS, SHADOW, THEME_ORDER, WIN_W,
                      Th, alpha, css, rounded)
from ui.prism_widgets import (Chip, HeroButton, IconButton, HotkeyField,
                              LangSelector, LogoStatus, SwapButton,
                              ToggleSwitch, Toast, Wordmark, make_label)
from ui.settings_ui import (FlowLayout, Fadeable, KeyChip, ProviderList,
                            RefButton, RefColorRow, RefChip, RefPreview,
                            RefSliderRow, RefSpecCard, RefSwap, RefTabs)
from PyQt5.QtGui import QPen as _QPen
from PyQt5.QtGui import QPainter as _QPainter
from PyQt5.QtGui import QColor as _QColor
from PyQt5.QtGui import QFont as _QFont

ENGINE_LINE = "EasyOCR + OpenVINO · on-device OCR"

# Reference card geometry for the Settings page (settings_menu.html).
SETTINGS_W = 420
SETTINGS_H = 600
SETTINGS_RADIUS = 20
LANG_CHIPS = ["Latin", "Chinese", "Japanese", "Korean", "Arabic", "Cyrillic"]
LANG_SUPPORT = {
    "easyocr": list(LANG_CHIPS),
    "ppocr": ["Latin", "Chinese", "Japanese"],
}
ENGINE_SPEC = {
    "easyocr": ("The original pipeline. Slower, but reads the widest range "
                "of languages.", 2, 3),
    "ppocr": ("Runs fast on your device. Reads Latin, Chinese and Japanese.",
              3, 2),
}


# ==========================================================================
#  Glass window — flat painted body, full-body drag
# ==========================================================================
class GlassWindow(QWidget):
    def __init__(self, inner_w, inner_h):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._inner_w = inner_w
        self.set_inner_size(inner_w, inner_h)
        self._drag_off = None

    def set_inner_size(self, w, h):
        """Resize the window around a w×h content body."""
        self.setFixedSize(w, h)

    def body_rect(self):
        return QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

    # -- painted body ------------------------------------------------------
    def paintEvent(self, e):
        p = _QPainter(self)
        p.setRenderHints(_QPainter.Antialiasing | _QPainter.SmoothPixmapTransform
                         | _QPainter.TextAntialiasing)

        body = self.body_rect()
        settings = (hasattr(self, "stack")
                    and getattr(self, "settings", None) is self.stack.currentWidget())
        radius = SETTINGS_RADIUS if settings else RADIUS
        path = rounded(body, radius)
        p.fillPath(path, Th.c("bg_a"))

        edge = Th.c("line") if settings else alpha(Th.c("edge"), 60)
        p.setPen(_QPen(edge, 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rounded(body.adjusted(.5, .5, -.5, -.5), radius - .5))

    # -- full-body drag (manual move; no startSystemMove hand-off) ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_off = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_off is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPos() - self._drag_off)

    def mouseReleaseEvent(self, e):
        self._drag_off = None


# ==========================================================================
#  Main page
# ==========================================================================
class MainPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 22)
        lay.setSpacing(0)

        # ---- header ------------------------------------------------------
        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.logo = LogoStatus()
        bar.addWidget(self.logo)
        bar.addWidget(Wordmark())
        bar.addStretch(1)
        self.btn_theme = IconButton("sun", 34, tip="Cycle theme")
        self.btn_settings = IconButton("gear", 34, tip="Settings")
        self.btn_min = IconButton("minimize", 34, tip="Minimize")
        self.btn_close = IconButton("close", 34, danger=True, tip="Close")
        for b in (self.btn_theme, self.btn_settings, self.btn_min, self.btn_close):
            bar.addWidget(b)
        lay.addLayout(bar)
        lay.addSpacing(14)

        # ---- hero --------------------------------------------------------
        self.hero = HeroButton()
        lay.addWidget(self.hero)
        lay.addSpacing(12)

        # ---- language pair ----------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(10)
        self.src = LangSelector(
            rows=languages.FROM_LANGS,
            badge_of=lambda i, r: languages.FROM_SHORT[i],
            label_of=lambda i, r: r[0],
            index=0, align="left")
        self.dst = LangSelector(
            rows=languages.TO_LANGS,
            badge_of=lambda i, r: r[1].split("-")[0].upper(),
            label_of=lambda i, r: r[0],
            index=0, align="right")
        self.swap = SwapButton()
        row.addWidget(self.src, 1)
        row.addWidget(self.swap, 0, Qt.AlignVCenter)
        row.addWidget(self.dst, 1)
        lay.addLayout(row)
        lay.addSpacing(14)

        # ---- recent pairs --------------------------------------------------
        self.chips_row = QHBoxLayout()
        self.chips_row.setSpacing(8)
        self.chips_row.setContentsMargins(0, 0, 0, 0)
        self.recents_wrap = QWidget()
        self.recents_wrap.setLayout(self.chips_row)
        lay.addWidget(self.recents_wrap)
        lay.addSpacing(6)

        # ---- footer --------------------------------------------------------
        lay.addStretch(1)
        self.eng = make_label(ENGINE_LINE, 8.5, _QFont.Normal, "muted")
        self.eng.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.eng)

        # ---- wiring ----------------------------------------------------------
        self.src.changed.connect(self._on_from_changed)
        self.dst.changed.connect(self._on_to_changed)
        self.swap.clicked.connect(self._swap_languages)
        self.hero.clicked.connect(self.win.trigger_snip)
        self.logo.clicked.connect(self.win.on_status_clicked)
        self.btn_theme.clicked.connect(self._cycle_theme)
        self.btn_settings.clicked.connect(lambda: self.win.goto(1))
        self.btn_min.clicked.connect(self.win.showMinimized)
        self.btn_close.clicked.connect(self.win.close)

        self._reflect_settings()
        self.refresh_theme_icon()

    # ---------------------------------------------------------------- helpers
    def _reflect_settings(self):
        """Push stored prefs into the pickers without firing handlers."""
        s = self.win.store.settings
        from_idx = languages.find_from_index(
            s.source_lang_name, s.source_lang_option)
        to_idx = languages.find_to_index(s.dest_lang)
        self.src.setCurrentIndex(from_idx)
        self.dst.setCurrentIndex(to_idx)
        s.source_lang_name = languages.FROM_LANGS[from_idx][0]
        s.source_lang_option = languages.FROM_LANGS[from_idx][1]
        s.dest_lang = languages.TO_LANGS[to_idx][1]
        s.dest_lang_name = languages.TO_LANGS[to_idx][0]
        self._update_swap_state()
        self._refresh_recent_chips()
        self.refresh_engine_line()

    def refresh_engine_line(self):
        """Footer names the engine this build will actually sniff with."""
        s = self.win.store.settings
        engine = "PP-OCRv6" if s.ocr_engine == "ppocr" else "EasyOCR"
        self.eng.setText(f"{engine} + OpenVINO · on-device OCR")

    # ------------------------------------------------------------- languages
    def _on_from_changed(self, idx):
        name, opt = languages.FROM_LANGS[idx]
        s = self.win.store.settings
        option_changed = (opt != s.source_lang_option)
        s.source_lang_name = name
        s.source_lang_option = opt
        self.win.store.save()
        # Languages sharing one model bundle need no server restart.
        if option_changed:
            self.win.backend.restart_flask_server(opt)
        else:
            print(f"Source language updated: {name} (same OCR model, no restart)")
        self._update_swap_state()
        self._refresh_recent_chips()

    def _on_to_changed(self, idx):
        name, code = languages.TO_LANGS[idx]
        s = self.win.store.settings
        s.dest_lang_name = name
        s.dest_lang = code
        print(f"Destination language updated: {name}")
        self.win.store.save()
        self._update_swap_state()
        self._refresh_recent_chips()

    def _update_swap_state(self):
        s = self.win.store.settings
        ok = languages.is_swappable(s.source_lang_name, s.dest_lang_name)
        self.swap.setEnabled(ok)
        if ok:
            self.swap.setToolTip("Swap languages")
        else:
            self.swap.setToolTip(
                f"No OCR model for '{s.dest_lang_name}' - can't swap")

    def _swap_languages(self):
        s = self.win.store.settings
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
        self.src.setCurrentIndex(new_from, emit=True)  # fires handler
        self.dst.setCurrentIndex(new_to, emit=True)    # fires handler

    # ---------------------------------------------------------------- recents
    def _push_recent(self):
        s = self.win.store.settings
        entry = {"from": s.source_lang_name, "to": s.dest_lang}
        s.recent_pairs = [e for e in s.recent_pairs if e != entry]
        s.recent_pairs.insert(0, entry)
        s.recent_pairs = s.recent_pairs[:languages.MAX_RECENTS]
        self.win.store.save()
        self._refresh_recent_chips()

    def _refresh_recent_chips(self):
        while self.chips_row.count():
            item = self.chips_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        pairs = self.win.store.settings.recent_pairs
        if pairs:
            s = self.win.store.settings
            for entry in pairs:
                from_short = languages.FROM_SHORT[
                    languages.find_from_index(entry["from"], 1)]
                to_short = entry["to"].split("-")[0].upper()
                chip = Chip(from_short, to_short)
                chip.set_active(entry["from"] == s.source_lang_name
                                and entry["to"] == s.dest_lang)
                chip.setToolTip(f'{entry["from"]} \u2192 '
                                f'{languages.to_display_name(entry["to"])}')
                chip.clicked.connect(
                    lambda e=dict(entry): self._apply_recent(e))
                self.chips_row.addWidget(chip)
        self.chips_row.addStretch(1)
        self.recents_wrap.setVisible(bool(pairs))
        if self.win.stack.currentIndex() == 0:
            self.win._hug()  # chips row appearing/disappearing changes height

    def _apply_recent(self, entry):
        s = self.win.store.settings
        self.src.setCurrentIndex(
            languages.find_from_index(entry["from"], s.source_lang_option),
            emit=True)
        self.dst.setCurrentIndex(
            languages.find_to_index(entry["to"]), emit=True)

    # ------------------------------------------------------------------ theme
    def _cycle_theme(self):
        order = THEME_ORDER
        nxt = order[(order.index(self.win.theme_name) + 1) % len(order)]
        self.btn_theme.icon_spin.go(self.btn_theme.icon_spin.val + 90)
        self.win.set_theme(nxt)

    def refresh_theme_icon(self):
        self.btn_theme.icon = "moon" if self.win.theme_name == "day" else "sun"
        self.btn_theme.update()


# ==========================================================================
#  Settings page (in-window; hugs its content via _hug())
# ==========================================================================
class SettingsPage(QWidget):
    """Settings card, matching ``settings_menu.html``.

    420 px wide, 20 px padding, 14 px gaps: title, equal tabs behind a
    sliding pill, one top-aligned panel at a time (fade + 6 px rise),
    ghost/primary footer.
    """

    back = pyqtSignal()

    FILL_PRESETS = ["#6366F1", "#22D3EE", "#34D399", "#FBBF24", "#FB7185"]
    TAB_IDS = ["capture", "read", "translate", "keys", "general"]
    CONTENT_W = 380

    def __init__(self, win):
        super().__init__()
        self.win = win
        self._in_anim = None
        self._shift = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        lay.addWidget(make_label("Settings", 13.5, _QFont.DemiBold, "text"))

        s = self.win.store.settings
        self.tabs = RefTabs([
            ("capture", "Capture"), ("read", "Read"),
            ("translate", "Translate"), ("keys", "Hotkeys"),
            ("general", "General"),
        ], "capture", width=self.CONTENT_W)
        lay.addWidget(self.tabs)

        self.panels = QStackedWidget()
        self._build_capture_panel(s)
        self._build_read_panel(s)
        self._build_translate_panel(s)
        self._build_hotkeys_panel()
        self._build_general_panel(s)
        lay.addWidget(self.panels, 1)
        lay.addSpacing(4)  # .foot { padding-top: 4px }

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(0)
        self.btn_reset = RefButton("Reset defaults", "ghost")
        self.btn_done = RefButton("Done", "primary")
        foot.addWidget(self.btn_reset)
        foot.addStretch(1)
        foot.addWidget(self.btn_done)
        lay.addLayout(foot)

        self.tabs.valueChanged.connect(self._switch_panel)
        self.r_fill.colorChanged.connect(
            lambda c: self._set("fill_color", c.name()))
        self.r_fop.valueChanged.connect(lambda v: self._set("opacity", v / 100.0))
        self.r_bw.valueChanged.connect(lambda v: self._set("line_width", v))
        self.r_engine.valueChanged.connect(self._on_engine)
        self.btn_reset.clicked.connect(self.reset)
        self.btn_done.clicked.connect(self.back.emit)

    # ------------------------------------------------------------------ panels
    def _panel(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        self.panels.addWidget(page)
        return box

    def _sub(self, text):
        return make_label(text, 9.75, _QFont.DemiBold, "text")

    def _build_capture_panel(self, s):
        box = self._panel()
        self.preview = RefPreview(s.fill_color, int(s.opacity * 100),
                                  s.line_width)
        box.addWidget(self.preview)
        self.r_fill = RefColorRow("Selection fill", self.FILL_PRESETS,
                                  s.fill_color)
        self.r_fop = RefSliderRow("Opacity", 0, 100, int(s.opacity * 100), "%")
        self.r_bw = RefSliderRow("Border width", 0, 10, s.line_width, " px")
        for row in (self.r_fill, self.r_fop, self.r_bw):
            box.addWidget(row)
        box.addStretch(1)

    def _build_read_panel(self, s):
        box = self._panel()
        box.addWidget(self._sub("Recognition engine"))
        self.r_engine = RefTabs(OCR_ENGINES, s.ocr_engine, width=self.CONTENT_W)
        box.addWidget(self.r_engine)
        self.spec = RefSpecCard("", 0, 0)
        box.addWidget(self.spec)
        box.addWidget(self._sub("Languages to read"))
        holder = QWidget()
        flow = FlowLayout(holder, spacing=8)
        self.chips = {}
        for lang in LANG_CHIPS:
            chip = RefChip(lang)
            chip.clicked.connect(lambda l=lang: self._toggle_lang(l))
            flow.addWidget(chip)
            self.chips[lang] = chip
        holder.setFixedHeight(flow.heightForWidth(self.CONTENT_W))
        box.addWidget(holder)
        self.lang_hint = make_label("", 9.0, _QFont.Normal, "muted")
        box.addWidget(self.lang_hint)
        box.addStretch(1)
        self._sync_engine_ui()

    def _build_translate_panel(self, s):
        box = self._panel()
        head = QWidget()
        head.setFixedHeight(48)
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        block = QVBoxLayout()
        block.setContentsMargins(0, 0, 0, 0)
        block.setSpacing(2)
        block.addWidget(make_label("Translate after capture", 10.5,
                                   _QFont.DemiBold, "text"))
        block.addWidget(make_label("Show the translation next to the text",
                                   9.0, _QFont.Normal, "muted"))
        row.addLayout(block, 1)
        self.translate_toggle = ToggleSwitch(s.translate)
        row.addWidget(self.translate_toggle, 0, Qt.AlignVCenter)
        box.addWidget(head)

        self.tr_body = Fadeable()
        body = QVBoxLayout(self.tr_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)

        langs = QHBoxLayout()
        langs.setContentsMargins(0, 0, 0, 0)
        langs.setSpacing(8)
        from_col = QVBoxLayout()
        from_col.setContentsMargins(0, 0, 0, 0)
        from_col.setSpacing(4)
        from_col.addWidget(make_label("From", 9.0, _QFont.Normal, "muted"))
        self.tr_from = LangSelector(
            languages.FROM_LANGS,
            lambda i, r: languages.FROM_SHORT[i],
            lambda i, r: r[0],
            languages.find_from_index(s.from_lang, s.source_lang_option),
            "left", compact=True)
        from_col.addWidget(self.tr_from)
        to_col = QVBoxLayout()
        to_col.setContentsMargins(0, 0, 0, 0)
        to_col.setSpacing(4)
        to_col.addWidget(make_label("To", 9.0, _QFont.Normal, "muted"))
        self.tr_to = LangSelector(
            languages.TO_LANGS,
            lambda i, r: r[1].split("-")[0].upper(),
            lambda i, r: r[0],
            languages.find_to_index(s.to_lang), "right", compact=True)
        to_col.addWidget(self.tr_to)
        self.tr_swap = RefSwap()
        langs.addLayout(from_col, 1)
        langs.addWidget(self.tr_swap, 0, Qt.AlignBottom)
        langs.addLayout(to_col, 1)
        body.addLayout(langs)

        body.addWidget(self._sub("Translation provider"))
        self.provider = ProviderList(TRANSLATE_PROVIDERS, s.provider)
        body.addWidget(self.provider)
        box.addWidget(self.tr_body)
        box.addStretch(1)

        self.translate_toggle.toggled.connect(self._on_translate_toggle)
        self.tr_body.set_dimmed(not s.translate)
        self.provider.valueChanged.connect(lambda v: self._set("provider", v))
        self.tr_from.changed.connect(self._on_from_setting)
        self.tr_to.changed.connect(self._on_to_setting)
        self.tr_swap.clicked.connect(self._swap_translate)
        self._sync_swap()

    def _build_hotkeys_panel(self):
        s = self.win.store.settings
        box = self._panel()
        self.hotkey_field = HotkeyField(s.hotkey)
        box.addWidget(self._row("Start capture", self.hotkey_field))
        box.addWidget(self._row("Cancel", KeyChip("Esc")))
        box.addStretch(1)
        self.hotkey_field.changed.connect(self._on_hotkey_changed)
        self.hotkey_field.recordingChanged.connect(self._on_hotkey_recording)

    def _row(self, text, widget, hint=None):
        """Reference ``.row``: 48 px tall, 112 px label, content right."""
        host = QWidget()
        host.setFixedHeight(48)
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        lb = make_label(text, 9.75, _QFont.Normal, "muted")
        lb.setFixedWidth(112)
        row.addWidget(lb)
        if hint:
            row.addWidget(make_label(hint, 9.0, _QFont.Normal, "muted"))
        row.addStretch(1)
        row.addWidget(widget)
        return host

    def _build_general_panel(self, s):
        box = self._panel()
        self.autostart_toggle = ToggleSwitch(is_autostart_enabled())
        box.addWidget(self._row("Start on login", self.autostart_toggle,
                                "Launch with your system"))
        box.addStretch(1)
        self.autostart_toggle.toggled.connect(self._on_autostart_changed)

    # ------------------------------------------------------------------ tabs
    def _switch_panel(self, value):
        idx = self.TAB_IDS.index(value)
        if idx == self.panels.currentIndex():
            return
        self.panels.setCurrentIndex(idx)
        page = self.panels.currentWidget()

        fx = QGraphicsOpacityEffect(page)
        fx.setOpacity(0.0)
        page.setGraphicsEffect(fx)
        fade = QPropertyAnimation(fx, b"opacity", self)
        fade.setDuration(180)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.finished.connect(lambda: page.setGraphicsEffect(None))
        fade.start()
        self._in_anim = fade

        # translateY(6px) -> 0, exactly like @keyframes in
        lay = page.layout()
        shift = QVariantAnimation(self)
        shift.setDuration(180)
        shift.setStartValue(6.0)
        shift.setEndValue(0.0)
        shift.setEasingCurve(QEasingCurve.OutCubic)
        shift.valueChanged.connect(
            lambda v: lay.setContentsMargins(0, int(round(float(v))), 0, 0))
        shift.start()
        self._shift = shift
        self.win._hug()

    # --------------------------------------------------------------- reading
    def _on_engine(self, engine):
        self._set("ocr_engine", engine)
        s = self.win.store.settings
        supported = LANG_SUPPORT.get(engine, LANG_CHIPS)
        langs = [l for l in (s.langs or []) if l in supported]
        if not langs:
            langs = ["Latin"]
        self._set("langs", langs)

    def _toggle_lang(self, lang):
        s = self.win.store.settings
        if lang not in LANG_SUPPORT.get(s.ocr_engine, LANG_CHIPS):
            return
        langs = list(s.langs or ["Latin"])
        if lang in langs:
            if len(langs) == 1:
                return  # keep at least one language selected
            langs.remove(lang)
        else:
            langs.append(lang)
        self._set("langs", langs)

    def _sync_engine_ui(self):
        s = self.win.store.settings
        desc, speed, cover = ENGINE_SPEC.get(
            s.ocr_engine, ENGINE_SPEC["easyocr"])
        self.spec.set_spec(desc, speed, cover)
        supported = LANG_SUPPORT.get(s.ocr_engine, LANG_CHIPS)
        selected = set(s.langs or [])
        for lang, chip in self.chips.items():
            chip.setEnabled(lang in supported)
            chip.set_active(lang in selected)
        self.lang_hint.setText(
            "Greyed-out languages need EasyOCR."
            if s.ocr_engine == "ppocr" else "All languages are available.")

    # ------------------------------------------------------------- translate
    def _on_translate_toggle(self, on):
        self._set("translate", bool(on))
        self.tr_body.set_dimmed(not on)

    def _sync_swap(self):
        s = self.win.store.settings
        self.tr_swap.setEnabled(bool(s.from_lang)
                                and s.from_lang.lower() != "auto-detect")

    def _on_from_setting(self, idx):
        self._set("from_lang", languages.FROM_LANGS[idx][0])
        self._set("source_lang_name", languages.FROM_LANGS[idx][0])
        self._set("source_lang_option", languages.FROM_LANGS[idx][1])
        self._sync_swap()

    def _on_to_setting(self, idx):
        self._set("to_lang", languages.TO_LANGS[idx][1])
        self._set("dest_lang", languages.TO_LANGS[idx][1])
        self._set("dest_lang_name", languages.TO_LANGS[idx][0])
        self._sync_swap()

    def _swap_translate(self):
        s = self.win.store.settings
        from_name = s.from_lang
        to_name = languages.to_display_name(s.to_lang)
        from_idx = languages.find_from_index(to_name, s.source_lang_option)
        to_idx = languages.find_to_index(from_name)
        if from_idx >= 0 and to_idx >= 0:
            self.tr_from.setCurrentIndex(from_idx, emit=True)
            self.tr_to.setCurrentIndex(to_idx, emit=True)

    # --------------------------------------------------------------- hotkeys
    def _on_hotkey_recording(self, recording):
        """Release the live hotkey while the user records a new one."""
        # The in-app shortcut would otherwise fire on the combo being recorded.
        self.win.local_hotkey_shortcut.setEnabled(not recording)
        if recording:
            unregister_hotkey()
        else:
            self._register_hotkey()

    def _register_hotkey(self):
        s = self.win.store.settings
        unregister_hotkey()
        filt = register_hotkey(self.win.trigger_snip, s.hotkey)
        self.win.nativeEventFilter = filt
        return filt is not None

    def _on_hotkey_changed(self, sequence):
        sequence = canonical_hotkey(sequence)
        if not hotkey_supported(sequence):
            self.hotkey_field.set_sequence(self.win.store.settings.hotkey)
            self.win.toast.show_text(
                "Use a modifier (Ctrl, Alt, Shift or Win) plus a letter, "
                "digit or F-key")
            self._register_hotkey()
            return
        previous = self.win.store.settings.hotkey
        self.win.store.settings.hotkey = sequence
        self.win.store.save()
        self.hotkey_field.set_sequence(sequence)
        self.win.local_hotkey_shortcut.setKey(QKeySequence(sequence))
        if not self._register_hotkey():
            # Windows refused it (usually already owned by another app).
            self.win.store.settings.hotkey = previous
            self.win.store.save()
            self.hotkey_field.set_sequence(previous)
            self.win.local_hotkey_shortcut.setKey(QKeySequence(previous))
            self._register_hotkey()
            self.win.toast.show_text(
                f"{sequence} is already used by another application")
            return
        self.win.toast.show_text(f"Capture now starts with {sequence}")

    # -------------------------------------------------------------- autostart
    def _on_autostart_changed(self, enabled):
        if set_autostart(ROOT, enabled):
            self._set("autostart", bool(enabled))
        else:
            self.autostart_toggle.setChecked(not enabled)
            self.win.toast.show_text(
                "Could not update the Windows startup entry")

    # ------------------------------------------------- store <-> preview ---
    def _sync_summaries(self):
        self._sync_engine_ui()

    def _sync_preview(self):
        s = self.win.store.settings
        self.preview.set_state(s.fill_color, int(s.opacity * 100),
                               s.line_width)

    def _set(self, key, value):
        setattr(self.win.store.settings, key, value)
        self.win.store.save()
        self._sync_preview()
        self._sync_summaries()
        self.win.main.refresh_engine_line()

    def reset(self):
        self.win.store.reset()  # keeps recent pairs (history, not config)
        if self.win.theme_name != self.win.store.settings.theme:
            self.win.set_theme(self.win.store.settings.theme)
        self._refresh_from_store()
        # Defaults include the shortcut and autostart, so apply them for real.
        self._on_hotkey_changed(self.win.store.settings.hotkey)
        set_autostart(ROOT, self.win.store.settings.autostart)
        self.autostart_toggle.setChecked(is_autostart_enabled())

    def _refresh_from_store(self):
        s = self.win.store.settings
        self.r_fill.set_color(s.fill_color)
        self.r_fop.setValue(int(s.opacity * 100), animate=True)
        self.r_bw.setValue(s.line_width, animate=True)
        self.r_engine.select(s.ocr_engine)
        self.translate_toggle.setChecked(s.translate)
        self.tr_body.set_dimmed(not s.translate)
        self.provider.set_value(s.provider)
        self.hotkey_field.set_sequence(s.hotkey)
        self.autostart_toggle.setChecked(is_autostart_enabled())
        self.tr_from.setCurrentIndex(
            languages.find_from_index(s.from_lang, s.source_lang_option))
        self.tr_to.setCurrentIndex(languages.find_to_index(s.to_lang))
        self._sync_swap()
        self._sync_preview()
        self._sync_summaries()
        self.win.main.refresh_engine_line()

# ==========================================================================
#  Control Center
# ==========================================================================
class LingoLensControlCenter(GlassWindow):
    def __init__(self):
        self.store = SettingsStore(ROOT / "settings.json")
        self.store.load()
        theme_name = self.store.settings.theme
        if theme_name not in THEME_ORDER:
            theme_name = "aurora"
            self.store.settings.theme = theme_name
        # Boot straight into the stored theme (no morph on launch).
        Th.a = PALETTES[theme_name]
        Th.b = PALETTES[theme_name]
        Th.t = 1.0
        self.theme_name = theme_name

        super().__init__(WIN_W, 420)
        self.setWindowTitle("LingoLens")
        self._last_status = None
        self.backend = Backend(ROOT, on_health=self._set_status)
        self.nativeEventFilter = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        self.stack = QStackedWidget()
        self.main = MainPage(self)
        self.settings = SettingsPage(self)
        self.stack.addWidget(self.main)
        self.stack.addWidget(self.settings)
        root.addWidget(self.stack)
        self.toast = Toast(self, bottom_margin=SHADOW + 16)

        self._hug()  # drop the ~370px dead space the old fixed 740px left

        self.settings.back.connect(lambda: self.goto(0))
        # In-app fallback for when the global registration is refused (for
        # example the combo is already owned by another app).
        self.local_hotkey_shortcut = QShortcut(
            QKeySequence(self.store.settings.hotkey), self,
            activated=self.trigger_snip)

        self.backend.start_flask_server(
            self.store.settings.source_lang_option)
        self.nativeEventFilter = register_hotkey(
            self.trigger_snip, self.store.settings.hotkey)
        self._theme_anim = None
        self._fade = None

    # ------------------------------------------------------------------ pages
    def _hug(self):
        """Size the window to the current page's content.

        The Settings page is the reference card: 420 px wide, at least
        600 px tall. Main keeps the 480 px Prism width.
        """
        page = self.stack.currentWidget()
        QApplication.sendPostedEvents(None, QEvent.LayoutRequest)
        lay = page.layout()
        lay.invalidate()
        lay.activate()
        if page is getattr(self, "settings", None):
            h = max(SETTINGS_H, max(1, lay.sizeHint().height()))
            self.set_inner_size(SETTINGS_W, h)
            return
        hint = max(1, lay.sizeHint().height())
        self.set_inner_size(WIN_W, hint)

    def goto(self, idx):
        if idx == self.stack.currentIndex():
            return
        if idx == 0 and hasattr(self, "main"):
            self.main.refresh_engine_line()
        page = self.stack.widget(idx)
        fx = QGraphicsOpacityEffect(page)
        fx.setOpacity(0.0)
        page.setGraphicsEffect(fx)
        self.stack.setCurrentIndex(idx)
        self._hug()
        a = QPropertyAnimation(fx, b"opacity", self)
        a.setDuration(260)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.finished.connect(lambda: page.setGraphicsEffect(None))
        a.start()
        self._fade = a

    # ------------------------------------------------------------------ theme
    def set_theme(self, name):
        if name not in THEME_ORDER:
            return
        self.theme_name = name
        self.store.settings.theme = name
        self.store.save()
        Th.a = Th.snapshot()
        Th.b = PALETTES[name]
        Th.t = 0.0
        a = QVariantAnimation(self, duration=420)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.InOutCubic)

        def on(v):
            Th.t = float(v)
            for w in self.findChildren(QWidget):
                w.update()
            self.update()

        a.valueChanged.connect(on)
        a.finished.connect(self._refresh_labels)
        a.start()
        self._theme_anim = a
        self.main.refresh_theme_icon()
        # The Settings page no longer exposes a theme picker; nothing to sync.

    def _refresh_labels(self):
        for lb in self.findChildren(QLabel):
            if hasattr(lb, "refresh"):
                lb.refresh()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.stack.currentIndex() == 1:
            self.goto(0)
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------------ status
    def _set_status(self, state):
        if state == self._last_status:
            return  # repeated same-state poll: skip the logo entirely
        self._last_status = state
        main = getattr(self, "main", None)
        if main is None:
            return  # backend can report synchronously before MainPage exists
        main.logo.set_state(state)

    def on_status_clicked(self):
        """Manual re-check; restart the server if it is down."""
        if self.backend.recheck_health() == "restart":
            self.backend.restart_flask_server(
                self.store.settings.source_lang_option)

    # -------------------------------------------------------------------- snip
    def trigger_snip(self):
        self.main._push_recent()
        s = self.store.settings
        err = self.backend.launch_snip(
            s.dest_lang, s.fill_color, s.opacity, s.line_width,
            ocr_engine=s.ocr_engine,
            source_option=s.source_lang_option,
            provider=s.provider)
        if err:
            self.toast.show_text(f"Could not launch snipper: {err}")
        else:
            self.toast.show_text("Snipper launched - drag a region to translate")

    def closeEvent(self, a0):
        self.backend.stop()
        unregister_hotkey()
        a0.accept()


if __name__ == "__main__":  # headless check: QT_QPA_PLATFORM=offscreen
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtGui import QImage as _QImage

    Backend.start_flask_server = lambda self, source_lang_option: None
    _app = QApplication(sys.argv)
    _win = LingoLensControlCenter()

    def _snap(widget, path, bg="#cfd3de", scale=2):
        widget.show()
        _app.processEvents()
        img = _QImage(widget.size() * scale, _QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(scale)
        img.fill(_QColor(bg))
        _p = _QPainter(img)
        widget.render(_p)
        _p.end()
        img.save(path)
        return path

    import tempfile as _tf
    _scratch = _tf.gettempdir()
    print(_snap(_win, f"{_scratch}/prism_main.png"))
    _win.goto(1)
    for _ in range(6):  # allow the page-fade to finish before the shot
        _app.processEvents()
        time.sleep(0.08)
    print(_snap(_win, f"{_scratch}/prism_settings.png"))
