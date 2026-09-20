# LingoLens - Agent Instructions

## Mission
Make the in-place translation overlay work and look native. After a screen snip, the user must
see the translated text drawn exactly where the source text was, on the source's own
background, so the region looks like the original screen already written in the target
language. No boxes, halos, ghost glyphs, or seams. Nothing else matters until this works on the
real Windows desktop.

Pipeline (already exists): capture.py (snip) -> detector.py (OpenVINO text boxes, crops) ->
ocr_server.py (Flask + EasyOCR, port 5000) -> overlay.py (group words -> lines -> blocks,
translate each block, remove source text, draw translation on ONE transparent window that
exactly covers the snipped region).

## Read order (before editing anything)
1. This file.
2. docs/OVERLAY_SPEC.md - full design, algorithms, numeric acceptance criteria, phase gates.
3. docs/reference/blend_reference.py - working, tested reference of the blending core.
4. docs/reference/qt_lifecycle_repro.py - reproduces the "overlay never appears" bug.
README.md, ARCHITECTURE.md, DEVELOPMENT_LOG.md, MIGRATION_PLAN.md contain unverified or wrong
claims (for example "overlay rendering verified", singleton detector, Tkinter overlays). Treat
them as history. Correct them in the last phase.

## Your constraints (read carefully)
- You are text-only. You cannot see screenshots or the overlay. Never write "looks right",
  "blends well", or "works" from imagination. Evidence is: (a) numbers printed by the harness,
  (b) PNG artifacts written to debug/ for the human to open. Say exactly what you verified
  and what only the human can verify.
- Earlier work declared success from unit tests that never touched rendering, and 7 of 29 test
  boxes were inverted (y_max < y_min) so they passed by accident. Green tests are not proof.
- The GUI cannot be driven by you. Automated checks run headless with QT_QPA_PLATFORM=offscreen.
  Real-desktop checks are done by the human; you prepare the exact steps and ask for results.
- Platform: Windows, Git Bash. Use .venv/Scripts/python.exe and forward slashes.
- Make small, targeted edits. Re-read the file region after each edit. Run py_compile after every
  edit. Avoid rewriting large files in one tool call.

## Verified defects (line numbers approximate; confirm with grep)
1. Overlay is destroyed at once. overlay.py:434 keeps the window in a local variable; when
   show_translations() returns, Python deletes the parentless widget, no window remains, Qt quits,
   capture.py:179 exec_() returns, process exits. Reproduced: docs/reference/qt_lifecycle_repro.py A.
   Fix: module-level registry of live overlays; app.setQuitOnLastWindowClosed(False); quit only
   when the registry becomes empty.
2. Wrong window size. overlay.py:431-434 sizes the window from OCR box extents + 40 px, not the
   snip. The full-size pixmap is then scaled into that rect (paintEvent, line 334): distortion and
   misplacement. Use the captured image width/height and the snip origin.
3. Text drawn wrong. overlay.py:317-325 uses drawText(x, y, str) (y is the BASELINE, so text lands
   above the box), no wrapping, no fitting, QFont("fixedsys", n) mixing point and pixel sizes, fixed
   user colour with a fake outline. Use drawText(QRect, flags, text), setPixelSize, fit to the box.
4. Background removal smudges. overlay.py:160-190 runs one full-image cv2.inpaint per word with a
   rectangle mask (ghost blobs, slow). Use ring-median fill for flat backgrounds and ONE inpaint
   call over glyph masks for textured ones (see reference).
5. Grouping merges unrelated text. Lines join across any horizontal gap; paragraphs ignore
   horizontal alignment. Measured on a 4-block fixture: current code returns 2 paragraphs.
6. Dismiss handler is dead. overlay.py:457 creates _DismissFilter with no reference (garbage
   collected) and checks event type 17, which is QEvent.Show, not a mouse press. Delete it; use
   mousePressEvent and keyPressEvent on the window.
7. Detector keeps junk. detector.py:92-107 applies no confidence threshold (conf only orders NMS),
   does not clamp boxes to the image, and can produce empty crops: cv2.imwrite raises on those
   (verified), which aborts the whole snip. Unclamped x_max also gets encoded into the crop
   filename, so the OCR key can disagree with the real crop. Add CONF_THRESHOLD (start 0.3, tune
   with evidence), clamp, skip degenerate boxes, log raw vs kept counts.
8. Capture race. capture.py:137-139 repaints and calls ImageGrab.grab while the tinted selection
   window may still be composited (it is closed only at line 148), which can tint the sampled
   background. Fix: freeze-frame capture (grab the screen BEFORE showing the selection UI, crop from
   that). Also call QApplication.setAttribute(Qt.AA_DisableHighDpiScaling) before creating the
   QApplication so Qt pixels equal ImageGrab pixels.
9. Smaller: translator.py:1 imports googletrans at top level but requirements.txt lacks it, so a clean
   install raises ImportError; and googletrans 4.0.2 (current PyPI) is async, so translate() returns a
   coroutine (verified) and the "primary" path silently never works. Make it optional, prefer
   deep_translator, add timeouts, chunk long text for MyMemory. The alpha setting is
   unused (see spec); failures are invisible because capture.py logs only to a console nobody sees
   (add a rotating file log under logs/); each hotkey press starts a new process so the
   "singleton" detector reloads every snip (acceptable for now, do not redesign).

## Target behaviour (the contract)
- One frameless, always-on-top, translucent window at the snip origin with exactly the snip size,
  in physical pixels. It is fully transparent except "patches" over translated blocks.
- Each patch = source pixels with the text removed + the translation on top. Outside patches the
  live screen shows through unchanged (measured: 0 changed pixels).
- Translation unit is a block: single word/label, sentence line, or paragraph (grouped by geometry).
- Text colour comes from the source (glyph pixel median), guarded by WCAG contrast >= 4.5.
- Font size follows the source (median line height / 1.25), largest pixel size that fits, floor at
  0.6x source. Translations run 20-50% longer: the source box is a minimum, not a limit; expand into
  the detected container and free space, keep inner padding, stop at neighbouring blocks.
- Alignment follows the source (left by default; centre when the source was centred in its container).
- Right-to-left targets (ar, ur, he, fa) use right-to-left layout.
- Dismiss: any mouse button, or Esc when focused. Overlay never blocks the app from exiting.
- User settings keep their keys. Text colour and font size settings become fallbacks only; alpha is
  ignored for patches (see docs/OVERLAY_SPEC.md section 7).

## Rules of engagement
- Diagnose first. For each defect: write a failing test or repro, then fix, then show it pass.
- Work one phase at a time (below). Commit after each green phase. Never start the next phase until
  the current gate passes and you have written the phase report.
- Do not rename or move files, change the Flask /ocr contract (returns {"x_min,x_max,y_min,y_max": text}), change the
  Control Center UI, or rename settings keys. Do not refactor unrelated code.
- Never delete or weaken a test to get green. If a test is wrong (inverted boxes), fix its data and
  say why in the commit message.
- No new runtime dependencies. pytest is allowed as a dev dependency.
- If a decision changes user-visible behaviour, or you fail the same check 3 times, stop and ask
  the human with the evidence you have.
- Keep pure logic (grouping, colour, fitting) free of window code so it runs headless.
- After each phase update docs/PROGRESS.md (phase, status, decisions, open questions, how to resume).

## Phases and gates (details in docs/OVERLAY_SPEC.md section 10)
- P0 Baseline: branch overlay-fix, py_compile, run tests, add failing repro tests + debug dump
  (LINGOLENS_DEBUG=1) + replay tool. Gate: repro tests fail on old code for the stated reasons.
- P1 Lifecycle and geometry (defects 1, 2, 6). Gate: lifecycle test passes; window rect equals
  snip rect in a test; HUMAN desktop check with debug outlines.
- P2 Detection and grouping (defects 5, 7 + inverted test data). Gate: fixture yields 32 -> 8 -> 4.
- P3 Blend renderer (defects 3, 4). Gate: all numeric checks in the spec pass on fixtures and on
  replayed real dumps; HUMAN visual check of debug/composite.png.
- P4 Capture integrity and DPI (defect 8). Gate: capture-vs-regrab difference check; HUMAN check on
  a scaled (125%/150%) display.
- P5 Robustness and docs (defect 9, RTL, CJK joining, doc corrections, dead code removal).

## Commands
```
.venv/Scripts/python.exe -m py_compile app.py python/*.py
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python -q
.venv/Scripts/python.exe docs/reference/blend_reference.py          # numeric acceptance table
.venv/Scripts/python.exe docs/reference/qt_lifecycle_repro.py A     # must show EXITED EARLY on old code
.venv/Scripts/python.exe python/tools/replay.py debug/<stamp>        # re-render a real dump offline
.venv/Scripts/python.exe python/ocr_server.py 1                     # OCR server (human/e2e only)
```
Human e2e (agent prepares, human runs): start the Control Center with LINGOLENS_DEBUG=1, press
Alt+Shift+M, drag a region. Artifacts land in debug/<timestamp>/.

## Facts you need
- Flask: http://localhost:5000, GET /health, POST /ocr {folder_location}; result keys are
  "x_min,x_max,y_min,y_max" (crop filename without .png), values are recognised text.
- capture.py CLI args: dest fill_color opacity line_width alpha font_size text_color (all strings).
- OpenVINO model path must stay absolute (_this_dir / "models" / ...).
- DPI: SetProcessDpiAwareness(2) is called before Qt imports; keep that order.
- Settings live in settings.json (gitignored): source_lang_option, dest_lang, fill_color,
  text_color, opacity, line_width, alpha, font_size.

## Report format after every phase
Changed (files, one line each) / Evidence (paste harness output) / Not verified (what needs the
human) / Decisions / Next step. Keep it short and factual.

## Out of scope
New features, UI redesign, new languages, packaging, moving OCR into a QThread, replacing Flask,
multi-monitor support (note as future work only).
