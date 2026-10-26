# AGENTS_NEXT — Translation Latency & Reliability

Read `AGENTS.md` first. This file is the next-phase brief. It does **not** replace
`AGENTS.md`, and it does **not** authorize live translation, WGC/D3D11 capture,
or real-time overlays. Scope is the existing snip pipeline only.

Working directory: `G:\LingoLens`
Interpreter: `.venv/Scripts/python.exe`
Branch at time of writing: `main`
Untracked files to leave alone: `mock_design.py`, `mock_ui.py`

---------------------------------------------------------------------------------------------------

## 1. Mission

Make the existing snip translator **fast, correct, and hard to crash** using
multiple translation providers.

"Error-free" here means:

- No unhandled exception in the OCR → group → translate → render path.
- The selected source language is actually used. No silent `en-US` fallback for
  Japanese, Chinese, Russian, Bengali, Korean, etc.
- Every network request has a real connect/read timeout and a per-snip deadline.
  A provider that hangs cannot hang the overlay.
- If every provider fails, the original text stays visible (no overlay patch),
  and the failure is visible in the log/status. Do not crash, and do not paint
  an empty box.
- Duplicate blocks are translated once. Repeated snips can hit a cache.
- A failed provider is skipped for a short cooldown instead of being hammered.
- Paid/keyed providers are never used silently just because a free provider
  failed.

"Error-free" does **not** mean "always returns a translation". It means the
failure path is deterministic and safe.

Target, provisional until measured on this machine:

- p50 translation latency <= 1.5 s for 1–3 blocks / <= 300 chars.
- p95 <= 3.0 s.
- Cache hit <= 20 ms.
- No translation request outlives its deadline by more than 250 ms.
- No snip exits with a traceback.

The current stored debug dump shows a translation stage of ~8.7 s, so measure a
baseline before optimizing. Do not claim the target is met without a harness
output.

---------------------------------------------------------------------------------------------------

## 2. What to extract from OverTranslate

Extract the **translation orchestration and resilience layer**, not the app.

Reference only:

- Public MIT repo: `https://github.com/Hon-Lu/OverTranslate`
- Previously decompiled trees (may be wiped after a reboot):
  - `C:\Users\sezar\AppData\Local\Temp\ot_src\main\OverTranslate.Services\TranslationService.cs`
  - `C:\Users\sezar\AppData\Local\Temp\ot_src\main\OverTranslate.Services.Providers\ResilientProvider.cs`
  - `C:\Users\sezar\AppData\Local\Temp\ot_src\main\OverTranslate.Services.Ocr\OnnxOcrEngine.cs`

What to copy as behavior:

1. **TranslationService** shape:
   provider selection, request lifecycle, source/target language handling,
   cancellation/deadline propagation, and a result/error contract.
2. **ResilientProvider** behavior:
   retry classification, fallback, hedging (start a backup before the first
   provider finishes), timeouts, and per-provider health.
3. **Provider adapters**:
   Google and MyMemory first. Optional DeepL / OpenAI-compatible only when
   explicitly configured. Do not port all of OverTranslate's providers in one
   phase.
4. **OCR confidence gate** (adjacent, cheap, and important for error-free):
   OverTranslate uses a 0.6 recognition confidence floor. LingoLens currently
   ignores EasyOCR confidence entirely. Filter low-confidence OCR text before
   it reaches translation. Do this inside `ocr_server.py`; do not change the
   `/ocr` response contract.
5. **Provider/language normalization**:
   exact source codes, region-qualified codes where required (e.g. MyMemory
   wants `bn-IN`, `hi-IN`), and no `source=auto` for providers that require a
   concrete source.

Do **not** extract now:

- WGC window/monitor capture.
- D3D11 frame pools, readback, or overlay exclusion.
- Realtime translation state machines, frame fingerprints, or 150 ms polling.
- The 428-file C#/WPF structure. Reimplement the policy in Python; do not port
  the tree.

Licensing/ToS:

- OverTranslate code is MIT, but its manga OCR model is CC BY-NC-SA 4.0.
- The free translation endpoints are unofficial. Do not ship them commercially
  without a terms-of-service review.
- Never commit provider keys. Read them from environment variables or an
  untracked local file.

---------------------------------------------------------------------------------------------------

## 3. Current defects this phase must fix

These are confirmed in the current code. Re-check line numbers before editing.

1. **Non-Latin OCR is thrown away before translation.**
   `python/overlay.py` uses `re.compile(r'[A-Za-z0-9]')` in
   `_parse_ocr_results`. Probe result:
   - `こんにちは` → dropped
   - `Привет` → dropped
   - `Hello` → kept
   Fix with Unicode-aware filtering, e.g.
   `any(ch.isalnum() for ch in text)`. Add a test that calls
   `_parse_ocr_results`, not only `blocks._join_words`.

2. **Source language never reaches the translator.**
   `ui/main_window.py` knows `source_lang_name`, but
   `ui/backend.py::launch_snip`, `python/capture.py`, `python/detector.py`,
   `python/overlay.py`, and `python/translator.py` only carry `dest`.
   `translate_text()` has no `source` parameter.
   Add source through the pipeline without changing the existing capture argv
   contract. Preferred: `LINGOLENS_SOURCE` environment variable set by
   `Backend.launch_snip`, read by `capture.py`, passed down. Keep the first
   seven positional arguments exactly as they are.

3. **MyMemory fallback always assumes English.**
   `python/translator.py` defaults to `en-US` for MyMemory. If Google fails
   while the source is Japanese/Chinese/Russian/Bengali, the fallback is asked
   to translate from English. Fix by passing the exact source code and mapping
   it to MyMemory's region-qualified form.

4. **The timeout wrapper does not actually bound the call.**
   `_run_with_timeout()` uses a `ThreadPoolExecutor` context manager. On
   timeout, leaving the `with` block calls `shutdown(wait=True)`, so it waits
   for the slow worker anyway. Measured: a 0.1 s timeout against a 1 s worker
   took 1.0 s.
   Replace it with a router that uses explicit `requests` connect/read
   timeouts, a persistent worker pool, and `concurrent.futures.wait(...,
   FIRST_COMPLETED, timeout)`. Do not wait for late losers. Ensure a late
   request cannot keep the process alive after dismissal.

5. **OCR confidence is ignored.**
   `python/ocr_server.py` does `result = reader.recognize(file_path)` and keeps
   `box[1]` only. `box[2]` is the confidence. Add `MIN_OCR_CONF = 0.6`, skip
   low-confidence text, and log kept/dropped counts. Keep the returned JSON
   shape unchanged.

6. **The cache and provider health die with each snip.**
   `capture.py` is a new process per hotkey. Any in-memory cache or circuit
   breaker is lost. Use a small persistent cache (stdlib `sqlite3` is allowed)
   or a long-lived local translation service. Do not add a new runtime
   dependency.

7. **There is no per-request telemetry.**
   Add provider, source, destination, char count, attempt, timeout/error class,
   latency, cache hit, and fallback reason to logs and the debug dump. Do not
   log API keys or full text unless debug mode is already writing it.

---------------------------------------------------------------------------------------------------

## 4. Target design

Keep the public entry point stable:

```python
# python/translator.py remains the facade.
translate_text(text: str, dest: str, source: str = "auto") -> str
translate_blocks(texts: list[str], dest: str, source: str = "auto",
                 deadline_s: float = 4.0) -> list[str]
```

Suggested package:

```text
python/translation/
  __init__.py
  types.py          # TranslationRequest, ProviderResult, ErrorKind
  router.py         # provider selection, hedge, deadline, fallback
  cache.py          # SQLite + in-memory LRU, keyed by source/dest/text
  health.py         # circuit breaker per provider
  providers/
    __init__.py
    base.py         # Provider protocol + shared HTTP session
    google.py       # Google web endpoint or deep_translator, explicit timeouts
    mymemory.py     # direct requests, region-qualified source
    deepl.py        # optional, keyed
    openai.py       # optional, keyed
```

Routing policy, first pass:

- Validate `source` and `dest`. If equal, return the source text unchanged.
- Skip empty text and text with no alnum characters.
- Cache lookup by normalized `(source, dest, text)`.
- Provider order:
  1. configured keyed provider, only if the user explicitly selected it;
  2. Google;
  3. MyMemory.
- If Google has an open circuit, start with MyMemory.
- Start the next provider if the current one has not produced a valid result
  after ~800 ms (configurable). Return the first valid result.
- Per-provider attempt timeout: ~2.5 s. Snip deadline: ~4 s.
- On every provider failure, classify:
  - retryable: 408, 425, 429, 5xx, connection, read timeout, empty body;
  - fatal for that provider: 400, 401, 403, 404, bad language/key;
  - skip: empty/unchanged result, source == destination.
- After 3 consecutive retryable failures, open the provider circuit for ~30 s.
  Reset on a success. Never let all circuits stay open permanently; the last
  resort is to try the primary once.
- If all providers fail, return the source text for that block. The renderer
  must leave that block unpainted, so the original screen text remains.
- Never silently route to a paid provider. If the user did not configure one,
  do not invent one.

Source flow:

1. `ui/languages.py`: add `SOURCE_CODES` keyed by source display name
   (`English -> en`, `Chinese -> zh-CN`, `Japanese -> ja`, `Russian -> ru`,
   `Bengali -> bn`, `Korean -> ko`, etc.).
2. `ui/main_window.py::trigger_snip`: pass the source code.
3. `ui/backend.py::launch_snip`: add a source parameter and put it in the
   child environment as `LINGOLENS_SOURCE`. Keep the existing argv order.
4. `python/capture.py`: read `LINGOLENS_SOURCE`, pass it to `detector.main`.
5. `python/detector.py::main`: accept `source`, pass to
   `overlay.show_translations`.
6. `python/overlay.py`: pass source and destination to `translate_blocks`.
7. `python/translator.py`: keep `translate_text()` as a compatibility wrapper
   around the new router.

Latency work, in order:

1. Reuse one `requests.Session` per provider with a bounded connection pool.
   Do not create a translator/client per chunk.
2. Translate blocks concurrently with a small cap (2–4 in flight), not one
   nested thread pool per chunk.
3. Deduplicate identical block strings within a snip.
4. Add the persistent cache before adding more providers.
5. Only then consider batching multiple blocks into one request. Do not batch
   unrelated UI text blindly; measure the quality and latency win.
6. Keep translation off the UI thread. The overlay must still be able to exit
   promptly if the user dismisses it.

Do not add `aiohttp`, `httpx`, or another HTTP stack. `requests` is already a
dependency. Stdlib `sqlite3`, `threading`, `concurrent.futures`, and `hashlib`
are allowed.

---------------------------------------------------------------------------------------------------

## 5. Phases and gates

### P0 — Baseline and failing tests

- Add stage timing around detector, OCR, grouping, translation, and render.
- Run 10–20 recorded snips; record p50/p95 per stage.
- Add failing tests for:
  - CJK/Russian/Bengali text through `_parse_ocr_results`;
  - non-English source passed to MyMemory;
  - timeout bounded within deadline + 250 ms;
  - all-provider failure returns source without exception;
  - duplicate blocks call the provider once.
- Gate: baseline table written; the new tests fail on current code for the
  stated reasons.

### P1 — Correctness

- Fix Unicode OCR filtering.
- Add source through the whole pipeline.
- Add provider error taxonomy and safe failure.
- Keep `translate_text(text, dest)` working for old callers.
- Gate: full path handles Japanese, Russian, Bengali, and Arabic source samples;
  no fallback request uses `en-US` for a non-English source; no traceback on
  empty/malformed text.

### P2 — Router, providers, cache, health

- Implement `TranslationRouter` with Google + MyMemory.
- Add fake providers for tests; no network in unit tests.
- Add cache, dedupe, circuit breaker, and per-attempt telemetry.
- Gate:
  - fake 429/500/timeout falls back correctly;
  - fake auth failure does not retry forever;
  - second identical request is a cache hit;
  - 3 failures open the circuit and a success closes it;
  - all-fail path leaves source text untouched.

### P3 — Latency

- Persistent HTTP sessions, bounded workers, request deadline, hedge delay.
- SQLite cache survives a new snip process.
- Remove nested thread-pool-per-chunk behavior.
- Gate: measured p50/p95 targets, cache hit <= 20 ms, no request outlives
  deadline + 250 ms, no lingering non-daemon worker blocks process exit.

### P4 — UX and observability

- Use the existing toast/status path for "translation unavailable" or
  "using fallback"; do not redesign the Control Center.
- Write translation metrics to `debug/<stamp>/metrics.json` (provider, attempts,
  latencies, fallback reason).
- Gate: human desktop check of success, fallback, and total failure on a real
  snip; source text remains visible on failure.

### P5 — Optional keyed providers

- Add DeepL and/or OpenAI-compatible only behind an explicit setting/env key.
- Never fall back to them silently.
- Gate: missing/invalid key handled cleanly; no secret in repo or logs.

Do not start a live-mode phase in this brief. If live mode is wanted later, it
needs a separate capture plan (WGC or DXGI Desktop Duplication), a frame
fingerprint, click-through overlays, and overlay exclusion. That is not this
phase.

---------------------------------------------------------------------------------------------------

## 6. Required tests (headless, no network)

Put tests under `python/tests/` (the folder is local-only at the moment).

- `test_unicode_ocr_parse`: `こんにちは`, `Привет`, `বাংলা`, `مرحبا` survive
  `_parse_ocr_results`; `|` and `~` are still dropped.
- `test_source_reaches_translator`: UI source code → capture env → overlay →
  router; assert provider received the correct source.
- `test_mymemory_source_is_not_en_us_for_japanese`: fake Google failure; assert
  MyMemory source is `ja`, not `en-US`.
- `test_timeout_is_bounded`: fake provider sleeps 10 s; assert return within
  deadline + 250 ms.
- `test_fallback_on_429_and_5xx`: fake Google fails; fake MyMemory succeeds;
  assert fallback and latency.
- `test_auth_failure_is_fatal_for_provider`: fake 401; no retry loop.
- `test_all_providers_fail_returns_source`: no exception, source preserved.
- `test_cache_hit_skips_provider`: second call has zero provider attempts.
- `test_duplicate_blocks_translate_once`: two identical strings → one request.
- `test_circuit_breaker_opens_and_resets`.
- `test_no_provider_key_in_logs`: assert secret strings never appear.

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python -q
```

Do not weaken an existing test to get green. If a test data box is inverted,
fix the data and say why.

---------------------------------------------------------------------------------------------------

## 7. Do not do

- Do not build live translation / WGC / D3D11 / frame loops in this phase.
- Do not change the Flask `/ocr` request/response contract.
- Do not rename settings keys or redesign the Control Center.
- Do not change the existing capture argv order; source goes through an
  environment variable.
- Do not add runtime dependencies.
- Do not copy decompiled C# or paste provider code without a license/ToS review.
- Do not silently fall back to a paid provider.
- Do not log API keys.
- Do not claim "error-free" based only on mocked providers. The final gate is a
  real desktop snip plus the harness numbers.

---------------------------------------------------------------------------------------------------

## 8. Restart checklist

```text
cd G:\LingoLens
git status --short
# expected: only mock_design.py and mock_ui.py untracked

QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest python -q
# baseline: 72 passed

.venv/Scripts/python.exe python/ocr_server.py 1   # human/e2e only
```

Then:

1. Read `AGENTS.md`, this file, and `docs/OVERLAY_SPEC.md`.
2. Verify the current line numbers with `grep`; docs may lag the code.
3. Start P0. Do not jump to provider code before the baseline and failing tests.
4. Update `docs/PROGRESS.md` after each phase with evidence and what is still
   human-verified only.

The immediate first patch, if you only do one thing:

- Replace the ASCII-only OCR filter with Unicode-aware filtering, pass the
  selected source language through the pipeline, and make the timeout actually
  bound the provider call. Those three are the difference between "multi-provider
  mode" and "multi-provider-looking code that still waits 8 seconds and breaks
  on Japanese."
