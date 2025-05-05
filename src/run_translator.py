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
import concurrent.futures
from functools import partial
from typing import Optional, Dict

# Adjust path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from .database.connection import get_db, SessionLocal # Need SessionLocal for threads
from .database import crud, models
from .processing.translator import Translator
from .openai_client import OPENAI_MODEL # Import default model

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
# Explicitly set level for the CRUD logger
logging.getLogger('src.database.crud').setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

# --- Configuration ---
BATCH_SIZE = 50 # How many reviews to fetch from DB at a time
MAX_WORKERS = 8 # Max concurrent API calls
# SLEEP_BETWEEN_BATCHES = 5 # Less needed now?

def _process_single_translation(review: models.Review, translator: Translator) -> tuple[int, str, Optional[str]]:
    """Helper function to translate one review and return result for DB update.
       Designed to be run in a separate thread.
    """
    recommendation_id = review.recommendationid
    logger.debug(f"Thread processing review {recommendation_id} (Lang: {review.original_language})...")
    
    translation_result = translator.translate_review_text(
        text=review.original_review_text,
        original_language_code=review.original_language
    )
    
    status = 'failed'
    if translation_result is not None and not translation_result.startswith("[REFUSAL"):
        status = 'translated'
    elif translation_result and translation_result.startswith("[REFUSAL"):
        status = 'skipped'
    
    # Get DB session using the dependency function with context manager
    db_session_gen = get_db()
    thread_db: Session = next(db_session_gen)
    try:
        crud.update_review_translation(
            db=thread_db,
            recommendation_id=recommendation_id,
            translation=translation_result,
            model=translator.model, 
            status=status
        )
        logger.debug(f"Thread updated review {recommendation_id} status to {status}")
        return (recommendation_id, status, None) # Return success status
    except Exception as e:
         logger.error(f"Thread DB update failed for review {recommendation_id}: {e}")
         return (recommendation_id, 'failed', str(e)) # Return fail status and error
    finally:
        # Ensure the session from get_db is closed correctly
        try:
            next(db_session_gen)
        except StopIteration:
             pass # Expected if generator already yielded and finished
        except Exception as close_err:
              logger.error(f"Error closing DB session in thread for review {recommendation_id}: {close_err}")

def process_translations():
    logger.info("Starting translation processing run (multi-threaded)...")
    total_processed_count = 0
    total_failed_count = 0
    total_skipped_count = 0

    # Keep track of translators per app_id 
    translators: Dict[int, Translator] = {}

    # Use outer DB session only for querying batches
    db_session_gen = get_db()
    db: Session = next(db_session_gen)

    try:
        while True: 
            logger.info(f"Querying for up to {BATCH_SIZE} reviews needing translation...")
            reviews_to_translate = crud.get_reviews_needing_translation(db, limit=BATCH_SIZE)

            if not reviews_to_translate:
                logger.info("No more reviews found needing translation. Exiting loop.")
                break 

            logger.info(f"Found {len(reviews_to_translate)} reviews to process in this batch.")
            batch_results = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_map = {}
                for review in reviews_to_translate:
                    # Ensure translator instance exists for the app_id
                    if review.app_id not in translators:
                        logger.info(f"Initializing translator for app {review.app_id}")
                        translators[review.app_id] = Translator(app_id=str(review.app_id))
                    translator_instance = translators[review.app_id]
                    
                    # Submit task to thread pool
                    future = executor.submit(_process_single_translation, review, translator_instance)
                    future_map[future] = review.recommendationid # Map future to review ID for logging

                # Process results as they complete
                for future in concurrent.futures.as_completed(future_map):
                    rec_id = future_map[future]
                    try:
                        result_id, status, error_msg = future.result()
                        batch_results.append(status)
                        if status == 'translated':
                            total_processed_count += 1
                        elif status == 'skipped':
                             total_skipped_count += 1
                        else:
                            total_failed_count += 1
                            logger.warning(f"Translation/Update failed for review {result_id}: {error_msg}")
                    except Exception as exc:
                        logger.error(f"Review {rec_id} generated an exception in thread: {exc}")
                        total_failed_count += 1
                        batch_results.append('failed')

            logger.info(f"Batch finished. Results - Translated: {batch_results.count('translated')}, Skipped: {batch_results.count('skipped')}, Failed: {batch_results.count('failed')}")

            if len(reviews_to_translate) < BATCH_SIZE:
                 logger.info("Processed partial batch, likely finished all pending reviews.")
                 break 
            else:
                 logger.info("Processed full batch, fetching next batch...")
                 # Optional shorter sleep between batches now
                 time.sleep(1)

    except Exception as e:
        logger.exception(f"An error occurred during the main translation processing loop: {e}")
    finally:
        # Save all caches at the end
        logger.info("Saving all translator caches...")
        for app_id, translator_instance in translators.items():
            translator_instance.save_cache()
        
        logger.info("Closing main database session.")
        try:
            next(db_session_gen)
        except StopIteration:
            pass
        except Exception as e:
             logger.error(f"Error closing main DB session: {e}")

    logger.info(f"Translation processing finished. Total Translated: {total_processed_count}, Total Failed: {total_failed_count}, Total Skipped: {total_skipped_count}")

if __name__ == "__main__":
    process_translations() 