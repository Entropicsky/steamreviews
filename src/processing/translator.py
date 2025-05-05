import os
import json
import logging
import time
from typing import List, Dict, Optional

# Adjust path to import from sibling directories
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.models import Review # Import Review model
from openai_client import call_openai_api, OPENAI_MODEL # Import API call function and default model
from constants import LANGUAGE_MAP # Import from constants

logger = logging.getLogger(__name__)

# Define CACHE_DIR within this module (or pass via config later)
CACHE_DIR = os.getenv("CACHE_DIR", "data")
os.makedirs(CACHE_DIR, exist_ok=True)

class Translator:
    """Handles translation of reviews using OpenAI's API (Thread-safe cache handling)."""

    def __init__(self, app_id: str, model: str = OPENAI_MODEL):
        """Initialize Translator. Loads cache once."""
        self.model = model
        self.app_id = app_id
        self.cache_file = os.path.join(CACHE_DIR, f"translations_{self.app_id}_cache.json")
        # Load cache into memory during initialization
        self.translation_cache = self._load_cache()
        logger.info(f"Translator initialized for app {app_id}. Cache size: {len(self.translation_cache)}")

    def _load_cache(self) -> Dict[str, str]:
        """Load translation cache from file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    # Add basic validation if needed
                    data = json.load(f)
                    if isinstance(data, dict):
                        logger.info(f"Loaded {len(data)} translations from cache: {self.cache_file}")
                        return data
                    else:
                        logger.warning(f"Cache file {self.cache_file} has invalid format. Ignoring.")
            except Exception as e:
                logger.warning(f"Translation cache loading failed for {self.cache_file}: {e}")
        return {}

    def save_cache(self) -> None: # Make save public for explicit call
        """Save the current in-memory translation cache to file."""
        logger.info(f"Saving translation cache ({len(self.translation_cache)} items) to {self.cache_file}")
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.translation_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save translation cache {self.cache_file}: {e}")

    def translate_review_text(self, text: str, original_language_code: str) -> Optional[str]:
        """Translates text. Updates in-memory cache, does NOT save file here."""
        cache_key = f"{original_language_code}:{text}"

        if not text or not text.strip():
            logger.debug("Empty text provided for translation.")
            return "" # Return empty string for empty input

        # Check in-memory cache
        if cache_key in self.translation_cache:
            logger.debug(f"Using cached translation for key: {cache_key[:50]}...")
            return self.translation_cache[cache_key]

        # Get the full language name for the prompt
        language_name = LANGUAGE_MAP.get(original_language_code, original_language_code)

        # --- Translation Prompt ---
        prompt = [
            {
                "role": "system",
                "content": f"You are a professional translator specialized in translating game reviews from {language_name} to English. The input is a Steam review text. Your goal is to accurately translate the user's text to English, preserving the original tone, style, and intent as closely as possible.\n\nIf the text is very short, contains potential slang, typos, or seems unclear, translate it directly to English to the best of your ability. **Do not add commentary about the input quality or explain difficulties in translation.** If a direct translation is truly impossible, you may indicate this concisely (e.g., by returning the original text or '[untranslatable]')."
            },
            {
                "role": "user",
                "content": f"Translate this {language_name} Steam review text to English: {text}"
            }
        ]

        try:
            translated_text = call_openai_api(
                prompt=prompt,
                model=self.model,
                temperature=0.3
            )

            if translated_text is not None and not translated_text.startswith("[REFUSAL"):
                logger.debug(f"Successfully translated text from {language_name}.")
                # Update IN-MEMORY cache only
                self.translation_cache[cache_key] = translated_text 
                # DO NOT SAVE FILE HERE: self._save_cache()
                return translated_text
            elif translated_text and translated_text.startswith("[REFUSAL"):
                 logger.warning(f"Translation refused for key {cache_key[:50]}...: {translated_text}")
                 # Store refusal message in cache?
                 # self.translation_cache[cache_key] = translated_text
                 # self._save_cache()
                 return translated_text # Return refusal message
            else:
                logger.error(f"Translation failed for key {cache_key[:50]}... (API returned None)")
                return None # Indicate failure explicitly

        except Exception as e:
             logger.error(f"Exception during translation API call for key {cache_key[:50]}...: {e}")
             return None # Indicate failure explicitly

    # Optional: Keep batch translate method if needed elsewhere, but core logic is now text-based
    # def batch_translate(self, reviews: List[Review], batch_size: int = 10) -> List[Review]: ... 