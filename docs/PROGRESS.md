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

All 9 defects confirmed against current code on overlay-fix branch.

1. Overlay destroyed at once — overlay.py:434 local var, no registry, no setQuitOnLastWindowClosed.
2. Wrong window size — overlay.py:426-432 derives size from OCR boxes + 40px.
3. Text drawn wrong — overlay.py:317 QFont("fixedsys"), line 322 drawText(x,y,str) baseline.
4. Background removal smudges — overlay.py:160-187 per-word cv2.inpaint rectangle.
5. Grouping merges unrelated — overlay.py:126 no horizontal overlap/alignment guard.
6. Dismiss handler dead — overlay.py:457-466 eventFilter on QEvent.Show (type 17), no parent.
7. Detector keeps junk — detector.py:92-100 no conf threshold, no clamp, no empty-crop guard.
8. Capture race — capture.py:137-139 grab while tinted UI visible, no AA_DisableHighDpiScaling.
9. Translator — translator.py:1 googletrans import at top, missing from requirements.txt.

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
