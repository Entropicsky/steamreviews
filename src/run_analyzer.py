#!/usr/bin/env python3
"""
Analysis Processing Script

Queries the database for reviews ready for analysis (translated or originally English),
calls the OpenAI API via the ReviewAnalyzer service for structured data extraction,
and updates the database with results.

Run using: python -m src.run_analyzer
"""

import logging
import sys
import os
import time
import concurrent.futures
from typing import Optional

# Adjust path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from .database.connection import get_db, SessionLocal
from .database import crud, models
from .processing.analyzer import ReviewAnalyzer
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
BATCH_SIZE = 20 # Smaller batch for potentially longer analysis calls
MAX_WORKERS = 8 # Max concurrent analysis API calls
# SLEEP_BETWEEN_BATCHES = 5 # Seconds

def _process_single_analysis(review: models.Review, analyzer: ReviewAnalyzer) -> tuple[int, str, Optional[str]]:
    """Helper function to analyze one review and return result for DB update.
       Designed to be run in a separate thread.
    """
    recommendation_id = review.recommendationid
    logger.debug(f"Thread processing review {recommendation_id} for analysis...")

    text_to_analyze = None
    if review.translation_status == 'translated' and review.english_translation:
        text_to_analyze = review.english_translation
    elif review.original_language == 'english':
            text_to_analyze = review.original_review_text
    
    if not text_to_analyze or not text_to_analyze.strip():
        logger.warning(f"Thread skipping analysis for review {recommendation_id}: No suitable text.")
        # Update status to failed directly here?
        thread_db: Session = SessionLocal()
        try:
            crud.update_review_analysis(thread_db, recommendation_id, {}, 'failed')
            return (recommendation_id, 'failed', "No text available")
        except Exception as db_err:
            logger.error(f"Thread DB update failed for skipped analysis {recommendation_id}: {db_err}")
            return (recommendation_id, 'failed', f"DB error on skip: {db_err}")
        finally:
            thread_db.close()

    analysis_result_dict = analyzer.analyze_review_text(text_to_analyze)

    status = 'failed'
    if isinstance(analysis_result_dict, dict) and 'error' not in analysis_result_dict:
        status = 'analyzed'
    elif isinstance(analysis_result_dict, dict) and analysis_result_dict.get('error') == "Model refused analysis request":
        status = 'skipped'
    
    # Update DB in this thread
    thread_db: Session = SessionLocal()
    try:
        crud.update_review_analysis(
            db=thread_db,
            recommendation_id=recommendation_id,
            analysis_data=analysis_result_dict,
            status=status
        )
        logger.debug(f"Thread updated review {recommendation_id} analysis status to {status}")
        return (recommendation_id, status, analysis_result_dict.get('error')) # Return status and maybe error
    except Exception as e:
        logger.error(f"Thread DB update failed for analysis {recommendation_id}: {e}")
        return (recommendation_id, 'failed', str(e)) # Return fail status and error
    finally:
        thread_db.close()

def process_analysis():
    logger.info("Starting analysis processing run (multi-threaded)...")
    total_processed_count = 0
    total_failed_count = 0
    total_skipped_count = 0

    analyzer = ReviewAnalyzer() # One analyzer instance is likely fine

    # Use outer DB session for querying batches
    db_session_gen = get_db()
    db: Session = next(db_session_gen)

    try:
        while True: 
            logger.info(f"Querying for up to {BATCH_SIZE} reviews needing analysis...")
            reviews_to_analyze = crud.get_reviews_needing_analysis(db, limit=BATCH_SIZE)

            if not reviews_to_analyze:
                logger.info("No more reviews found needing analysis. Exiting loop.")
                break

            logger.info(f"Found {len(reviews_to_analyze)} reviews to process in this batch.")
            batch_results = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # Pass the shared analyzer instance to the worker function
                # partial_process_func = partial(_process_single_analysis, analyzer=analyzer)
                # executor.map is simpler if we only pass one varying argument (review)
                # Use submit to handle passing both review and analyzer
                future_map = {}
                for review in reviews_to_analyze:
                    future = executor.submit(_process_single_analysis, review, analyzer)
                    future_map[future] = review.recommendationid
                
                for future in concurrent.futures.as_completed(future_map):
                    rec_id = future_map[future]
                    try:
                        result_id, status, error_msg = future.result()
                        batch_results.append(status)
                        if status == 'analyzed':
                            total_processed_count += 1
                        elif status == 'skipped':
                            total_skipped_count += 1
                        else:
                            total_failed_count += 1
                            logger.warning(f"Analysis/Update failed for review {result_id}: {error_msg}")
                    except Exception as exc:
                        logger.error(f"Review {rec_id} generated an exception in analysis thread: {exc}")
                        total_failed_count += 1
                        batch_results.append('failed')
            
            logger.info(f"Batch finished. Results - Analyzed: {batch_results.count('analyzed')}, Skipped: {batch_results.count('skipped')}, Failed: {batch_results.count('failed')}")

            if len(reviews_to_analyze) < BATCH_SIZE:
                 logger.info("Processed partial batch, likely finished all pending reviews for analysis.")
                 break
            else:
                 logger.info("Processed full batch, fetching next batch...")
                 time.sleep(1)

    except Exception as e:
        logger.exception(f"An error occurred during the main analysis processing loop: {e}")
    finally:
        logger.info("Closing main database session.")
        try:
            next(db_session_gen) 
        except StopIteration:
            pass
        except Exception as e:
             logger.error(f"Error closing main DB session: {e}")

    logger.info(f"Analysis processing finished. Total Analyzed: {total_processed_count}, Total Failed: {total_failed_count}, Total Skipped: {total_skipped_count}")

if __name__ == "__main__":
    process_analysis() 