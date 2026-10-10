"""Main window — LingoLens Control Center in the Prism shell.

One :class:`GlassWindow` (custom-painted glass body, ambient glows,
full-body drag) + a :class:`QStackedWidget` with two pages:

- :class:`MainPage` — hero snip button, gated capture-mode switch,
  From/To language selectors, recent-pair chips, live OCR status.
- :class:`SettingsPage` — theme picker, live style preview, capture-box
  and overlay-text knobs, all writing straight into ``SettingsStore``.

The window owns NO domain state: languages from ``ui.languages``,
prefs from ``SettingsStore``, processes from ``Backend``.

Honest-data rule: nothing here invents telemetry. The Control Center
process never sees OCR text, latency, or confidence, so there are no
history-snippet rows and no latency tiles — recent-pair chips (backed
by ``store.settings.recent_pairs``) are the single recents surface,
and the footer names the real engine (EasyOCR + OpenVINO).
"""

import math
import sys
import time

from PyQt5.QtCore import (QEasingCurve, QPointF, Qt, QPropertyAnimation,
                          QRectF, QVariantAnimation, QTimer, pyqtSignal)
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import (QApplication, QGraphicsOpacityEffect,
                             QHBoxLayout, QLabel, QScrollArea, QShortcut,
                             QStackedWidget, QVBoxLayout, QWidget)

from ui import ROOT, languages
from ui.backend import Backend, register_hotkey, unregister_hotkey
from ui.settings_store import SettingsStore
from ui.theme import (PALETTES, RADIUS, SHADOW, THEME_ORDER, WIN_W,
                      Th, alpha, app_font, mix, rounded)
from ui.prism_widgets import (Card, Chip, ColorRow, HeroButton, IconButton,
                              LangSelector, OverlayPreview, PillButton,
                              Segmented, SliderRow, StatusPill, SwapButton,
                              ThemePicker, Toast, Wordmark, make_label)
from PyQt5.QtGui import QBrush as _QBrush
from PyQt5.QtGui import QLinearGradient as _QLinearGradient
from PyQt5.QtGui import QPen as _QPen
from PyQt5.QtGui import QRadialGradient as _QRadialGradient
from PyQt5.QtGui import QPainter as _QPainter
from PyQt5.QtGui import QColor as _QColor
from PyQt5.QtGui import QFont as _QFont

HEALTH = {  # backend state -> (pill text, palette key)
    "ready": ("OCR ready", "green"),
    "starting": ("OCR starting", "amber"),
    "offline": ("OCR offline - retry", "rose"),
}

ENGINE_LINE = "EasyOCR + OpenVINO · on-device OCR"

# Capture modes beyond region need capture.py support (window/screen
# grab argv) that does not exist yet — they stay visible but gated.
MODE_REASON = "Window / full-screen capture is not wired yet - region only"


def _caption(text):
    lb = make_label(text.upper(), 9, _QFont.DemiBold, "muted")
    f = lb.font()
    f.setLetterSpacing(_QFont.AbsoluteSpacing, 1.2)
    lb.setFont(f)
    return lb


# ==========================================================================
#  Glass window — painted body, throttled ambient clock, full-body drag
# ==========================================================================
class GlassWindow(QWidget):
    # 15 fps ambient clock; stopped while hidden/minimised (no background burn).
    AMBIENT_MS = 66

    def __init__(self, inner_w, inner_h):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._inner_w = inner_w
        self.set_inner_size(inner_w, inner_h)
        self._drag_off = None
        self._shadow = None
        self._shadow_dpr = 0
        self._t0 = time.monotonic()
        self._clock = QTimer(self, interval=self.AMBIENT_MS)
        self._clock.timeout.connect(self._tick)
        self._clock.start()

    def set_inner_size(self, w, h):
        """Resize the window around a w×h content body (shadow margin added)."""
        self.setFixedSize(w + 2 * SHADOW, h + 2 * SHADOW)
        self._shadow = None  # shadow pixmap keys off window size; rebuild

    def body_rect(self):
        return QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

    # -- ambient clock: repaint only while actually on screen ---------------
    def _tick(self):
        if self.isVisible() and not self.isMinimized():
            self.update()

    def showEvent(self, e):
        if not self._clock.isActive():
            self._clock.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._clock.stop()
        super().hideEvent(e)

    def changeEvent(self, e):
        if e.type() == e.WindowStateChange:
            if self.isMinimized():
                self._clock.stop()
            elif not self._clock.isActive():
                self._clock.start()
        super().changeEvent(e)

    # -- shadow (pre-rendered once per DPR) ---------------------------------
    def _build_shadow(self):
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = _QPainter(pm)
        p.setRenderHint(_QPainter.Antialiasing)
        body = self.body_rect()
        for i in range(20, 0, -1):
            grow = i * (SHADOW - 10) / 20
            r = body.adjusted(-grow, -grow + 9, grow, grow + 9)
            p.fillPath(rounded(r, RADIUS + grow), _QColor(2, 3, 12, 6))
        p.end()
        self._shadow, self._shadow_dpr = pm, dpr

    def paintEvent(self, e):
        if self._shadow is None or self._shadow_dpr != self.devicePixelRatioF():
            self._build_shadow()
        p = _QPainter(self)
        p.setRenderHints(_QPainter.Antialiasing | _QPainter.SmoothPixmapTransform
                         | _QPainter.TextAntialiasing)
        p.drawPixmap(0, 0, self._shadow)

        body = self.body_rect()
        path = rounded(body, RADIUS)
        t = time.monotonic() - self._t0

        base = _QLinearGradient(body.topLeft(), body.bottomRight())
        base.setColorAt(0, Th.c("bg_a"))
        base.setColorAt(1, Th.c("bg_b"))
        p.fillPath(path, _QBrush(base))

        gs = Th.glow()
        glows = [
            (0.12 + 0.07 * math.sin(t * 0.50), -0.02 + 0.04 * math.cos(t * 0.40), 0.85, "indigo", 95),
            (0.98 + 0.05 * math.cos(t * 0.35), 0.30 + 0.07 * math.sin(t * 0.55), 0.62, "fuchsia", 52),
            (0.25 + 0.09 * math.sin(t * 0.30 + 2), 1.04 + 0.04 * math.cos(t * 0.50), 0.75, "cyan", 55),
        ]
        for fx, fy, fr, key, a in glows:
            c = QPointF(body.left() + fx * body.width(), body.top() + fy * body.height())
            g = _QRadialGradient(c, fr * body.width())
            g.setColorAt(0, alpha(Th.c(key), a * gs))
            g.setColorAt(1, alpha(Th.c(key), 0))
            p.fillPath(path, _QBrush(g))

        sheen = _QLinearGradient(body.topLeft(), QPointF(body.left(), body.top() + 140))
        sheen.setColorAt(0, alpha(Th.c("edge"), 14))
        sheen.setColorAt(1, alpha(Th.c("edge"), 0))
        p.fillPath(path, _QBrush(sheen))

        edge = _QLinearGradient(body.topLeft(), body.bottomLeft())
        edge.setColorAt(0, alpha(Th.c("edge"), 70))
        edge.setColorAt(0.5, alpha(Th.c("edge"), 22))
        edge.setColorAt(1, alpha(Th.c("edge"), 12))
        p.setPen(_QPen(_QBrush(edge), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rounded(body.adjusted(.5, .5, -.5, -.5), RADIUS - .5))

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
        logo_file = ROOT / "logo.png"
        if logo_file.exists():
            pm = QPixmap(str(logo_file)).scaled(
                36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_lbl = QLabel()
            logo_lbl.setPixmap(pm)
            logo_lbl.setFixedSize(36, 36)
            bar.addWidget(logo_lbl)
        bar.addWidget(Wordmark())
        bar.addSpacing(8)
        self.pill = StatusPill("OCR starting", "amber")
        self.pill.setToolTip("OCR engine status - click to re-check / restart")
        bar.addWidget(self.pill)
        bar.addStretch(1)
        self.btn_theme = IconButton("sun", 32, tip="Cycle theme")
        self.btn_settings = IconButton("gear", 32, tip="Settings")
        self.btn_min = IconButton("minimize", 32, tip="Minimize")
        self.btn_close = IconButton("close", 32, danger=True, tip="Close")
        for b in (self.btn_theme, self.btn_settings, self.btn_min, self.btn_close):
            bar.addWidget(b)
        lay.addLayout(bar)
        lay.addSpacing(14)

        # ---- hero --------------------------------------------------------
        self.hero = HeroButton()
        lay.addWidget(self.hero)
        lay.addSpacing(12)

        # ---- capture mode (region live; rest gated, no backend yet) ------
        self.mode = Segmented([("region", "Region"), ("window", "Window"),
                               ("monitor", "Screen")])
        self.mode.set_option_enabled(1, False, MODE_REASON)
        self.mode.set_option_enabled(2, False, MODE_REASON)
        lay.addWidget(self.mode)
        lay.addSpacing(14)

        # ---- language pair ----------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(10)
        colL, colR = QVBoxLayout(), QVBoxLayout()
        colL.setSpacing(7)
        colR.setSpacing(7)
        colL.addWidget(_caption("From"))
        self.src = LangSelector(
            rows=languages.FROM_LANGS,
            badge_of=lambda i, r: languages.FROM_SHORT[i],
            label_of=lambda i, r: r[0],
            index=0, align="left")
        colL.addWidget(self.src)
        colR.addWidget(_caption("To"))
        self.dst = LangSelector(
            rows=languages.TO_LANGS,
            badge_of=lambda i, r: r[1].split("-")[0].upper(),
            label_of=lambda i, r: r[0],
            index=0, align="right")
        colR.addWidget(self.dst)
        self.swap = SwapButton()
        mid = QVBoxLayout()
        mid.setSpacing(7)
        spacer = _caption("From")  # invisible alignment row
        spacer.setStyleSheet("color: transparent; background: transparent;")
        mid.addWidget(spacer)
        mid.addWidget(self.swap)
        mid.addStretch(1)
        row.addLayout(colL, 1)
        row.addLayout(mid)
        row.addLayout(colR, 1)
        lay.addLayout(row)
        lay.addSpacing(14)

        # ---- recent pairs --------------------------------------------------
        self.chips_row = QHBoxLayout()
        self.chips_row.setSpacing(8)
        self.recents_wrap = QWidget()
        self.recents_wrap.setLayout(self.chips_row)
        lay.addWidget(self.recents_wrap)
        lay.addSpacing(6)

        # ---- footer: honest engine line ------------------------------------
        lay.addStretch(1)
        eng = make_label(ENGINE_LINE, 8.5, _QFont.Normal, "muted")
        eng.setAlignment(Qt.AlignCenter)
        lay.addWidget(eng)

        # ---- wiring ----------------------------------------------------------
        self.src.changed.connect(self._on_from_changed)
        self.dst.changed.connect(self._on_to_changed)
        self.swap.clicked.connect(self._swap_languages)
        self.hero.clicked.connect(self.win.trigger_snip)
        self.pill.clicked.connect(self.win.on_status_clicked)
        self.btn_theme.clicked.connect(self._cycle_theme)
        self.btn_settings.clicked.connect(lambda: self.win.goto(1))
        self.btn_min.clicked.connect(self.win.showMinimized)
        self.btn_close.clicked.connect(self.win.close)
        self.mode.changed.connect(
            lambda i: self.win.toast.show_text(f"Capture mode: {self.mode.options[i][1]}"))

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

    def _on_to_changed(self, idx):
        name, code = languages.TO_LANGS[idx]
        s = self.win.store.settings
        s.dest_lang_name = name
        s.dest_lang = code
        print(f"Destination language updated: {name}")
        self.win.store.save()
        self._update_swap_state()

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
            self.chips_row.addWidget(_caption("Recent"))
            self.chips_row.addSpacing(4)
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
                    lambda _c, e=dict(entry): self._apply_recent(e))
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
        self.win.set_theme(nxt)

    def refresh_theme_icon(self):
        self.btn_theme.icon = "moon" if self.win.theme_name == "day" else "sun"
        self.btn_theme.update()


# ==========================================================================
#  Settings page (in-window; scrolls so it can never clip)
# ==========================================================================
class SettingsPage(QWidget):
    back = pyqtSignal()
    theme_picked = pyqtSignal(str)

    FILL_PRESETS = ["#6366F1", "#22D3EE", "#34D399", "#FBBF24", "#FB7185"]
    TEXT_PRESETS = ["#FFFFFF", "#000000", "#FDE68A", "#7DD3FC", "#86EFAC"]

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.pst = self._preview_state()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 22)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.btn_back = IconButton("back", 36, tip="Back")
        head.addWidget(self.btn_back)
        head.addWidget(make_label("Settings", 15, _QFont.Bold, "text"))
        head.addStretch(1)
        lay.addLayout(head)
        lay.addSpacing(10)

        # ---- scrollable content -----------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 1px; }"
            "QScrollBar::handle:vertical { background: rgba(128,128,128,110); border-radius: 3px; min-height: 28px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }")
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 4, 0)
        cl.setSpacing(10)

        c0 = Card(20)
        l0 = QVBoxLayout(c0)
        l0.setContentsMargins(16, 12, 16, 12)
        l0.setSpacing(6)
        l0.addWidget(make_label("Appearance", 9.5, _QFont.DemiBold, "soft"))
        self.picker = ThemePicker(self.win.theme_name)
        self.picker.picked.connect(self.theme_picked)
        l0.addWidget(self.picker)
        cl.addWidget(c0)

        self.preview = OverlayPreview(self.pst)
        cl.addWidget(self.preview)

        c1 = Card(20)
        l1 = QVBoxLayout(c1)
        l1.setContentsMargins(16, 12, 16, 12)
        l1.setSpacing(6)
        l1.addWidget(make_label("Capture box", 9.5, _QFont.DemiBold, "soft"))
        s = self.win.store.settings
        self.r_fill = ColorRow("Selection fill", self.FILL_PRESETS, s.fill_color)
        self.r_fop = SliderRow("Selection opacity", 0, 100, int(s.opacity * 100), "%")
        self.r_bw = SliderRow("Border width", 1, 10, s.line_width, " px")
        for w in (self.r_fill, self.r_fop, self.r_bw):
            l1.addWidget(w)
        cl.addWidget(c1)

        c2 = Card(20)
        l2 = QVBoxLayout(c2)
        l2.setContentsMargins(16, 12, 16, 12)
        l2.setSpacing(6)
        l2.addWidget(make_label("Overlay text", 9.5, _QFont.DemiBold, "soft"))
        self.r_text = ColorRow("Text color", self.TEXT_PRESETS, s.text_color)
        self.r_obg = SliderRow("Overlay background", 0, 100, int(s.alpha * 100), "%")
        self.r_font = SliderRow("Font size", 5, 25, s.font_size, " pt")
        for w in (self.r_text, self.r_obg, self.r_font):
            l2.addWidget(w)
        cl.addWidget(c2)
        cl.addStretch(1)
        scroll.setWidget(content)
        # AFTER setWidget: QScrollArea re-enables autoFill on the scrolled
        # widget, which Fusion fills with Window #f0f0f0 (white panel bug).
        content.setAutoFillBackground(False)
        lay.addWidget(scroll, 1)
        lay.addSpacing(10)

        foot = QHBoxLayout()
        self.btn_reset = PillButton("Reset defaults", "danger", 138)
        self.btn_done = PillButton("Done", "primary", 104)
        foot.addWidget(self.btn_reset)
        foot.addStretch(1)
        foot.addWidget(self.btn_done)
        lay.addLayout(foot)

        self.r_fill.colorChanged.connect(
            lambda c: self._set("fill_color", c.name()))
        self.r_text.colorChanged.connect(
            lambda c: self._set("text_color", c.name()))
        self.r_fop.valueChanged.connect(
            lambda v: self._set("opacity", v / 100.0))
        self.r_bw.valueChanged.connect(
            lambda v: self._set("line_width", v))
        self.r_obg.valueChanged.connect(
            lambda v: self._set("alpha", v / 100.0))
        self.r_font.valueChanged.connect(
            lambda v: self._set("font_size", v))
        self.btn_reset.clicked.connect(self.reset)
        self.btn_done.clicked.connect(self.back.emit)
        self.btn_back.clicked.connect(self.back.emit)

    # ---- store <-> preview -----------------------------------------------
    def _preview_state(self):
        s = self.win.store.settings
        return {"fill": s.fill_color, "fill_op": int(s.opacity * 100),
                "border": s.line_width, "text": s.text_color,
                "ov_bg": int(s.alpha * 100), "font": s.font_size}

    def _sync_preview(self):
        self.pst.update(self._preview_state())
        self.preview.update()

    def _set(self, key, value):
        setattr(self.win.store.settings, key, value)
        self.win.store.save()
        self._sync_preview()

    def reset(self):
        self.win.store.reset()  # keeps recent pairs (history, not config)
        if self.win.theme_name != self.win.store.settings.theme:
            self.win.set_theme(self.win.store.settings.theme)
        self._refresh_from_store()

    def _refresh_from_store(self):
        s = self.win.store.settings
        self.picker.set_current(s.theme)
        self.r_fill.set_color(s.fill_color)
        self.r_text.set_color(s.text_color)
        self.r_fop.setValue(int(s.opacity * 100))
        self.r_bw.setValue(s.line_width)
        self.r_obg.setValue(int(s.alpha * 100))
        self.r_font.setValue(s.font_size)
        self._sync_preview()


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
        self.settings.theme_picked.connect(self.set_theme)
        QShortcut(QKeySequence("Alt+Shift+M"), self,
                  activated=self.trigger_snip)

        self.backend.start_flask_server(
            self.store.settings.source_lang_option)
        self.nativeEventFilter = register_hotkey(self.trigger_snip)
        self._theme_anim = None
        self._fade = None

    # ------------------------------------------------------------------ pages
    def _hug(self):
        """Size the window to the current page; recents chips grow it."""
        self.main.layout().activate()
        hint = max(1, self.stack.currentWidget().sizeHint().height())
        self.set_inner_size(WIN_W, hint)

    def goto(self, idx):
        if idx == self.stack.currentIndex():
            return
        page = self.stack.widget(idx)
        fx = QGraphicsOpacityEffect(page)
        fx.setOpacity(0.0)
        page.setGraphicsEffect(fx)
        self.stack.setCurrentIndex(idx)
        if idx == 0:
            self._hug()  # settings page scrolls inside the main-page height
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
        self.settings.picker.set_current(name)
        self.main.refresh_theme_icon()

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
            return  # repeated same-state poll: skip the pill entirely
        self._last_status = state
        main = getattr(self, "main", None)
        if main is None:
            return  # backend can report synchronously before MainPage exists
        text, key = HEALTH.get(state, HEALTH["starting"])
        main.pill.set_state(text, key)

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
            s.alpha, s.font_size, s.text_color)
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

    _scratch = ("C:/Users/sezar/AppData/Local/hermes/profiles"
                "/lingolens-dev/cache/scratch")
    print(_snap(_win, f"{_scratch}/prism_main.png"))
    _win.goto(1)
    # Let the 260ms page-fade finish; otherwise the shot catches opacity 0.
    for _ in range(6):
        _app.processEvents()
        time.sleep(0.08)
    print(_snap(_win, f"{_scratch}/prism_settings.png"))
