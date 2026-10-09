"""Settings dialog — ALL appearance knobs live here, nowhere else.

FramelessDialog shell + kit parts (Section cards, SliderRow, ColorButton,
danger Reset + primary Done). Every control writes straight into
SettingsStore; there is no apply step.
"""
from PyQt5.QtWidgets import QHBoxLayout

from ui.settings_store import SettingsStore
from ui.ui_kit import (Button, ColorButton, FramelessDialog, Section,
                       SliderRow, snapshot)


class SettingsDialog(FramelessDialog):
    def __init__(self, store, on_appearance_changed=None, parent=None):
        super().__init__("Settings", parent, width=440)
        self.store = store
        self._on_change = on_appearance_changed
        self._build()

    def _build(self):
        s = self.store.settings

        cap = Section("Capture box")
        self.fill = cap.add_row("Selection fill",
                                ColorButton(s.fill_color))
        self.fill.colorChanged.connect(self._update_fill)
        self.opacity = cap.add(SliderRow("Selection opacity", 0, 100,
                                         int(s.opacity * 100), "%"))
        self.opacity.valueChanged.connect(self._update_opacity)
        self.border = cap.add(SliderRow("Border width", 1, 10,
                                        s.line_width, " px"))
        self.border.valueChanged.connect(self._update_width)
        self.body.addWidget(cap)

        ov = Section("Overlay text")
        self.text = ov.add_row("Text color", ColorButton(s.text_color))
        self.text.colorChanged.connect(self._update_text)
        self.overlay = ov.add(SliderRow("Overlay background", 0, 100,
                                        int(s.alpha * 100), "%"))
        self.overlay.valueChanged.connect(self._update_alpha)
        self.font = ov.add(SliderRow("Font size", 5, 25, s.font_size, " pt"))
        self.font.valueChanged.connect(self._update_font)
        self.body.addWidget(ov)

        foot = QHBoxLayout()
        reset = Button("Reset defaults", "danger")
        reset.clicked.connect(self._reset)
        done = Button("Done", "primary")
        done.clicked.connect(self.accept)
        foot.addWidget(reset)
        foot.addStretch()
        foot.addWidget(done)
        self.body.addLayout(foot)

    # ---- internals (store writes, no apply step) ----
    def _update_fill(self, color):
        self.store.settings.fill_color = color.name()
        self.store.save()

    def _update_text(self, color):
        self.store.settings.text_color = color.name()
        self.store.save()

    def _update_opacity(self, val):
        self.store.settings.opacity = val / 100.0
        self.store.save()

    def _update_width(self, val):
        self.store.settings.line_width = val
        self.store.save()

    def _update_alpha(self, val):
        self.store.settings.alpha = val / 100.0
        self.store.save()

    def _update_font(self, val):
        self.store.settings.font_size = val
        self.store.save()

    def _reset(self):
        self.store.reset()
        if self._on_change:
            self._on_change("appearance")
        s = self.store.settings
        self.fill.setColor(s.fill_color)
        self.text.setColor(s.text_color)
        for row, val in ((self.opacity, int(s.opacity * 100)),
                         (self.border, s.line_width),
                         (self.overlay, int(s.alpha * 100)),
                         (self.font, s.font_size)):
            row.setValue(val)
        print("Settings reset to defaults (from dialog)")


def open_settings(store, on_appearance_changed=None, parent=None):
    """Build + run the Settings dialog modally."""
    SettingsDialog(store, on_appearance_changed, parent).exec_()


if __name__ == "__main__":  # headless check: QT_QPA_PLATFORM=offscreen
    import sys
    from PyQt5.QtWidgets import QApplication
    from ui.ui_kit import apply_theme, enable_hidpi, lint

    enable_hidpi()
    _app = QApplication(sys.argv)
    apply_theme(_app)
    _dlg = SettingsDialog(SettingsStore(":memory:"))
    import os as _os
    _out = _os.environ.get("LINGOLENS_SNAP",
                           "C:/Users/sezar/AppData/Local/hermes/profiles"
                           "/lingolens-dev/cache/scratch/kit_settings.png")
    print(snapshot(_dlg, _out))
    print("lint:", lint(_dlg))
