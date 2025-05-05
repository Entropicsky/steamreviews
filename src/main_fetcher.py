#!/usr/bin/env python3
"""
Main Fetcher Script

Orchestrates the process of fetching new Steam reviews for tracked apps,
and potentially triggers subsequent processing steps (translation, analysis).

Run using: python -m src.main_fetcher
"""

import logging
import sys
import os
from typing import List

# Adjust path if needed, though running with -m should handle imports
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .database.connection import get_db
from .database import crud, models
from .steam_client import SteamAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

def run_fetcher():
    logger.info("Starting fetcher run...")
    db_session_gen = get_db()
    db = next(db_session_gen)
    steam_api = SteamAPI()

    try:
        apps_to_check = crud.get_active_tracked_apps(db)
        if not apps_to_check:
            logger.info("No active apps configured in tracked_apps table.")
            return # Exit early if no apps to process

        logger.info(f"Found {len(apps_to_check)} active apps to check.")

        for app in apps_to_check:
            logger.info(f"---")
            logger.info(f"Processing App ID: {app.app_id} (Name: {app.name})")
            last_fetch = app.last_fetched_timestamp or 0 # Default to 0 if null
            logger.info(f"Last fetched timestamp: {last_fetch}")

            try:
                # === Fetching New Reviews ===
                logger.info(f"Fetching new reviews (language='all') for App ID {app.app_id} after timestamp {last_fetch}...")
                # Call the updated fetch_reviews - unpack all 3 returned values
                new_reviews, highest_ts_in_run, _ = steam_api.fetch_reviews(
                    appid=app.app_id,
                    language='all',
                    after_timestamp=last_fetch
                )

                if not new_reviews:
                    logger.info(f"No new reviews found for App ID {app.app_id}.")
                    # Optionally update timestamp even if no reviews? For now, only update if reviews found.
                    continue # Go to next app

                logger.info(f"Fetched {len(new_reviews)} new reviews for App ID {app.app_id}. Highest timestamp in run: {highest_ts_in_run}")

                # === Step 3.3: Store new reviews in DB ===
                reviews_to_insert = []
                for review_obj in new_reviews:
                    # Explicitly map SQLAlchemy model attributes to DB column names dictionary
                    is_english = review_obj.language == 'english'
                    insert_dict = {
                        "recommendationid": review_obj.recommendationid,
                        "app_id": review_obj.appid,
                        "author_steamid": review_obj.author.steamid,
                        "original_language": review_obj.language,
                        "original_review_text": review_obj.review_text,
                        # Copy original text if English, otherwise leave null for translator
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

                if reviews_to_insert:
                    logger.info(f"Attempting to bulk insert/ignore {len(reviews_to_insert)} reviews...")
                    crud.add_reviews_bulk(db, reviews_to_insert)
                # === End Step 3.3 ===

                # === Step 3.4: Update last fetched timestamp ===
                if highest_ts_in_run > last_fetch:
                    logger.info(f"Updating last_fetched_timestamp for app {app.app_id} to {highest_ts_in_run}")
                    crud.update_last_fetch_time(db, app.app_id, highest_ts_in_run)
                else:
                    logger.info(f"No newer reviews found, last_fetched_timestamp for app {app.app_id} remains {last_fetch}")
                # === End Step 3.4 ===

            except Exception as fetch_err:
                logger.exception(f"Error processing app {app.app_id}: {fetch_err}")
                # Continue to the next app

    except Exception as e:
        logger.exception(f"An error occurred during the fetcher run: {e}")
    finally:
        logger.info("Closing database session.")
        try:
            next(db_session_gen)
        except StopIteration:
            pass # Expected
        except Exception as e:
             logger.error(f"Error closing DB session: {e}")

    logger.info("Fetcher run finished.")

if __name__ == "__main__":
    run_fetcher() 