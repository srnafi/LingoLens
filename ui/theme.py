"""Linear-minimal dark theme — one QSS string + status-pill style map.

Flat fills + one linear gradient. QSS supports qlineargradient; it does
NOT support blur/glow, so depth comes from the drop-shadow effect the
main window applies in code.
"""
LINEAR_QSS = """
QWidget {
    background-color: transparent;
    color: #f4f4f8;
    font-family: 'Segoe UI', Inter, Arial, sans-serif;
    font-size: 10pt;
}
QWidget#card {
    background-color: #0d0f14;
    border: 1px solid #2a2d36;
    border-radius: 14px;
}
QLabel#appTitle {
    font-size: 12pt;
    font-weight: 800;
}
QLabel#captionLabel {
    color: #6c7086;
    font-size: 8.5pt;
    font-weight: 700;
}
QPushButton {
    background-color: #14161d;
    color: #e8eaf2;
    border: 1px solid #2a2d36;
    border-radius: 8px;
    padding: 8px 12px;
}
QPushButton:hover {
    background-color: #1a1d26;
    border-color: #5e6ad2;
}
QPushButton:pressed {
    background-color: #101218;
}
QPushButton:disabled {
    color: #565b70;
    border-color: #1c1e24;
    background-color: #101218;
}
QPushButton:focus {
    outline: none;
    border-color: #5e6ad2;
}
QPushButton#ctaButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #707aea, stop:0.5 #5e6ad2, stop:1 #4953ad);
    color: #ffffff;
    font-size: 12pt;
    font-weight: 700;
    border: 1px solid #828cea;
    border-radius: 12px;
    padding: 13px;
}
QPushButton#ctaButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7d87f2, stop:0.5 #6a74de, stop:1 #515bb8);
    border-color: #929bf2;
}
QPushButton#ctaButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #5a64d6, stop:1 #3f4796);
}
QPushButton#statusButton {
    font-size: 9pt;
    font-weight: 700;
}
QPushButton#chipButton {
    border-radius: 12px;
    padding: 5px 13px;
    font-size: 9pt;
    font-weight: 600;
    color: #a5a9bd;
}
QPushButton#chipButton:hover {
    color: #ffffff;
}
QPushButton#toolButton {
    font-size: 13pt;
    padding: 4px 10px;
    min-width: 42px;
}
QPushButton#winButton {
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #8b8fa3;
    font-size: 11pt;
    min-width: 34px;
    padding: 4px 6px;
}
QPushButton#winButton:hover {
    background-color: #1c1f27;
    color: #ffffff;
    border: none;
}
QPushButton#closeButton {
    background: transparent;
    border: none;
    border-radius: 7px;
    color: #8b8fa3;
    font-size: 11pt;
    min-width: 34px;
    padding: 4px 6px;
}
QPushButton#closeButton:hover {
    background-color: #e81123;
    color: #ffffff;
    border: none;
}
QComboBox {
    background-color: #14161d;
    border: 1px solid #2a2d36;
    border-radius: 8px;
    padding: 9px 12px;
    color: #e8eaf2;
}
QComboBox:hover {
    border-color: #5e6ad2;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox QAbstractItemView {
    background-color: #14161d;
    border: 1px solid #2a2d36;
    selection-background-color: #5e6ad2;
    selection-color: #ffffff;
    outline: none;
}
QDialog {
    background-color: #0d0f14;
}
QGroupBox {
    border: 1px solid #2a2d36;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 16px;
    padding-left: 12px;
    padding-right: 12px;
    padding-bottom: 12px;
    font-weight: 700;
    color: #8b8fa3;
    font-size: 9pt;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: #2a2d36;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #5e6ad2;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #6c78dd;
}
QFrame#swatch {
    border: 1px solid #2a2d36;
    border-radius: 5px;
}
"""

STATUS_STYLE = {
    # state: (pill text, accent color)
    "ready": ("OCR ready", "#4ade80"),
    "starting": ("OCR starting", "#f9e2af"),
    "offline": ("OCR offline — retry", "#f38ba8"),
}
