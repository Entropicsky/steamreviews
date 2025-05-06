#!/usr/bin/env python
# scripts/check_video_status.py
import logging
import os
import sys
import argparse
from dotenv import load_dotenv

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.connection import get_db
from src.database.crud_youtube import get_video_by_id

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_status(video_id_to_check: str):
    logger.info(f"Checking status for video ID: {video_id_to_check}")
    load_dotenv()

    db_gen = get_db()
    db = next(db_gen)

    try:
        video = get_video_by_id(db, video_id_to_check)

        if not video:
            logger.error(f"Video with ID '{video_id_to_check}' not found in the database.")
            return

        logger.info(f"--- Status for Video ID: {video.id} ---")
        logger.info(f"Title: {video.title}")
        logger.info(f"Transcript Status: {video.transcript_status}")
        logger.info(f"Analysis Status: {video.analysis_status}")
        logger.info(f"----------------------------------------")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        if db:
            db.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check the status of a specific YouTube video in the database.')
    parser.add_argument('video_id', type=str, help='The ID of the video to check.')

    args = parser.parse_args()
    check_status(args.video_id) 