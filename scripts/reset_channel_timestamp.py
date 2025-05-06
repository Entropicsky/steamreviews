#!/usr/bin/env python
# scripts/reset_channel_timestamp.py
import logging
import os
import sys
import argparse
from dotenv import load_dotenv
from datetime import datetime, timezone

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.connection import get_db
from src.database.crud_youtube import update_channel_timestamp, get_channel_by_id

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_timestamp(channel_id_to_reset: str, new_timestamp_unix: int = 0):
    logger.info(f"Attempting to reset timestamp for channel ID: {channel_id_to_reset} to {new_timestamp_unix} ({datetime.fromtimestamp(new_timestamp_unix, tz=timezone.utc)})")
    load_dotenv()

    db_gen = get_db()
    db = next(db_gen)

    try:
        # Verify channel exists first
        channel = get_channel_by_id(db, channel_id_to_reset)
        if not channel:
            logger.error(f"Channel with ID '{channel_id_to_reset}' not found in the database.")
            return
        
        logger.info(f"Found channel: {channel.channel_name or 'N/A'} ({channel.handle or 'N/A'}). Current timestamp: {channel.last_checked_timestamp}")

        success = update_channel_timestamp(db, channel_id_to_reset, new_timestamp_unix)

        if success:
            logger.info(f"Successfully updated timestamp for channel {channel_id_to_reset} to {new_timestamp_unix}.")
            # Verify
            db.refresh(channel) # Refresh the object to get the updated value
            logger.info(f"Verified new timestamp in DB: {channel.last_checked_timestamp}")
        else:
            logger.error(f"Failed to update timestamp for channel {channel_id_to_reset}.")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        if db:
            db.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reset the last_checked_timestamp for a YouTube channel.')
    parser.add_argument('channel_id', type=str, help='The database ID (UC...) of the channel to reset.')
    parser.add_argument('--timestamp', type=int, default=0, help='The new UNIX timestamp to set (default: 0).')

    args = parser.parse_args()
    reset_timestamp(args.channel_id, args.timestamp) 