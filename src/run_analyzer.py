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

# Adjust path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from .database.connection import get_db
from .database import crud, models
from .processing.analyzer import ReviewAnalyzer
from .openai_client import OPENAI_MODEL # Import default model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration ---
BATCH_SIZE = 20 # Smaller batch for potentially longer analysis calls
SLEEP_BETWEEN_BATCHES = 5 # Seconds

def process_analysis():
    logger.info("Starting analysis processing run...")
    processed_count = 0
    failed_count = 0
    skipped_count = 0 # For refused analysis

    analyzer = ReviewAnalyzer() # Initialize analyzer (uses default model)

    # Use context manager for DB session
    db_session_gen = get_db()
    db: Session = next(db_session_gen)

    try:
        while True: # Keep running until no more pending reviews found in a batch
            logger.info(f"Querying for up to {BATCH_SIZE} reviews needing analysis...")
            reviews_to_analyze = crud.get_reviews_needing_analysis(db, limit=BATCH_SIZE)

            if not reviews_to_analyze:
                logger.info("No more reviews found needing analysis in this batch. Sleeping...")
                break

            logger.info(f"Found {len(reviews_to_analyze)} reviews to process.")

            for review in reviews_to_analyze:
                logger.debug(f"Processing review {review.recommendationid} for analysis...")
                
                # Simplify: Always use english_translation as it should be populated
                # for both 'translated' and 'not_required' (English) reviews.
                text_to_analyze = review.english_translation
                
                # Add a check for empty/null text just in case
                if not text_to_analyze or not text_to_analyze.strip():
                     logger.warning(f"Skipping analysis for review {review.recommendationid}: english_translation field is empty or null. Setting status to failed.")
                     # Update status to failed even if text is missing
                     crud.update_review_analysis(db, review.recommendationid, {}, 'failed')
                     failed_count += 1
                     continue

                # Proceed with analysis using text_to_analyze
                analysis_result_dict = analyzer.analyze_review_text(text_to_analyze)

                status = 'failed' # Default status
                if isinstance(analysis_result_dict, dict) and 'error' not in analysis_result_dict:
                    status = 'analyzed'
                    processed_count += 1
                elif isinstance(analysis_result_dict, dict) and analysis_result_dict.get('error') == "Model refused analysis request":
                    status = 'skipped' # Mark refused as skipped
                    skipped_count += 1
                else:
                     failed_count += 1
                
                # Update DB
                crud.update_review_analysis(
                    db=db,
                    recommendation_id=review.recommendationid,
                    analysis_data=analysis_result_dict, # Pass the whole dict (contains error or data)
                    status=status
                )
                logger.debug(f"Updated review {review.recommendationid} analysis status to {status}")

                # Optional: Add small delay
                time.sleep(0.5)

            # Check if loop should continue
            if len(reviews_to_analyze) < BATCH_SIZE:
                 logger.info("Processed partial batch, likely finished pending reviews for analysis.")
                 break
            else:
                 logger.info("Processed full batch, checking for more...")

    except Exception as e:
        logger.exception(f"An error occurred during analysis processing: {e}")
    finally:
        logger.info("Closing database session.")
        try:
            next(db_session_gen) # Ensure session is closed
        except StopIteration:
            pass
        except Exception as e:
             logger.error(f"Error closing DB session: {e}")

    logger.info(f"Analysis processing finished. Analyzed: {processed_count}, Failed: {failed_count}, Skipped (Refused): {skipped_count}")

if __name__ == "__main__":
    process_analysis() 