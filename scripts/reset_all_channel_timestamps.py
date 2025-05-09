#!/usr/bin/env python
# scripts/reset_all_channel_timestamps.py
import logging
import os
import sys
from dotenv import load_dotenv
from datetime import datetime, timezone

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.connection import get_db, SessionLocal
from src.database.models import YouTubeChannel
from src.database.crud_youtube import update_channel_timestamp # Re-use existing function if suitable, or direct update

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s')
logger = logging.getLogger(__name__)

def reset_all_timestamps():
    logger.info("Attempting to reset last_checked_timestamp to 0 for ALL YouTube channels...")
    load_dotenv() # Ensure DB_URL is loaded if running locally and defined in .env

    db_session_gen = get_db()
    db = next(db_session_gen)
    
    updated_count = 0
    failed_count = 0

    try:
        channels = db.query(YouTubeChannel).all()
        if not channels:
            logger.info("No channels found in the database.")
            return

        logger.info(f"Found {len(channels)} channels to process.")

        for channel in channels:
            logger.info(f"Processing channel: {channel.id} ({channel.handle or channel.channel_name or 'N/A'}). Current timestamp: {channel.last_checked_timestamp}")
            try:
                # Option 1: Use existing crud function if it's efficient for bulk updates (might commit per call)
                # success = update_channel_timestamp(db, channel.id, 0) 
                
                # Option 2: Direct update for efficiency, then one commit at the end.
                # For SQLAlchemy 1.x style (assuming current models):
                channel.last_checked_timestamp = 0
                # For SQLAlchemy 2.0 style, direct update statement might be better for true bulk if not already using it.
                # Let's stick to instance update for now as crud.update_channel_timestamp does a commit per call.
                
                # If update_channel_timestamp commits internally, we call it.
                # Otherwise, we set field and commit once.
                # Given the existing function name, it likely commits.
                # Let's modify to set and then do a single commit for efficiency.
                
                # Re-evaluating: The existing update_channel_timestamp executes and commits.
                # For simplicity and to reuse existing code, let's call it.
                # If performance is an issue on many channels, we can refactor this script.
                
                # Re-evaluating: The existing update_channel_timestamp executes and commits.
                # For simplicity and to reuse existing code, let's call it.
                # If performance is an issue on many channels, we can refactor this script.
                
                success = update_channel_timestamp(db, channel.id, 0) # This will commit per channel.

                if success:
                    logger.info(f"Successfully reset timestamp for channel {channel.id} to 0.")
                    updated_count += 1
                else:
                    # This else might not be hit if update_channel_timestamp raises an error on failure
                    # or if rowcount is 0 but no error (which shouldn't happen if channel was queried).
                    logger.warning(f"Failed to reset timestamp for channel {channel.id} (update_channel_timestamp returned False).")
                    failed_count += 1
            except Exception as e_channel:
                logger.error(f"Error resetting timestamp for channel {channel.id}: {e_channel}", exc_info=True)
                failed_count += 1
                db.rollback() # Rollback this specific channel's attempt if using individual commits in loop, or for main commit if one commit

        # If not committing per channel in the loop:
        # logger.info("Committing all timestamp resets...")
        # db.commit() 
        # logger.info("All changes committed.")

    except Exception as e_main:
        logger.error(f"An error occurred during the main process: {e_main}", exc_info=True)
        db.rollback()
    finally:
        logger.info(f"Timestamp reset process finished. Successfully updated: {updated_count}, Failed: {failed_count}.")
        try:
            next(db_session_gen) # Proper way to close session from get_db generator
        except StopIteration:
            pass # Generator exhausted
        except Exception as e_close:
            logger.error(f"Error closing DB session: {e_close}")
        logger.info("Database connection procedure finished.")

if __name__ == "__main__":
    reset_all_timestamps() 