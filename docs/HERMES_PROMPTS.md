# Running this with Hermes + Laguna S 2.1

Files in this kit:

| File | Who reads it | Purpose |
|---|---|---|
| `AGENTS.md` (repo root) | Hermes, automatically every turn | short rules, verified defects, contract, gates (10 KB) |
| `docs/OVERLAY_SPEC.md` | the agent, on demand | full design, algorithms, tests, phases, acceptance numbers |
| `docs/reference/blend_reference.py` | the agent | tested reference of the blend renderer + numeric checks |
| `docs/reference/qt_lifecycle_repro.py` | the agent | reproduces why the overlay never appears |
| `docs/HERMES_PROMPTS.md` | you | this file |

Why the setup is shaped this way: Laguna S 2.1 is a text-only model. It cannot look at your
screenshots or at the overlay, which is very likely how the last session declared victory while the
overlay never even appeared. So every gate here is a number the agent can print, and every visual
judgement is routed to you with exact steps.

---------------------------------------------------------------------------------------------------

## Part A. Setup checklist (5 minutes)

1. Copy the kit into the repo root so you get `AGENTS.md` and `docs/...` next to `app.py`.
   Put your two screenshots in `docs/reference/` as `bad.png` and `target.png` (for your own side
   by side comparison; the agent cannot read them).
2. `git status` should be clean. Then:
   ```
   git checkout -b overlay-fix
   git tag pre-overlay-fix
   ```
3. Add `logs/` and `debug/` to `.gitignore` (the agent will also do this).
4. Context file priority: Hermes loads only ONE project context file, first match wins:
   `.hermes.md` > `AGENTS.override.md` > `AGENTS.md` > `CLAUDE.md` > `.cursorrules`. If the old session
   left a `.hermes.md`, `AGENTS.override.md` or `CLAUDE.md` in the repo, it can shadow this
   `AGENTS.md`. Delete or move them.
5. Start a NEW Hermes session from the repo root (so `AGENTS.md` is discovered), then run `/context`
   and confirm `AGENTS.md` is listed and not truncated or blocked. Hermes scans context files for
   prompt-injection phrasing and blocks a file that trips it. This file is clean; if you edit it,
   avoid phrases like "ignore previous instructions".
6. Clean stale agent memory. Hermes keeps persistent memory and can create its own skills from
   experience, so the failed session may have saved wrong beliefs ("overlay verified", "tests prove
   it works") or the old approach. Look in your Hermes home (`%LOCALAPPDATA%\hermes` on native Windows,
   `~/.hermes` on WSL2), review memory entries and any auto-created skills from that session, and delete
   the misleading ones (the Hermes docs pages "Persistent Memory" and "Skills System" explain the
   layout; they also mention `hermes journey edit` for editing entries). I have not verified these
   exact paths on your install, so check before deleting.
7. Run Hermes natively on Windows, or make sure it launches the Windows venv
   (`.venv/Scripts/python.exe`). A Linux Python inside WSL2 lacks the Windows APIs this app uses.
8. `pip install pytest` inside the venv (dev only). For your human checkpoints keep the OCR server
   available (the Control Center starts it) and the OpenVINO model files in `python/models/`.

Model settings: keep thinking on (Laguna S 2.1 defaults to "max"). On the free OpenRouter endpoint
expect rate limits and a 256K context window; a long phase may stall, and you can simply say "continue".

---------------------------------------------------------------------------------------------------

## Part B. Kickoff prompt (paste as the first message of the first session)

```
You are working on LingoLens, a Windows PyQt5 screen-snip translator. Your project context
(AGENTS.md) is already loaded.

GOAL
Make the in-place translation overlay work and blend into the original screen, exactly as
specified in docs/OVERLAY_SPEC.md. The previous attempt produced an overlay that never stayed on
screen and, when forced to render, drew text in the wrong place with smudged backgrounds.

HOW WE WORK
- You are text-only. You cannot see images. Do not claim anything "looks right". Evidence is
  numbers printed by the harness and PNGs written to debug/ for me to open.
- One phase at a time (P0..P5). Commit after each green phase. Stop after each phase and post the
  report format from AGENTS.md. Do not begin the next phase until I write "go P<n>".
- Diagnose before fixing. Write a failing test or repro first, then fix, then show it pass.
- No new runtime dependencies, no file renames, no Control Center UI changes, no settings key
  changes, no unrelated refactors. Never weaken or delete a test to get green.
- If you fail the same check three times, or a decision changes what the user sees, stop and ask
  with the evidence you have.

DO THIS NOW, IN ORDER
1. Read docs/OVERLAY_SPEC.md completely. Then read docs/reference/blend_reference.py and
   docs/reference/qt_lifecycle_repro.py.
2. Run both reference scripts (blend_reference.py, then qt_lifecycle_repro.py with A, B and C) and
   paste the raw output.
3. Run: git status; git log --oneline -8. Create branch overlay-fix and tag pre-overlay-fix if I have
   not already.
4. For each numbered defect in AGENTS.md, confirm it against the ACTUAL code with grep and one
   sentence (file:line, what the code does). Line numbers in AGENTS.md are approximate. Report any
   defect that does not match what you find; do not assume.
5. Create docs/PROGRESS.md (phase table, decisions, open questions, how to resume).
6. Execute Phase P0 only. Stop at its gate and post the phase report, including the failing
   output of each new repro test and why it fails.
```

---------------------------------------------------------------------------------------------------

## Part C. Phase prompts

Send these after you have read the phase report and agree with it.

### go P1 (lifecycle and geometry)
```
go P1. Implement Phase P1 exactly as in docs/OVERLAY_SPEC.md sections 3, 4 and 10. Order: (1) make
the lifecycle and geometry tests pass, (2) add the debug outline mode and file logging, (3) delete
the dead code listed in section 4.3. Run py_compile and the full test suite. Then post the phase
report, followed by the exact human checkpoint 1 steps for me to run, and stop.
```

Human checkpoint 1 (you do this; send the result back with this template):
```
Checkpoint 1 result
- Cyan border exactly matches my dragged region: yes/no (if no: offset __ px, direction __)
- Overlay stayed until I clicked: yes/no
- Click closed it and no capture python process remained in Task Manager: yes/no
- Anything odd:
[pasted: debug/<stamp>/metrics.json and env.json]
```

### go P2 (detection and grouping)
```
Checkpoint 1 passed (or: here is what failed, fix that first). go P2. Implement Phase P2 per the spec
sections 5, 6 and 10: blocks.py, postprocess_predictions with the confidence threshold and clamping,
word filtering, and fix the inverted boxes in the existing tests with the helper assertion. Show the
fixture going from the old 2 paragraphs to 4 blocks. Post the report and stop.
```

### go P3 (blend renderer)
```
go P3. Implement Phase P3 per the spec section 7 and 10. Start from docs/reference/blend_reference.py
but adapt it to the project's data structures; keep every numeric check as a real pytest. Run the
renderer on the synthetic fixture and replay the real dump from checkpoint 1 with tools/replay.py.
Paste the metrics tables for both. List every acceptance row in section 11 with PASS/FAIL and the
number. Then give me the exact human checkpoint 2 steps and stop.
```

Human checkpoint 2 (visual) template:
```
Checkpoint 2 result (open debug/<stamp>/composite.png and also try it live)
1. No visible rectangles or halos: yes/no (blocks: __)
2. No leftover source glyphs: yes/no (blocks: __)
3. Text size similar to source: yes/no (blocks: __ too big / too small)
4. Colours match: yes/no (blocks: __)
5. Alignment matches (left/centre): yes/no (blocks: __)
6. Nothing outside the translated blocks changed: yes/no
7. Time from mouse release to overlay: __ s
Block numbers are the ones drawn in blocks.png. Dump folder attached: debug/<stamp>/
```

### go P4 (capture integrity, DPI)
```
go P4. Implement Phase P4 per spec section 10: freeze-frame capture using the user's fill colour,
opacity and line width for the selection rectangle, AA_DisableHighDpiScaling, the re-grab diagnostic
in debug mode. Add a unit test for the crop maths. Post the report and the human checkpoint 3 steps
(125% or 150% display scaling), then stop.
```

### go P5 (robustness and docs)
```
go P5. Implement Phase P5 per spec section 10. Correct README.md, ARCHITECTURE.md,
DEVELOPMENT_LOG.md and MIGRATION_PLAN.md so they describe reality (remove the false "verified"
claims, the Tkinter overlay mentions, and the singleton claim). Then run the final audit prompt below.
```

---------------------------------------------------------------------------------------------------

## Part D. Reporting a visual problem (works for a text-only agent)

The agent cannot look, so give it geometry and a reproducible artifact, not adjectives.

```
Visual problem in block <n> (numbered in debug/<stamp>/blocks.png).
Expected: <one sentence, e.g. "caption centred in the blue button, same white colour">.
Actual: <one sentence, e.g. "text is left aligned and about 40% smaller, touching the right edge">.
Dump folder: debug/<stamp>/ (I have put it in the repo).
Before changing anything: (1) run python/tools/replay.py on that dump and paste the metrics row for
block <n>, (2) tell me which metric explains it, (3) add a failing test that captures it, (4) fix,
(5) show the test passing and re-run the acceptance table.
```

Tips: always attach the whole `debug/<stamp>/` folder; name blocks by their number in `blocks.png`;
describe one problem per message.

---------------------------------------------------------------------------------------------------

## Part E. Corrective prompts

**It claims success without evidence**
```
Stop. You wrote "<quote>" but the output you showed does not establish it. Reminder: you cannot see
the screen. Re-run <harness or test command> and paste the raw output. Then give two lists:
(a) acceptance rows from OVERLAY_SPEC.md section 11 that are proven by that output, with the number,
(b) what only I can verify. Do not use "works", "looks" or "blends" without a number next to it.
```

**It drifts or rewrites too much**
```
You changed <files> which are outside Phase P<n>. Show me git diff --stat, revert everything outside the
phase scope with git, and continue with only the scope in OVERLAY_SPEC.md section 10.
```

**Same check fails repeatedly**
```
This check has failed three times. Stop editing. Write three competing hypotheses, and for each a cheap
experiment that prints numbers. Run the cheapest one and report. If the answer needs a human
observation, tell me exactly what to look at and what to send back.
```

**It touched the tests to get green**
```
Show git diff for every test file changed. For each change, explain why the original assertion was wrong.
Restore any change you cannot justify from the spec.
```

**It starts redesigning (new threads, new OCR, new UI)**
```
That is out of scope (AGENTS.md "Out of scope"). Drop it, note it in docs/PROGRESS.md under "future
work", and return to the current phase gate.
```

**New session or context got long (resume)**
```
Resume the LingoLens overlay work. Read AGENTS.md and docs/PROGRESS.md. Run git status and
git log --oneline -10. Run the test suite and docs/reference/blend_reference.py. Then tell me: current phase,
what is verified (with numbers), what is pending, and the next command you will run. Do not change any
code yet.
```

Start a fresh session per phase. `docs/PROGRESS.md` and the git history are the handoff.

---------------------------------------------------------------------------------------------------

## Part F. Final audit prompt

```
Final audit. For every row of OVERLAY_SPEC.md section 11 give status, the evidence (command and the
number), and the file that implements it. Then check and report: py_compile clean for app.py and python/*.py;
full pytest output; git diff --stat pre-overlay-fix..HEAD; settings.json and the Flask /ocr contract
unchanged; no print debugging left; logs/ and debug/ in .gitignore; the four docs corrected; dead code
(_DismissFilter, _init_timer) gone; a list of remaining risks ranked by how likely they are to
show up on a real desktop. Separate what you proved from what I still need to confirm.
```

---------------------------------------------------------------------------------------------------

## Part G. Notes on working with this model and agent

- **No vision**: never ask it to "make it look better". Ask for metric-driven fixes and give it
  block numbers and dump folders.
- **Long-horizon strength, verbosity cost**: it will happily run for a long time. The phase gates and
  "stop after each phase" keep you in the loop at the moments that need human eyes.
- **Tool-call hygiene**: this model has been reported to occasionally mangle nested tool arguments.
  `AGENTS.md` asks for small edits and a `py_compile` after each edit. If you see a corrupted edit,
  tell it to `git diff` and repair.
- **Cost of context**: `AGENTS.md` (10 KB) is injected every turn; the spec is read once per session
  on demand. Do not paste the spec into the chat.
- **GUI**: the agent can launch processes but cannot operate or watch the GUI. Anything involving the
  hotkey, dragging a region, or looking at the screen is yours.
- **Git as the safety net**: you tagged `pre-overlay-fix`. If a phase goes badly,
  `git reset --hard <last good commit>` and resume with the resume prompt.
