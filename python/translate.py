from googletrans import Translator
from deep_translator import GoogleTranslator, MyMemoryTranslator
import logging

def translate_word(word, dest='hi'):
    # Primary: googletrans
    try:
        translator = Translator()
        translation = translator.translate(word, dest=dest)
        if translation and hasattr(translation, 'text') and translation.text:
            return translation.text
    except Exception as e:
        logging.debug(f"googletrans failed: {e}, trying deep_translator GoogleTranslator")

    # Fallback 1: deep_translator GoogleTranslator
    try:
        dt_trans = GoogleTranslator(source='auto', target=dest).translate(word)
        if dt_trans:
            return dt_trans
    except Exception as e:
        logging.debug(f"deep_translator GoogleTranslator failed: {e}, trying MyMemoryTranslator")

    # Fallback 2: deep_translator MyMemoryTranslator
    try:
        mm_trans = MyMemoryTranslator(source='auto', target=dest).translate(word)
        if mm_trans:
            return mm_trans
    except Exception as e:
        logging.debug(f"deep_translator MyMemoryTranslator failed: {e}")

    # All failed, return original word
    return word

if __name__ == "__main__":
    word_to_test = "love"
    translated_word = translate_word(word_to_test, dest='es')
    print(f"Original: {word_to_test}")
    print(f"Translated (ES): {translated_word}")
