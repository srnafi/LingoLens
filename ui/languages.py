"""Language tables + pure pair logic — stdlib only, headless-testable.

The FROM option int selects the EasyOCR model bundle and must stay in
sync with ``python/ocr_server.py`` LANGUAGE_MAP.
"""
FROM_LANGS = [
    ("English", 1), ("Spanish", 1), ("French", 1), ("Italian", 1),
    ("Portuguese", 1), ("Vietnamese", 1), ("German", 1),
    ("Chinese", 2), ("Japanese", 3), ("Russian", 4),
    ("Bengali", 5), ("Korean", 6),
]
FROM_SHORT = ["EN", "ES", "FR", "IT", "PT", "VI", "DE",
              "ZH", "JA", "RU", "BN", "KO"]

TO_LANGS = [
    ("English", "en"), ("Spanish", "es"), ("French", "fr"), ("German", "de"),
    ("Italian", "it"), ("Portuguese", "pt"), ("Russian", "ru"),
    ("Vietnamese", "vi"), ("Bengali", "bn"), ("Hindi", "hi"),
    ("Chinese (Simplified)", "zh-CN"), ("Japanese", "ja"), ("Korean", "ko"),
    ("Arabic", "ar"), ("Urdu", "ur"), ("Dutch", "nl"), ("Turkish", "tr"),
    ("Polish", "pl"), ("Indonesian", "id"), ("Thai", "th"),
]

MAX_RECENTS = 3


def base_name(name):
    """'Chinese (Simplified)' -> 'chinese'. Used for From/To swap matching."""
    return name.split("(")[0].strip().lower()


def is_swappable(from_name, to_name):
    """A pair can flip only if both sides exist in both lists (OCR model needed)."""
    from_bases = {base_name(n) for n, _ in FROM_LANGS}
    to_bases = {base_name(n) for n, _ in TO_LANGS}
    return (base_name(from_name) in to_bases
            and base_name(to_name) in from_bases)


def find_from_index(name, option):
    """Index into FROM_LANGS by display name, falling back to model option."""
    for i, (n, _opt) in enumerate(FROM_LANGS):
        if n == name:
            return i
    for i, (n, opt) in enumerate(FROM_LANGS):
        if opt == option:
            return i
    return 0


def find_to_index(code):
    """Index into TO_LANGS by translation code."""
    for i, (_n, c) in enumerate(TO_LANGS):
        if c == code:
            return i
    return 0


def to_display_name(code):
    """Translation code -> display name ('bn' -> 'Bengali')."""
    for n, c in TO_LANGS:
        if c == code:
            return n
    return code


def sanitize_recents(raw):
    """Drop malformed/unknown recent-pair entries, cap at MAX_RECENTS."""
    valid_from = {n for n, _ in FROM_LANGS}
    valid_to = {c for _, c in TO_LANGS}
    clean = []
    for entry in raw if isinstance(raw, list) else []:
        if (isinstance(entry, dict)
                and entry.get("from") in valid_from
                and entry.get("to") in valid_to):
            clean.append({"from": entry["from"], "to": entry["to"]})
    return clean[:MAX_RECENTS]
