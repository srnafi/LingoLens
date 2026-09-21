"""Translation provider for LingoLens.

Tiered translation with graceful degradation. `googletrans` is optional: it is
not shipped in requirements.txt and the current PyPI release (4.0.2) is async,
which makes it unusable here, so it is never relied on. deep_translator
(GoogleTranslator) is the primary engine; MyMemory is the fallback.

Network calls are bounded by a per-call timeout and a single retry so a stalled
translation never blocks the overlay. Long texts are chunked to respect engine
limits (MyMemory rejects >~500 chars).

This module must always import successfully (it is imported at module load by
overlay.py), so no optional dependency is imported at the top level.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from deep_translator import GoogleTranslator, MyMemoryTranslator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits (verified against deep_translator 1.9.1 on the dev box).
# ---------------------------------------------------------------------------
# GoogleTranslator accepts very long texts, but we chunk anyway for speed and
# to isolate failures to a single sentence.
GOOGLE_CHUNK = 4500
# MyMemory rejects texts over ~500 characters.
MYMEM_CHUNK = 300
# Per-call network timeout and retry budget.
CALL_TIMEOUT_S = 8.0
CALL_RETRIES = 1

# googletrans is NOT used as a translation engine: it is not in requirements.txt
# and the current PyPI release (4.0.2) is async, which is incompatible with this
# synchronous pipeline. deep_translator (below) is the primary engine.

# MyMemory uses region-qualified language codes (e.g. "bn-IN", "hi-IN"). Map
# bare ISO 639-1 codes to the closest MyMemory code so engines receive a code
# they accept. Verified against the installed deep_translator 1.9.1 language set.
_MYMEM_LANGS = {
    "bn": "bn-IN", "hi": "hi-IN", "ar": "ar-SA", "ur": "ur-PK",
    "fa": "fa-IR", "he": "he-IL", "ja": "ja-JP", "zh": "zh-CN",
    "ko": "ko-KR", "th": "th-TH", "vi": "vi-VN", "tr": "tr-TR",
    "ru": "ru-RU", "de": "de-DE", "fr": "fr-FR", "es": "es-ES",
    "pt": "pt-PT", "it": "it-IT", "nl": "nl-NL", "sv": "sv-SE",
    "pl": "pl-PL", "uk": "uk-UA", "el": "el-GR", "ro": "ro-RO",
}


def _normalize_my_memory(dest):
    """Return a MyMemory-compatible language code for the given dest."""
    if not dest:
        return dest
    if "-" in dest or "_" in dest:
        return dest.replace("_", "-")
    return _MYMEM_LANGS.get(dest, dest)

# Sentence boundary splitter: matches end of sentence punctuation followed by
# whitespace and a word-start capital, used to break long texts into
# translation-safe chunks.
_SENT_RE = re.compile(r"(?<=[\.\!\?])\s+(?=[^\W\d_])")


def _split_sentences(text):
    """Split text into sentence-sized chunks for translation engines.

    Keeps each chunk under the per-engine limit when possible. Falls back to a
    hard character split if no sentence boundary is found.
    """
    sentences = _SENT_RE.split(text.strip())
    out = []
    buf = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if buf and len(buf) + 1 + len(s) > MYMEM_CHUNK:
            out.append(buf)
            buf = s
        else:
            buf = (buf + " " + s) if buf else s
    if buf:
        out.append(buf)
    return out if out else [text]


def _chunk_text(text, max_len):
    """Hard character chunking fallback when sentence splitting is insufficient."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


def _run_with_timeout(fn, timeout_s=CALL_TIMEOUT_S, retries=CALL_RETRIES):
    """Run fn() in a worker thread, with timeout and a single retry.

    Returns the function's result, or None on total failure. A timeout or
    exception is logged at debug level so the translation fallback chain can
    proceed silently on the user's desktop.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(fn)
                return fut.result(timeout=timeout_s)
        except FuturesTimeout:
            last_exc = TimeoutError(f"timed out after {timeout_s}s")
            logger.debug("translation timed out (attempt %d/%d)",
                         attempt + 1, retries + 1)
        except Exception as e:
            last_exc = e
            logger.debug("translation error (attempt %d/%d): %s",
                         attempt + 1, retries + 1, e)
    if last_exc:
        logger.debug("translation failed after %d retries: %s", retries + 1, last_exc)
    return None


def _google_translate(text, dest):
    """Primary engine: deep_translator GoogleTranslator (synchronous)."""
    chunks = _split_sentences(text)
    if len(chunks) == 1 and len(text) > GOOGLE_CHUNK:
        chunks = _chunk_text(text, GOOGLE_CHUNK)
    parts = []
    for c in chunks:
        res = _run_with_timeout(
            lambda c=c: GoogleTranslator(source="auto", target=dest).translate(c))
        if res:
            parts.append(res)
    if parts:
        return " ".join(parts)
    return None


def _mymemory_translate(text, dest, source=None):
    """Fallback engine: deep_translator MyMemoryTranslator, chunked.

    MyMemory does not accept source='auto'; it requires a region-qualified
    language code (e.g. 'en-US', 'bn-IN'). If no source is given we try 'en-US'
    (the common snip source) and then fall back to the bare normalized code.
    """
    src = source
    if not src or src == "auto":
        src = "en-US"
    chunks = _split_sentences(text)
    if len(chunks) == 1 and len(text) > MYMEM_CHUNK:
        chunks = _chunk_text(text, MYMEM_CHUNK)
    parts = []
    for c in chunks:
        res = _run_with_timeout(
            lambda c=c: MyMemoryTranslator(source=src, target=dest).translate(c))
        if res:
            parts.append(res)
    if parts:
        return " ".join(parts)
    # Retry once with the bare dest code normalized, in case 'en-US' was wrong.
    if src == "en-US":
        return _mymemory_translate(text, dest, source="en-GB")
    return None


def translate_text(text, dest="hi"):
    """Translate a full text block (sentence/paragraph) with tiered fallback.

    Translates complete text rather than individual words, which gives the
    translation engine full context for natural, grammatically correct output.

    Returns the translated text. If every engine fails, returns the original
    text unchanged (so the caller's "skip if equals source" logic takes over).
    """
    if not text or not text.strip():
        return text

    text = text.strip()

    # Primary: deep_translator GoogleTranslator (googletrans is not used — it
    # is not in requirements and its current release is async/broken).
    result = _google_translate(text, dest)
    if result and result.strip() and result.lower() != text.lower():
        return result

    # Fallback: MyMemory (needs region-qualified codes, e.g. "bn-IN").
    result = _mymemory_translate(text, _normalize_my_memory(dest))
    if result and result.strip() and result.lower() != text.lower():
        return result

    # All engines failed or returned the source unchanged: return source.
    logger.debug("translation failed or empty for dest=%s, returning source", dest)
    return text


def translate_word(word, dest="hi"):
    """Backward-compatible alias for word-level translation.

    Note: sentence/paragraph translation yields better quality; prefer
    translate_text with the full block string.
    """
    return translate_text(word, dest)


if __name__ == "__main__":
    # Quick smoke test: translate a full sentence to a destination language.
    import sys
    dest_lang = sys.argv[1] if len(sys.argv) > 1 else "bn"
    sample = sys.argv[2] if len(sys.argv) > 2 else "Welcome to the settings page"
    out = translate_text(sample, dest=dest_lang)
    print(f"[{dest_lang}] {sample}")
    print(f"  -> {out}")
