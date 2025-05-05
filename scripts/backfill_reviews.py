#!/usr/bin/env python3
"""
Backfill Script

Fetches *all* historical reviews for a specific app_id using the Steam API's
cursor pagination and inserts them into the database, ignoring conflicts.

Usage:
    python scripts/backfill_reviews.py --app-id <app_id_to_backfill>
"""

import logging
import sys
import os
import argparse
import time

# Adjust path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database import crud, models
from src.steam_client import SteamAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

def backfill_app(app_id: int):
    logger.info(f"--- Starting Backfill for App ID: {app_id} ---")
    db_session_gen = get_db()
    db = next(db_session_gen)
    steam_api = SteamAPI()
    total_fetched_this_run = 0
    page_num = 0
    cursor = "*"

    try:
        while True: 
            page_num += 1
            logger.info(f"Backfilling App {app_id} - Fetching page {page_num} with cursor: {cursor[:10]}...")
            
            reviews_batch, highest_ts_in_batch, next_cursor = steam_api.fetch_reviews(
                appid=app_id,
                language='all',
                after_timestamp=None,
                cursor=cursor
            )
            
            if not reviews_batch:
                 logger.info(f"No more reviews found for App ID {app_id} on page {page_num}. Backfill likely complete.")
                 break 
            
            batch_size = len(reviews_batch)
            total_fetched_this_run += batch_size
            logger.info(f"Fetched {batch_size} reviews from page {page_num}. Total fetched this run: {total_fetched_this_run}")

            # --- Process and Insert THIS BATCH --- 
            reviews_to_insert = []
            for review_obj in reviews_batch:
                 is_english = review_obj.language == 'english'
                 insert_dict = {
                    "recommendationid": review_obj.recommendationid,
                    "app_id": review_obj.appid,
                    "author_steamid": review_obj.author.steamid,
                    "original_language": review_obj.language,
                    "original_review_text": review_obj.review_text,
                    "english_translation": review_obj.review_text if is_english else None,
                    "translation_status": 'not_required' if is_english else 'pending',
                    "analysis_status": 'pending',
                    "timestamp_created": review_obj.timestamp_created,
                    "timestamp_updated": review_obj.timestamp_updated,
                    "voted_up": review_obj.voted_up,
                    "votes_up": review_obj.votes_up,
                    "votes_funny": review_obj.votes_funny,
                    "weighted_vote_score": review_obj.weighted_vote_score,
                    "comment_count": review_obj.comment_count,
                    "steam_purchase": review_obj.steam_purchase,
                    "received_for_free": review_obj.received_for_free,
                    "written_during_early_access": review_obj.written_during_early_access,
                    "developer_response": review_obj.developer_response,
                    "timestamp_dev_responded": review_obj.timestamp_dev_responded,
                    "author_num_games_owned": review_obj.author.num_games_owned,
                    "author_num_reviews": review_obj.author.num_reviews,
                    "author_playtime_forever": review_obj.author.playtime_forever,
                    "author_playtime_last_two_weeks": review_obj.author.playtime_last_two_weeks,
                    "author_playtime_at_review": review_obj.author.playtime_at_review,
                    "author_last_played": review_obj.author.last_played
                 }
                 reviews_to_insert.append(insert_dict)

            # Insert the current batch immediately
            if reviews_to_insert:
                logger.info(f"--->>> Calling add_reviews_bulk for {len(reviews_to_insert)} reviews (Page {page_num}) <<<---")
                try:
                    crud.add_reviews_bulk(db, reviews_to_insert)
                    logger.info(f"--->>> Finished add_reviews_bulk for page {page_num} successfully <<<---")
                except Exception as insert_err:
                     logger.error(f"--->>> EXCEPTION during add_reviews_bulk for page {page_num}: {insert_err} <<<---")
                     # Decide whether to break or continue on insert error
                     # Let's break for now to investigate
                     raise # Re-raise the exception to stop the script
            # --- End Batch Insertion --- 
            
            # Update cursor for next page
            if not next_cursor:
                 logger.info("No next cursor provided by Steam API. Ending backfill.")
                 break
            cursor = next_cursor

            time.sleep(2) # Keep the sleep between page fetches

        # === After Loop: Get Max Timestamp from DB and Update ===
        logger.info(f"Backfill fetch complete for {app_id}. Querying max timestamp from DB...")
        max_timestamp_from_db = crud.get_max_review_timestamp_for_app(db, app_id)

        if max_timestamp_from_db is not None and max_timestamp_from_db > 0:
             logger.info(f"Updating last_fetched_timestamp for app {app_id} to {max_timestamp_from_db} based on DB MAX.")
             crud.update_last_fetch_time(db, app_id, max_timestamp_from_db)
        else:
             # If no reviews were inserted OR max query failed, maybe don't update?
             # Or update to 0? Let's log a warning and not update.
             logger.warning(f"Could not retrieve valid max timestamp from DB for app {app_id}. last_fetched_timestamp not updated.")

    except Exception as e:
        logger.exception(f"An error occurred during backfill for app {app_id}: {e}")
    finally:
        logger.info("Closing database session for backfill.")
        try:
            next(db_session_gen)
        except StopIteration:
            pass
        except Exception as e:
            logger.error(f"Error closing DB session: {e}")
    
    logger.info(f"--- Finished Backfill for App ID: {app_id}. Total Reviews Fetched: {total_fetched_this_run} ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Steam reviews for a specific app ID.")
    parser.add_argument("-a", "--app-id", type=int, required=True,
                        help="The Steam App ID to backfill reviews for.")
    args = parser.parse_args()

    backfill_app(args.app_id) 