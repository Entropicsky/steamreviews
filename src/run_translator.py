#!/usr/bin/env python3
"""
Translation Processing Script

Queries the database for reviews needing translation, calls the OpenAI API
via the Translator service, and updates the database with results.

Run using: python -m src.run_translator
"""

import logging
import sys
import os
import time

# Adjust path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from .database.connection import get_db
from .database import crud, models
from .processing.translator import Translator
from .openai_client import OPENAI_MODEL # Import default model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration ---
BATCH_SIZE = 50 # How many reviews to fetch from DB at a time
SLEEP_BETWEEN_BATCHES = 5 # Seconds to sleep if no reviews found
# Consider adding rate limit handling if processing many reviews quickly

def process_translations():
    logger.info("Starting translation processing run...")
    processed_count = 0
    failed_count = 0
    skipped_count = 0

    # Keep track of translators per app_id to reuse cache
    translators: dict[str, Translator] = {}

    # Use context manager for DB session
    db_session_gen = get_db()
    db: Session = next(db_session_gen)

    try:
        while True: # Keep running until no more pending reviews found in a batch
            logger.info(f"Querying for up to {BATCH_SIZE} reviews needing translation...")
            reviews_to_translate = crud.get_reviews_needing_translation(db, limit=BATCH_SIZE)

            if not reviews_to_translate:
                logger.info("No more reviews found needing translation in this batch. Sleeping...")
                break # Exit the loop if no reviews found

            logger.info(f"Found {len(reviews_to_translate)} reviews to process.")

            for review in reviews_to_translate:
                if review.app_id not in translators:
                    # Initialize translator for this app_id (loads cache)
                    translators[review.app_id] = Translator(app_id=str(review.app_id))
                
                translator = translators[review.app_id]

                logger.debug(f"Processing review {review.recommendationid} (Lang: {review.original_language})...")
                
                translation_result = translator.translate_review_text(
                    text=review.original_review_text,
                    original_language_code=review.original_language
                )

                status = 'failed' # Default status
                if translation_result is not None and not translation_result.startswith("[REFUSAL"):
                    status = 'translated'
                    processed_count += 1
                elif translation_result and translation_result.startswith("[REFUSAL"):
                     status = 'skipped' # Mark refused as skipped for now
                     skipped_count += 1
                else:
                    failed_count += 1
                    # Keep translation_result as None or empty for failed cases
                    translation_result = None 

                # Update DB
                crud.update_review_translation(
                    db=db,
                    recommendation_id=review.recommendationid,
                    translation=translation_result, # Will be None if failed
                    model=translator.model, # Get model used
                    status=status
                )
                logger.debug(f"Updated review {review.recommendationid} status to {status}")
                
                # Optional: Add small delay between API calls
                time.sleep(0.2)

            # If we processed a full batch, maybe there are more? Loop again.
            # If we processed less than a full batch, we likely got all pending ones.
            if len(reviews_to_translate) < BATCH_SIZE:
                 logger.info("Processed partial batch, likely finished pending reviews.")
                 break # Exit loop
            else:
                 logger.info("Processed full batch, checking for more...")
                 # Optional: Add a longer sleep between full batches
                 # time.sleep(2)

    except Exception as e:
        logger.exception(f"An error occurred during translation processing: {e}")
    finally:
        logger.info("Closing database session.")
        try:
            next(db_session_gen) # Ensure session is closed
        except StopIteration:
            pass
        except Exception as e:
             logger.error(f"Error closing DB session: {e}")

    logger.info(f"Translation processing finished. Translated: {processed_count}, Failed: {failed_count}, Skipped (Refused): {skipped_count}")

if __name__ == "__main__":
    process_translations() 