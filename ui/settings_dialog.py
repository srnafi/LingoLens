"""Settings dialog — ALL appearance knobs live here, nowhere else.

Capture box (selection fill, opacity, border width) + overlay text
(color, background strength, font size) + reset-to-defaults. Every
control writes straight into SettingsStore; there is no apply step.
"""
from PyQt5 import QtCore, QtWidgets

from ui import languages
from ui.settings_store import SettingsStore


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, store, on_appearance_changed=None, parent=None):
        super().__init__(parent)
        self.store = store
        self._on_change = on_appearance_changed
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        self._build()

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(6)

        # ---- capture box group ----
        cap_group = QtWidgets.QGroupBox("Capture box")
        cap_layout = QtWidgets.QVBoxLayout()
        fill_row = QtWidgets.QHBoxLayout()
        fill_row.addWidget(QtWidgets.QLabel("Selection fill:"))
        self._fill_swatch = QtWidgets.QFrame()
        self._fill_swatch.setObjectName("swatch")
        self._fill_swatch.setFixedSize(30, 20)
        fill_row.addWidget(self._fill_swatch)
        fill_btn = QtWidgets.QPushButton("Choose…")
        fill_btn.clicked.connect(
            lambda: self._pick_color("fill", self._fill_swatch))
        fill_row.addStretch()
        fill_row.addWidget(fill_btn)
        cap_layout.addLayout(fill_row)
        self._opacity_lbl = QtWidgets.QLabel()
        cap_layout.addWidget(self._opacity_lbl)
        self._opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._opacity.setRange(0, 100)
        self._opacity.valueChanged.connect(self._update_opacity)
        cap_layout.addWidget(self._opacity)
        self._width_lbl = QtWidgets.QLabel()
        cap_layout.addWidget(self._width_lbl)
        self._width = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._width.setRange(1, 10)
        self._width.valueChanged.connect(self._update_width)
        cap_layout.addWidget(self._width)
        cap_group.setLayout(cap_layout)
        layout.addWidget(cap_group)

        # ---- overlay text group ----
        txt_group = QtWidgets.QGroupBox("Overlay text")
        txt_layout = QtWidgets.QVBoxLayout()
        tc_row = QtWidgets.QHBoxLayout()
        tc_row.addWidget(QtWidgets.QLabel("Text color:"))
        self._text_swatch = QtWidgets.QFrame()
        self._text_swatch.setObjectName("swatch")
        self._text_swatch.setFixedSize(30, 20)
        tc_row.addWidget(self._text_swatch)
        tc_btn = QtWidgets.QPushButton("Choose…")
        tc_btn.clicked.connect(
            lambda: self._pick_color("text", self._text_swatch))
        tc_row.addStretch()
        tc_row.addWidget(tc_btn)
        txt_layout.addLayout(tc_row)
        self._alpha_lbl = QtWidgets.QLabel()
        txt_layout.addWidget(self._alpha_lbl)
        self._alpha = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._alpha.setRange(0, 100)
        self._alpha.valueChanged.connect(self._update_alpha)
        txt_layout.addWidget(self._alpha)
        self._font_lbl = QtWidgets.QLabel()
        txt_layout.addWidget(self._font_lbl)
        self._font = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._font.setRange(5, 25)
        self._font.valueChanged.connect(self._update_font)
        txt_layout.addWidget(self._font)
        txt_group.setLayout(txt_layout)
        layout.addWidget(txt_group)

        self._refresh_swatches()
        # Set slider positions without firing save-churn.
        s = self.store.settings
        for slider, val in ((self._opacity, int(s.opacity * 100)),
                            (self._width, s.line_width),
                            (self._alpha, int(s.alpha * 100)),
                            (self._font, s.font_size)):
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)
        self._update_labels()

        btn_row = QtWidgets.QHBoxLayout()
        reset_btn = QtWidgets.QPushButton("Reset defaults")
        reset_btn.setStyleSheet("color: #f38ba8;")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        close_btn = QtWidgets.QPushButton("Done")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ---- internals ----
    def _refresh_swatches(self):
        s = self.store.settings
        self._fill_swatch.setStyleSheet(
            f"QFrame#swatch {{ background-color: {s.fill_color}; }}")
        self._text_swatch.setStyleSheet(
            f"QFrame#swatch {{ background-color: {s.text_color}; }}")

    def _update_labels(self):
        s = self.store.settings
        self._opacity_lbl.setText(
            f"Selection opacity: {int(s.opacity * 100)}%")
        self._width_lbl.setText(f"Border width: {s.line_width}px")
        self._alpha_lbl.setText(f"Overlay background: {int(s.alpha * 100)}%")
        self._font_lbl.setText(f"Font size: {s.font_size}pt")

    def _pick_color(self, which, swatch):
        col = QtWidgets.QColorDialog.getColor()
        if col.isValid():
            if which == "fill":
                self.store.settings.fill_color = col.name()
            else:
                self.store.settings.text_color = col.name()
            swatch.setStyleSheet(
                f"QFrame#swatch {{ background-color: {col.name()}; }}")
            self.store.save()

    def _update_opacity(self, val):
        self.store.settings.opacity = val / 100.0
        self._opacity_lbl.setText(f"Selection opacity: {val}%")
        self.store.save()

    def _update_width(self, val):
        self.store.settings.line_width = val
        self._width_lbl.setText(f"Border width: {val}px")
        self.store.save()

    def _update_alpha(self, val):
        self.store.settings.alpha = val / 100.0
        self._alpha_lbl.setText(f"Overlay background: {val}%")
        self.store.save()

    def _update_font(self, val):
        self.store.settings.font_size = val
        self._font_lbl.setText(f"Font size: {val}pt")
        self.store.save()

    def _reset(self):
        self.store.reset()
        if self._on_change:
            self._on_change("appearance")
        self._refresh_swatches()
        s = self.store.settings
        for slider, val in ((self._opacity, int(s.opacity * 100)),
                            (self._width, s.line_width),
                            (self._alpha, int(s.alpha * 100)),
                            (self._font, s.font_size)):
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)
        self._update_labels()
        print("Settings reset to defaults (from dialog)")


def open_settings(store, on_appearance_changed=None, parent=None):
    """Build + run the Settings dialog modally."""
    SettingsDialog(store, on_appearance_changed, parent).exec_()
