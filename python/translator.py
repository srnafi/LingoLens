from googletrans import Translator
from deep_translator import GoogleTranslator, MyMemoryTranslator
import logging

logger = logging.getLogger(__name__)


def translate_text(text, dest='hi'):
    """Translate a full text block (sentence/paragraph) with tiered fallback.

    Translates complete text rather than individual words, which gives the
    translation engine full context for natural, grammatically correct output.
    """
    if not text or not text.strip():
        return text

    # Primary: googletrans
    try:
        translator = Translator()
        result = translator.translate(text, dest=dest)
        if result and hasattr(result, 'text') and result.text:
            return result.text
    except Exception as e:
        logger.debug(f"googletrans failed: {e}")

    # Fallback 1: deep_translator GoogleTranslator
    try:
        result = GoogleTranslator(source='auto', target=dest).translate(text)
        if result:
            return result
    except Exception as e:
        logger.debug(f"GoogleTranslator failed: {e}")

    # Fallback 2: deep_translator MyMemoryTranslator
    try:
        result = MyMemoryTranslator(source='auto', target=dest).translate(text)
        if result:
            return result
    except Exception as e:
        logger.debug(f"MyMemoryTranslator failed: {e}")

    # All failed, return original
    return text


# Backward-compatible alias
translate_word = translate_text


if __name__ == "__main__":
    # Test with a full sentence to demonstrate context-aware translation
    test_cases = [
        ("Welcome to the settings page", "es"),
        ("Click the button below to continue", "fr"),
        ("Error: file not found. Please try again.", "de"),
    ]
    for text, lang in test_cases:
        translated = translate_text(text, dest=lang)
        print(f"[{lang}] {text}")
        print(f"  -> {translated}\n")
