"""LingoLens Control Center UI package.

Layout of the main window (action only, no marketing copy):

    [logo/engine-status LingoLens]  [theme]  [settings]  [–]  [×]
    [      Snip & Translate  ·  Alt+Shift+M      ]
    [ FROM ▾ ]  [swap]  [ TO ▾ ]
    [ chips ]              <- hidden when empty

NOTE: this module must stay Qt-free. ``app.py`` calls
:func:`ui.dpi.ensure_dpi_awareness` BEFORE any PyQt5 import — importing
anything from ``ui`` that pulls in Qt at module top would silently break
that ordering and reintroduce blurry text on scaled displays.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "settings.json"
