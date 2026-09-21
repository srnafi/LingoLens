# LingoLens Overlay Spec

Read fully before editing code. `AGENTS.md` is the short version; this is the authority.
Everything marked **(measured)** was reproduced on the current code with the reference scripts in
`docs/reference/`. Everything marked **(human)** can only be verified on the real Windows desktop.

---------------------------------------------------------------------------------------------------

## 1. Visual target (in words, because you cannot see images)

The person snips a region. A moment later that region looks like the original screen, but its
text is in the target language. Concretely:

1. Each translated text sits where the source text was, in the same visual role (label, button
   caption, heading, paragraph).
2. The background behind it is the source's own background: solid colour, gradient, border,
   texture. No rectangle of a different colour, no halo, no blur, no shadow.
3. No trace of the source glyphs (no faint outlines, no coloured fringes from anti-aliasing).
4. Text colour matches the source's text colour; if that would be unreadable, black or white.
5. Font size is close to the source (within 0.6x to 1.0x); text never runs outside its
   container (button, card, banner) and never collides with neighbouring text.
6. Pixels outside the translated blocks are untouched: the overlay is transparent there and the
   live screen shows through.
7. It stays on screen until dismissed (click or Esc), then the process exits.

Symptoms of the failed attempt, reproduced on the current code **(measured)**:
- Overlay never stays visible (process exits about 0.6 s after the pipeline finishes).
- If it did stay: window 812x241 for a 900x420 snip, image squished to fit.
- Translated text painted above its box in a monospace bitmap font, single line, not wrapped.
- Grey/coloured "diamond" smears on backgrounds (per-word rectangle inpainting).
- 4 separate text blocks collapsed into 2 paragraphs, so unrelated strings were translated together.

The human keeps two screenshots (bad result, target result) in `docs/reference/`. You cannot open
them. Do not try. Work to the numbers in section 11 and let the human judge the PNGs.

---------------------------------------------------------------------------------------------------

## 2. Module layout after the fix

Keep existing file names and public entry points. Add small modules so logic is testable headless.

| File | Role | Headless-testable |
|---|---|---|
| `python/capture.py` | selection UI, freeze-frame capture, hands off to detector, guarantees process exit | partly |
| `python/detector.py` | OpenVINO detect; add pure `postprocess_predictions()` | yes (pure fn) |
| `python/ocr_server.py` | unchanged contract | n/a |
| `python/blocks.py` (new) | Word/Line/Block, grouping, text joining, constants | yes |
| `python/blend.py` (new) | removal, colours, container, fitting, RGBA overlay render, metrics | yes (`QT_QPA_PLATFORM=offscreen`) |
| `python/overlay.py` | `show_translations()` orchestration, `OverlayWindow`, registry, dismissal | partly |
| `python/debug_dump.py` (new) | writes `debug/<stamp>/` artifacts when `LINGOLENS_DEBUG=1` | yes |
| `python/tools/replay.py` (new) | re-renders a dump offline, prints metrics | yes |
| `python/tests/fixtures.py` (new) | synthetic screenshot with ground truth (copy `make_fixture` from the reference) | yes |
| `python/tests/test_*.py` (new) | see section 9 | yes |

Existing tests `python/test_overlay.py` and `python/test_pipeline.py` import helpers such as
`_parse_ocr_results`, `_group_words_into_lines`, `_group_lines_into_paragraphs`, `_line_bbox`,
`_paragraph_bbox`, `_estimate_font_size` from `overlay`. Either keep thin wrappers/re-exports in
`overlay.py`, or update the tests deliberately in the same commit and say so. Do not silently
delete them.

Rendering rule: never subclass or instantiate a window inside `blend.py`/`blocks.py`. `blend.py`
returns a `QImage` (Format_ARGB32_Premultiplied) and metrics; only `overlay.py` shows windows.

---------------------------------------------------------------------------------------------------

## 3. Coordinates

- Everything is in physical pixels. Images are snip-relative (origin = top-left of the snip).
- Overlay window: position = (x1, y1) screen coordinates of the snip, size = (width, height) of the
  captured image. Never derive size from OCR boxes.
- Before creating `QApplication` (in `capture.py` and in `overlay.py`'s `__main__`) call
  `QApplication.setAttribute(Qt.AA_DisableHighDpiScaling, True)` so Qt pixels equal `ImageGrab`
  pixels. Keep `SetProcessDpiAwareness(2)` before Qt imports.
- Log `QApplication.primaryScreen().devicePixelRatio()`; warn if it is not 1.0.
- Assert (log an ERROR, do not crash) that `captured_image.shape[:2] == (y2 - y1, x2 - x1)`. A
  mismatch means a DPI scaling problem.
- Multi-monitor is out of scope. Note in the final report that `pyautogui.size()` and the capture
  widget cover the primary monitor only.

---------------------------------------------------------------------------------------------------

## 4. Process and Qt lifecycle

### 4.1 Root cause **(measured)**
`docs/reference/qt_lifecycle_repro.py A` reproduces it: the overlay is created in a local
variable, `show_translations()` returns, Python deletes the parentless widget, no visible window
remains, Qt ends the event loop, the process exits. Variants B and C (registry, plus
`setQuitOnLastWindowClosed(False)`) survive.

### 4.2 Required behaviour
- `capture.py` `__main__`: `app.setQuitOnLastWindowClosed(False)`.
- Every exit path ends with either an open overlay or an explicit `QApplication.quit()`:
  Esc/Q in the selection UI, selection smaller than 10 px, no text detected, OCR/Flask down,
  translation failure, any exception (log the traceback, then quit).
- `overlay.py`: module-level `_OVERLAYS: list`. `present_overlay(qimage, x, y)` creates the window,
  appends it, and removes it when it closes. When the list becomes empty call
  `QApplication.quit()` (via `QTimer.singleShot(0, ...)`).
- Do the heavy pipeline after the selection window is gone: in `mouseReleaseEvent` compute the rect,
  `self.hide()`, then `QTimer.singleShot(50, run_pipeline)`. Do not run OCR inside the mouse handler.
- Create and touch Qt widgets on the GUI thread only. Translation may use the thread pool
  (network only); fonts, painters and windows stay on the GUI thread.
- Log to a rotating file (`logs/lingolens.log`, 1 MB x 3) in `capture.py`. The console is invisible
  when launched from the Control Center. Add `logs/` and `debug/` to `.gitignore`.

### 4.3 OverlayWindow
- Flags: `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`; attribute
  `WA_TranslucentBackground`. Background not auto-filled.
- `resize(w, h)` and `move(x, y)` once, from the snip rect. No timers.
- `paintEvent`: `painter.setCompositionMode(QPainter.CompositionMode_Source)` then `drawImage(0, 0, img)`
  (no scaling). Keep the `QImage` alive as an attribute.
- `mousePressEvent`: any button closes the window. `keyPressEvent`: Esc or Q closes.
  `show()` then `raise_()` and `activateWindow()`. Windows may refuse focus for a window created by
  a background process, so click-to-dismiss is the primary path and Esc is a bonus **(human)**.
- Fully transparent pixels should let clicks through to the app below while patches capture clicks
  (layered-window behaviour) **(human)**. If not, document it; do not fight it.
- Debug aid: when `LINGOLENS_DEBUG_OUTLINE=1`, draw a 2 px cyan border around the window bounds and a
  1 px magenta outline around every patch. Used for the geometry check in P1.
- Delete `_DismissFilter`, `_init_timer`, `_ensure_paint`, the unused `dismiss` closure and unused imports.

---------------------------------------------------------------------------------------------------

## 5. Detection and OCR clean-up

`detector.py`:
- Extract a pure function `postprocess_predictions(preds, sx, sy, img_w, img_h, conf_thr, iou_thr)`
  returning kept boxes `[x0, y0, x1, y1, conf]`. Steps: drop all-zero rows; drop `conf < conf_thr`;
  scale; clamp to `[0, W]` x `[0, H]`; drop boxes narrower than 6 px or shorter than 6 px; NMS.
- `CONF_THRESHOLD = 0.3` default, override with env `LINGOLENS_CONF`. Keep `NMS_IOU = 0.1` as a named
  constant; change it only with evidence from dumps.
- Never write an empty crop; skip and log it. `cv2.imwrite` raises on an empty array **(measured)**, and
  `detect()` has no per-crop guard, so one degenerate box currently aborts the whole snip. Also build the
  crop filename from the CLAMPED coordinates; today an unclamped `x_max` is encoded in the name while the
  slice silently shortens, so the OCR key disagrees with the real crop.
- Log raw count, kept count, threshold, and per-stage milliseconds.
- Save `detections.json` (boxes + conf) into the debug dump.

`overlay.py`, after OCR:
- Drop words whose text has no letters or digits (icons recognised as `|`, `O`, `~`). Leaving them
  out means they are not repainted or removed.
- Keep the Flask contract: `/ocr` returns `{"x_min,x_max,y_min,y_max": text}`. Parse order carefully:
  x_min, x_max, y_min, y_max.

---------------------------------------------------------------------------------------------------

## 6. Grouping into blocks (`blocks.py`)

A block is the translation unit: a single word or label, one line, or a paragraph.
Reference implementation: `group_lines()` and `group_blocks()` in `docs/reference/blend_reference.py`.

Normalise first: enforce `x0 < x1`, `y0 < y1` (swap if needed), drop boxes under 3 px.

Constants (module top, named, documented):

| Name | Value | Meaning |
|---|---|---|
| `LINE_MERGE_CY` | 0.5 | word joins a line if `abs(cy - line_cy) < 0.5 * line_h` |
| `COLUMN_GAP` | 1.5 | split a line into separate segments if horizontal gap > 1.5 x height |
| `PARA_GAP` | 0.9 | lines are one block if vertical gap < 0.9 x average line height |
| `PARA_LEFT_ALIGN` | 1.0 | and left edges differ by less than 1.0 x line height |
| `PARA_HEIGHT_RATIO` | 0.6 to 1.6 | and heights are similar (a heading is not merged into body text) |

Also require horizontal overlap between consecutive lines. Two buttons far apart on one row become
two blocks. Two columns become separate blocks. A 3-line paragraph is one block.

Text joining: words joined with a space; if the majority of characters are CJK (Han, Hiragana,
Katakana, Hangul), join with an empty string.

Block record (dataclass): `words`, `lines`, `bbox`, `n_lines`, `text`, `src_px` (median line
height / 1.25, floor 9).

Baseline **(measured)**: on the reference fixture the current code returns 2 paragraphs; the correct
answer is 32 words -> 8 lines -> 4 blocks.

---------------------------------------------------------------------------------------------------

## 7. Blend renderer (`blend.py`)

Reference: `docs/reference/blend_reference.py` (tested; port the ideas, keep the numeric checks).

### 7.1 Remove source text
For each block: pad the box by 2 px (`BOX_PAD`), sample a 4 px ring outside it (`RING`), take the
per-channel median as the background colour and the mean channel std as `ring_std`.
- Flat (`ring_std < 6`): fill the whole padded box with the ring median. This also removes
  anti-aliasing and ClearType fringes.
- Textured/gradient: build a glyph mask (pixels whose colour distance from the background exceeds
  `max(28, 0.35 * max_distance)`), dilate 2x with a 3x3 kernel, OR all masks into one full-image mask,
  and call `cv2.inpaint(..., 3, INPAINT_TELEA)` ONCE for the whole image.
- Never inpaint per word and never inpaint rectangles on flat backgrounds **(measured: p99 colour
  deviation 109-157 for the old approach vs 0 for the new one)**.
- Busy backgrounds (photos, `ring_std > 25`): a smudged translation is worse than a visible
  backdrop. Fill the padded box with the ring median (fully opaque), flag `busy=True` in metrics.

### 7.2 Colours
- Background: ring median. Text colour: median of pixels at or above the 60th percentile of distance
  inside the glyph mask. If the mask is empty, fall back to the user `text_color` setting.
- WCAG contrast: if `contrast(fg, bg) < 4.5`, use black when the background luminance is above 0.4,
  else white. Functions are in the reference.

### 7.3 Container and free space
Translations are commonly 20-50% longer than the source, so the source box is a minimum.
- Container = bounding rect of the region around the block that has about the same colour, found by
  `cv2.floodFill` on the text-removed image (floating range, tolerance 6, 4-connected, mask-only).
  Guard against leaks: if the region exceeds `4 * box_w + 80` wide or `6 * box_h + 80` tall, use the
  box grown by half its width sideways and twice its height downward.
- Free rect: start at the box's left/top edge; grow right and down to the container edge minus an
  inner inset of `max(4, round(0.35 * font_px))`; stop 6 px before any other block that lies to the
  right (overlapping rows) or below (overlapping columns).

### 7.4 Fit
Largest integer pixel size `s` in `[floor(0.6 * src_px), src_px]` (never below 8) such that the
wrapped text fits the free rect, using `QFontMetrics.boundingRect(QRect(0,0,w,big), Qt.TextWordWrap, text)`.
- Always `QFont.setPixelSize`. Never point sizes, never `QFont("fixedsys", n)`.
- Never `drawText(x, y, str)` for blocks. Use `drawText(QRect, flags, text)`.
- Family: first installed of `Segoe UI`, `Arial`, `DejaVu Sans`, `Noto Sans`, else the default family.
  Qt falls back per script (Bengali, Hindi, Arabic, CJK, Thai) **(human: verify samples)**.
- If nothing fits at the floor size, use the floor size, let it use the free rect, and set
  `fits=False` in metrics. Do not draw outside the snip.

### 7.5 Alignment
- Left edge stays at the source's left edge (no shift).
- Horizontal centre: single-line source, box centre within 6% of container width from the container
  centre, and container narrower than 3x the box. Centre inside the container inset by the padding.
- Vertical: if the source box centre is within 10% of the container height from the container
  centre, centre the new text block vertically in the container; else align to the source top (and
  centre a single line within its source box height).

### 7.6 Right-to-left
Targets `ar`, `ur`, `he`, `fa` (the language list includes Arabic and Urdu): set
`painter.setLayoutDirection(Qt.RightToLeft)` and mirror alignment (anchor to the right edge of the
source box or container). Add a headless test that draws a sample and asserts the text bounding box
touches the right side of the rect.

### 7.7 Patches and output
- Output: a `QImage` the size of the snip, `Format_ARGB32_Premultiplied`, initially fully transparent.
- Patch rect = union(source box, text rect), clipped to the image. Copy the text-removed pixels into it
  (opaque), then draw the text on top. Nothing else is drawn.
- Skip a block entirely (no removal, no patch) when: translation is empty; translation equals the
  source ignoring case and whitespace; translation failed and returned the source; box is under 6 px.
- Composite preview for humans: alpha-blend the overlay over the capture.

### 7.8 Settings semantics (decision made; the human may change it)
- `alpha`: ignored for patches (patches are opaque). A translucent patch would show the source text
  through the translation and destroy the blend. Keep the key and the slider untouched; list this in
  the P3 report.
- `text_color`: fallback only (empty glyph mask).
- `font_size`: fallback for `src_px` when a block is too small to estimate (box height under 8 px).
- Never mutate `settings.json`.

### 7.9 Translation
- One translation per block, in parallel (existing thread pool), 8 workers max, dedupe identical
  texts, per-call timeout of 8 s, one retry.
- `translator.py`: make `googletrans` an optional import (it is imported at module top but missing from
  `requirements.txt`, so a clean install raises ImportError). The current PyPI release, 4.0.2, has an
  async `translate` **(measured: `inspect.iscoroutinefunction` is True)**, so the call returns a
  coroutine, `hasattr(result, 'text')` is False, and the current code silently falls through to
  deep_translator anyway. Make `deep_translator.GoogleTranslator` the primary. Chunk text over 4500
  characters; the MyMemory fallback rejects text over roughly 500 characters, so chunk at sentence
  boundaries. Verify these limits against the installed deep_translator version rather than trusting
  this paragraph.
- A failed translation returns the source text; section 7.7 then skips the block.

---------------------------------------------------------------------------------------------------

## 8. Debug dump and replay

When `LINGOLENS_DEBUG=1` (environment variables are inherited by the child processes the Control
Center starts), write `debug/<YYYYmmdd-HHMMSS>/`:

`capture.png`, `detections.json`, `boxes.png` (detections drawn on the capture), `ocr.json` (exact
Flask response), `blocks.json`, `blocks.png` (blocks drawn, numbered), `translations.json`,
`removed.png`, `overlay_rgba.png`, `composite.png`, `metrics.json`, `timings.json`, `env.json`
(python, Qt, OpenCV, screen size, devicePixelRatio).

`python/tools/replay.py <dump_dir> [--dest ru] [--stub-translate]` loads `capture.png` + `ocr.json`
(+ `translations.json` when present, so results are deterministic), runs blocks -> render, writes the
last five artifacts, and prints the metrics table. This is how you iterate without the desktop.

`metrics.json` per block: `bbox`, `n_lines`, `src_px`, `font_px`, `ratio`, `contrast`, `fits`,
`busy`, `container`, `free_rect`, `patch`, `ring_std`, `p99_bg_dist`, `box_edge`, `ring_edge`.
Global: counts (words, lines, blocks, skipped), `pixels_changed_outside_patches`, timings.

Ask the human to send back a dump folder when a visual problem needs diagnosing.

---------------------------------------------------------------------------------------------------

## 9. Tests (pytest, headless)

Add `python/tests/conftest.py` that sets `QT_QPA_PLATFORM=offscreen`, and stubs `googletrans` /
`translator` if they cannot be imported so tests never touch the network.

Fix the existing inverted test boxes first (`_make_word("Line1", 10, 100, 50, 20)` has y_max < y_min;
7 of 29 calls are inverted). Add a guard in the test helper: `assert y_max > y_min and x_max > x_min`.

| Test | Asserts |
|---|---|
| `test_fixture_sane` | fixture boxes have max > min; ground truth differs from screenshot only where text is |
| `test_blocks_fixture` | 32 words -> 8 lines -> 4 blocks |
| `test_blocks_columns` | two far-apart words on one row -> 2 blocks; two columns -> separate blocks |
| `test_blocks_heading_vs_body` | different heights are not merged |
| `test_remove_flat` / `test_remove_gradient` | MAE vs ground truth <= 2.0 / <= 6.0; p99 bg distance <= 12 |
| `test_outside_patches_untouched` | alpha 0 and composite == source outside patches |
| `test_fit_monotonic` | fit never exceeds free rect; longer text never gets a larger font |
| `test_contrast_guard` | low-contrast pair is replaced by black/white with contrast >= 4.5 |
| `test_rtl_alignment` | RTL sample anchors right |
| `test_detector_postprocess` | threshold, clamp, min size, empty-crop skipping, NMS |
| `test_geometry` | window `geometry()` equals the snip rect; no scaling in `paintEvent` |
| `test_lifecycle_registry` | real `show_translations()` with OCR/translation stubbed: overlay still visible after 1 s of event loop, registry has 1; closing it ends the loop |
| `test_lifecycle_subprocess` | run the repro pattern in a subprocess; exits within 1 s after dismissal, not before |

Lifecycle tests must fail on the old code for the stated reason (commit them failing in P0, then
make them pass in P1).

---------------------------------------------------------------------------------------------------

## 10. Phases, gates, human checkpoints

After each phase: commit, update `docs/PROGRESS.md`, post the report from `AGENTS.md`.

**P0 Baseline (no product change).** Create branch `overlay-fix`. `py_compile` all files. Run existing
tests. Add `conftest.py`, `fixtures.py`, the failing repro tests (lifecycle, geometry, blocks count,
removal metrics), the debug dump writer, and `replay.py`. Gate: each new test fails on the old code
for the reason stated in this spec, and you show the failure output.

**P1 Lifecycle and geometry.** Defects 1, 2, 6. Registry, `setQuitOnLastWindowClosed(False)`, explicit
quit on every path, window from snip rect, direct event handlers, delete dead code, file logging.
Gate: `test_lifecycle_*` and `test_geometry` pass; `py_compile` clean.
**Human checkpoint 1** (give the human these exact steps): set `LINGOLENS_DEBUG=1` and
`LINGOLENS_DEBUG_OUTLINE=1`, start the Control Center, press Alt+Shift+M, drag over some text.
Expect: a cyan border exactly around the dragged region (no offset, no scaling), magenta outlines
around text blocks, stays until click, click closes it, Task Manager shows no leftover `python`
capture process. Ask them to send `debug/<stamp>/metrics.json` and `env.json` plus a one-line result.

**P2 Detection and grouping.** Defects 5, 7, and inverted test data. `blocks.py`,
`postprocess_predictions`, word filtering. Gate: fixture 32 -> 8 -> 4; all grouping and detector tests
pass. No human step; `blocks.png` and `boxes.png` are written for later review.

**P3 Blend renderer.** Defects 3, 4. `blend.py`, `OverlayWindow.paintEvent` draws the QImage. Gate:
every numeric check in section 11 passes on the synthetic fixture AND on the replayed real dump from
checkpoint 1 (proxies only; no ground truth there). Include the metrics table in the report.
**Human checkpoint 2:** compare `debug/<stamp>/composite.png` and the live overlay with the screen using
this checklist: (1) no visible rectangles or halos, (2) no leftover source glyphs, (3) similar text
size, (4) colours match, (5) alignment matches, (6) nothing outside the region changed,
(7) how long from mouse release to overlay. The human replies with the checklist result and, for any
failure, the block number from `blocks.png`.

**P4 Capture integrity and DPI.** Defect 8. Freeze-frame capture: `ImageGrab.grab()` of the screen
before showing the selection UI; the selection widget paints that frozen image as its background
(dimmed) and draws the selection rect with the user's fill colour, opacity and line width; crop the
snip from the frozen image. Add `AA_DisableHighDpiScaling`. Diagnostic: in debug mode, 300 ms after the
selection window closes re-grab the same bbox and log the mean absolute difference from the snip
(must be < 2.0 per channel unless the screen changed).
Gate: unit test for cropping maths; the diagnostic logs a value.
**Human checkpoint 3:** repeat on a display scaled to 125% or 150%; send `env.json` and the logged
difference; confirm overlay alignment by eye.

**P5 Robustness and docs.** Defect 9, RTL, CJK joining, translator import, README/ARCHITECTURE/
DEVELOPMENT_LOG/MIGRATION_PLAN corrections (remove false claims; describe the new modules and the debug
workflow), `.gitignore` updates, delete dead code, final full test run, final report. Human samples:
bn, hi, ar, ja, zh, ko, th snips to confirm font fallback.

---------------------------------------------------------------------------------------------------

## 11. Acceptance criteria (definition of done)

| # | Criterion | Threshold | Where measured |
|---|---|---|---|
| 1 | Overlay alive after pipeline returns | >= 10 s in test; exits <= 1 s after dismissal | lifecycle tests |
| 2 | Window rect equals snip rect | exact, DPR 1.0 | geometry test, human checkpoint 1 |
| 3 | Grouping on fixture | 32 -> 8 -> 4 | blocks test |
| 4 | Removal vs ground truth (fixture) | MAE <= 2.0 flat, <= 6.0 gradient | blend tests |
| 5 | Removal proxy (real data) | flat: p99 bg distance <= 12; textured: box edge <= 1.5 x ring edge + 3 | metrics.json |
| 6 | Pixels changed outside patches | 0, alpha 0 | blend tests, metrics.json |
| 7 | Text/background contrast | >= 4.5 for every block | blend tests |
| 8 | Font ratio (font_px / src_px) | 0.6 to 1.05 for at least 90% of blocks | metrics.json |
| 9 | Text inside its container and the snip | 100% | blend tests |
| 10 | Render stage time (60 words, 1080p region) | <= 300 ms on the dev machine, reported | timings.json |
| 11 | End-to-end latency mouse-up to overlay | measured and reported per stage | timings.json, human |
| 12 | Clean runs | 20 consecutive replays, no exception | replay loop |
| 13 | Human visual checklist | items 1-7 of checkpoint 2 all pass | human |

Do not call the task done until 1-12 are shown with output and the human has answered 13.

---------------------------------------------------------------------------------------------------

## 12. Known risks and how to handle them

- Detector boxes are looser or tighter than glyphs. The pad and the glyph mask absorb this; do not
  trust box edges for colour sampling beyond the ring median.
- Ring contaminated by a neighbouring block. Median is robust below 50% contamination; if the ring
  spans two very different colours (`ring_std` high, flat fill would be wrong), the textured branch
  handles it.
- Text on photos or heavy gradients: backdrop fallback (7.1). Flag it; do not pretend it blends.
- Translation much longer than the container: floor font 0.6x, then overflow into free space only;
  report `fits=False`.
- Vertical text, rotated text, text over video: unsupported by the horizontal detector. Ignore.
- Windows foreground rules can block keyboard focus for the overlay; mouse dismissal must always work.
- Per-word OCR on multi-line crops can be poor. Not in scope; note candidates for the human.
- Do not chase quality by changing EasyOCR or OpenVINO settings unless a dump shows detection or
  recognition is the actual problem.
