#!/usr/bin/env python
# scripts/reset_video_analysis_status.py
import logging
import os
import sys
import argparse
from dotenv import load_dotenv

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.connection import get_db
from src.database.crud_youtube import update_video_analysis_status, get_video_by_id

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Target status to reset to
TARGET_STATUS = 'pending'

def reset_status(video_id_to_reset: str):
    logger.info(f"Attempting to reset analysis_status for video ID: {video_id_to_reset} to '{TARGET_STATUS}'")
    load_dotenv()

    db_gen = get_db()
    db = next(db_gen)

    try:
        # Verify video exists first
        video = get_video_by_id(db, video_id_to_reset)
        if not video:
            logger.error(f"Video with ID '{video_id_to_reset}' not found in the database.")
            return
        
        logger.info(f"Found video: {video.title or 'N/A'}. Current analysis_status: {video.analysis_status}")

        if video.analysis_status == TARGET_STATUS:
            logger.warning(f"Video {video_id_to_reset} analysis_status is already '{TARGET_STATUS}'. No update needed.")
            return

        success = update_video_analysis_status(db, video_id_to_reset, TARGET_STATUS)

        if success:
            logger.info(f"Successfully updated analysis_status for video {video_id_to_reset} to '{TARGET_STATUS}'.")
            # Verify
            db.refresh(video) # Refresh the object to get the updated value
            logger.info(f"Verified new analysis_status in DB: {video.analysis_status}")
        else:
            logger.error(f"Failed to update analysis_status for video {video_id_to_reset}.")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        if db:
            db.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f'Reset the analysis_status of a specific YouTube video to \'{TARGET_STATUS}\'.')
    parser.add_argument('video_id', type=str, help='The ID of the video to reset.')

    args = parser.parse_args()
    reset_status(args.video_id) 