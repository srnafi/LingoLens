# LingoLens Overlay Fix — Progress

## Phase Table

| Phase | Goal | Status | Gate |
|-------|------|--------|------|
| P0 Baseline | branch, py_compile, existing tests, failing repros, debug dump, replay tool | DONE | repro tests fail on old code for stated reasons |
| P1 Lifecycle & geometry | defects 1, 2, 6 | DONE | 6 P1 tests pass; debug dump wired into show_translations; 8 P2-P5 defects still failing |
| P2 Detection & grouping | defects 5, 7 + inverted test data | PENDING | 32 -> 8 -> 4 |
| P3 Blend renderer | defects 3, 4 | PENDING | numeric checks pass on fixtures + real dumps |
| P4 Capture integrity & DPI | defect 8 | PENDING | capture-vs-regrab diff check |
| P5 Robustness & docs | defect 9, RTL, CJK, doc corrections | PENDING | full test run, human samples |

## Defect Confirmation (against actual code)

Defects 1, 2, 6 FIXED in P1. Defects 3, 4, 5, 7, 8, 9 still present.

FIXED:
1. Overlay destroyed at once -- FIXED: _OVERLAYS registry, destroyed() -> _on_overlay_closed,
   setQuitOnLastWindowClosed(False). OverlayWindow uses Qt.Tool flag.
2. Wrong window size -- FIXED: snip_w_img/snip_h_img from capture_bgr.shape[:2].
3. Text drawn wrong -- overlay.py still uses QFont("Arial") (fixed from "fixedsys"),
   drawText(dx, dy, t_text) (still baseline mode, not QRect). Defect 3 NOT fully fixed;
   belongs to P3 (blend renderer).
4. Background removal smudges -- _reconstruct_background still per-word rectangle inpaint.
   Defect 4 NOT fixed; belongs to P3.
5. Grouping merges unrelated -- _group_lines_into_paragraphs still no alignment/overlap guard.
   Defect 5 NOT fixed; belongs to P2.
6. Dismiss handler dead -- FIXED: deleted _DismissFilter; now mousePressEvent + keyPressEvent.
7. Detector keeps junk -- detector.py unchanged. Defect 7 NOT fixed; belongs to P2.
8. Capture race -- capture.py: added AA_DisableHighDpiScaling in __main__ (setup done).
   Freeze-frame capture NOT implemented; belongs to P4.
9. Translator -- translator.py unchanged (top-level googletrans import). Defect 9 NOT fixed;
   belongs to P5.

## Environment

- Python 3.11.16 (.venv), PyQt5 5.15.2, openvino 2026.4.0, deep_translator 1.9.1 (sync, not async).
- googletrans NOT installed (confirmed). deep_translator GoogleTranslator.translate is synchronous.
- Existing tests (test_overlay.py, test_pipeline.py) CANNOT BE COLLECTED: import of overlay.py triggers translator.py which does `from googletrans import Translator` at top level — ModuleNotFoundError.

## Decisions

- P0: Will create conftest.py that stubs googletrans so existing tests can at least be collected, allowing baseline test run. Will NOT fix defect 9 in P0 (that's P5) — only stub for test collection.
- P0: New repro tests will target the real code paths (lifecycle, geometry, grouping count, removal metrics).

## Open Questions

- Defect 9 spec text says deep_translator 4.0.2 googletrans is async, but installed googletrans is missing entirely and deep_translator is sync. Need to verify actual deep_translator chunking limits against 1.9.1.

## How to Resume

```
cd F:/LingoLens
.venv/Scripts/python.exe -m py_compile app.py python/*.py
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python -q
.venv/Scripts/python.exe docs/reference/blend_reference.py
.venv/Scripts/python.exe docs/reference/qt_lifecycle_repro.py A B C
```
