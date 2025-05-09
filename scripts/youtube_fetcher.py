#!/usr/bin/env python3
"""
YouTube Feedback Fetcher Script

Fetches new YouTube videos for tracked influencers/games, 
retrieves metadata and transcripts using the Supadata API, 
and stores the raw data in the database for later analysis.

Designed to be run as a scheduled job (e.g., via cron or Heroku Scheduler).
"""

import logging
import sys
import os
import time
import argparse # Added
from datetime import datetime, timezone, timedelta
import concurrent.futures # Added for parallelism
from functools import partial # Added for passing args to thread worker
from typing import Dict, Any, Optional

# Adjust path to import from src
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(SRC_DIR)

from sqlalchemy.orm import Session
from dateutil.parser import isoparse # For parsing ISO 8601 dates from API

from src.database.connection import get_db, SessionLocal # Import SessionLocal for threads
from src.database import crud_youtube as crud
from src.youtube.supadata_client import SupadataClient, SupadataAPIError
from src.database.models import YouTubeChannel # Import the model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Ensure logs go to stdout for Heroku
    ]
)
logger = logging.getLogger(__name__)

# --- Configuration ---
FETCH_LIMIT_PER_CHANNEL = 30 # How many recent videos to check per channel run (Changed from 100)
API_DELAY_SECONDS = 1 # Can potentially reduce delay with parallel calls, but monitor Supadata limits
MAX_VIDEO_WORKERS = 8 # Max concurrent video processing threads per channel
# DEFAULT_FETCH_VIDEOS_NEWER_THAN_DAYS = 30 # Only process videos uploaded in the last X days (safety net)
# Default is now set via argparse

# --- Helper Function for Single Video Processing ---
def _process_single_video(video_id: str, channel_id: str, client: SupadataClient, effective_cutoff_ts: int) -> Dict[str, Any]:
    """Fetches metadata, checks date, fetches transcript, and updates DB for ONE video.
       Designed to run in a thread. Returns a dict with status/results.
    """
    log_prefix = f"[Video {video_id}]"
    result = {"status": "skipped", "new_video_added": False, "transcript_fetched": False, "transcript_failed": False, "transcript_unavailable": False, "upload_timestamp": 0}
    db: Optional[Session] = None
    try:
        # Create a new session for this thread
        db = SessionLocal()
        
        # Check if video already exists
        existing_video = crud.get_video_by_id(db, video_id)
        if existing_video:
            logger.debug(f"{log_prefix} Already in DB.")
            if existing_video.upload_date:
                 result["upload_timestamp"] = int(existing_video.upload_date.timestamp())
            return result # Return status skipped, already exists
        
        # Fetch metadata
        logger.debug(f"{log_prefix} Fetching metadata...")
        metadata = client.get_video_metadata(video_id)
        # Add small delay *after* metadata fetch, *before* potential transcript fetch
        time.sleep(API_DELAY_SECONDS)

        if not metadata:
            logger.warning(f"{log_prefix} Could not fetch metadata.")
            result["status"] = "metadata_failed"
            return result

        # Parse upload date
        upload_date_str = metadata.get('uploadDate')
        upload_date_dt: Optional[datetime] = None
        upload_date_ts = 0
        if upload_date_str:
            try:
                upload_date_dt = isoparse(upload_date_str)
                if upload_date_dt.tzinfo is None:
                    upload_date_dt = upload_date_dt.replace(tzinfo=timezone.utc)
                upload_date_ts = int(upload_date_dt.timestamp())
                result["upload_timestamp"] = upload_date_ts
            except ValueError:
                logger.warning(f"{log_prefix} Could not parse upload date '{upload_date_str}'")
        
        # NEW date check:
        if upload_date_ts <= effective_cutoff_ts:
            logger.debug(f"{log_prefix} Uploaded {upload_date_dt} (ts: {upload_date_ts}) is not newer than effective cutoff (ts: {effective_cutoff_ts}). Skipping.")
            result["status"] = "skipped_older_than_effective_cutoff"
            return result

        logger.info(f"{log_prefix} NEW video found (Title: {metadata.get('title', 'N/A')}) Uploaded: {upload_date_dt}")
        result["status"] = "processing"
        result["new_video_added"] = True

        # Add video record to DB
        added_video = crud.add_video(
            db=db,
            video_id=video_id,
            channel_id=channel_id,
            title=metadata.get('title'),
            description=metadata.get('description'),
            upload_date=upload_date_dt
        )
        if not added_video:
            logger.error(f"{log_prefix} Failed to add video to database.")
            result["status"] = "db_add_failed"
            return result

        # Fetch transcript
        logger.debug(f"{log_prefix} Fetching transcript...")
        transcript_text = client.get_transcript(video_id, lang='en', text=True)
        # No sleep needed after transcript fetch within this function

        if transcript_text == "UNAVAILABLE":
            logger.warning(f"{log_prefix} Transcript unavailable.")
            crud.update_video_transcript_status(db, video_id, 'unavailable')
            result["transcript_unavailable"] = True
            result["status"] = "transcript_unavailable"
        elif transcript_text:
            added_transcript = crud.add_transcript(db, video_id, 'en', transcript_text)
            if added_transcript:
                logger.info(f"{log_prefix} Transcript fetched and stored.")
                result["transcript_fetched"] = True
                result["status"] = "transcript_fetched"
            else:
                logger.error(f"{log_prefix} Failed to store transcript.")
                result["transcript_failed"] = True
                result["status"] = "transcript_failed"
        else:
            logger.error(f"{log_prefix} Failed to fetch transcript (returned None).")
            crud.update_video_transcript_status(db, video_id, 'failed')
            result["transcript_failed"] = True
            result["status"] = "transcript_failed"
            
        return result

    except Exception as e:
        logger.error(f"{log_prefix} Unexpected error in worker thread: {e}", exc_info=True)
        result["status"] = "worker_exception"
        return result
    finally:
        if db:
            db.close()

# --- Original process_channel modified for parallelism ---
def process_channel(db: Session, client: SupadataClient, channel: YouTubeChannel, max_age_days: int):
    """Process a single YouTube channel: find new videos, fetch metadata & transcripts in parallel."""
    processed_video_ids_count = 0
    new_video_count = 0
    transcript_fetched_count = 0
    transcript_failed_count = 0
    transcript_unavailable_count = 0
    highest_ts_of_newly_added_video_this_run = 0 # NEW: Tracks the timestamp of the newest video *actually added* in this run

    channel_id = channel.id
    channel_handle = channel.handle

    true_latest_known_video_ts_in_db = crud.get_latest_video_upload_timestamp_for_channel(db, channel_id) or 0
    logger.info(f"Latest known video timestamp in DB for channel {channel_id}: {datetime.fromtimestamp(true_latest_known_video_ts_in_db, tz=timezone.utc).isoformat() if true_latest_known_video_ts_in_db > 0 else 'None'}")

    # For logging the previous last_checked_timestamp, we can still use channel.last_checked_timestamp
    previous_last_checked_dt = datetime.fromtimestamp(channel.last_checked_timestamp, tz=timezone.utc) if channel.last_checked_timestamp and channel.last_checked_timestamp > 0 else "Never"
    logger.info(f"Processing channel {channel_id} ({channel_handle or 'No Handle'}). Previous DB last_checked_timestamp: {previous_last_checked_dt if isinstance(previous_last_checked_dt, str) else previous_last_checked_dt.isoformat()}")

    safety_cutoff_dt = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    logger.info(f"Safety cutoff date (videos older than this will be skipped if no newer known video): {safety_cutoff_dt.isoformat()}")

    effective_cutoff_ts = max(true_latest_known_video_ts_in_db, int(safety_cutoff_dt.timestamp()))
    logger.info(f"Effective cutoff for new videos (timestamp): {effective_cutoff_ts} ({datetime.fromtimestamp(effective_cutoff_ts, tz=timezone.utc).isoformat() if effective_cutoff_ts > 0 else 'Epoch'})")

    try:
        # 1. Get recent video IDs from the channel using the handle
        if not channel_handle:
             logger.error(f"Channel {channel_id} is missing a handle. Cannot fetch videos.")
             now_ts = int(datetime.now(timezone.utc).timestamp())
             crud.update_channel_timestamp(db, channel_id, now_ts)
             return

        video_ids = client.get_channel_videos(channel_handle, limit=FETCH_LIMIT_PER_CHANNEL, type='video')

        if video_ids is None:
            logger.warning(f"Fetching video IDs failed for channel handle {channel_handle}.")
            now_ts = int(datetime.now(timezone.utc).timestamp())
            crud.update_channel_timestamp(db, channel_id, now_ts)
            return
            
        if not video_ids:
            logger.info(f"No recent videos returned by Supadata for channel handle {channel_handle}.")
            now_ts = int(datetime.now(timezone.utc).timestamp())
            crud.update_channel_timestamp(db, channel_id, now_ts)
            return

        # 2. Process video IDs in parallel
        logger.info(f"Submitting {len(video_ids)} videos for parallel processing (Max Workers: {MAX_VIDEO_WORKERS}). Using effective_cutoff_ts: {effective_cutoff_ts}")
        tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_VIDEO_WORKERS) as executor:
            future_map = {}
            for video_id in video_ids:
                future = executor.submit(
                    _process_single_video, 
                    video_id=video_id, 
                    channel_id=channel_id, 
                    client=client, 
                    effective_cutoff_ts=effective_cutoff_ts # Pass the new combined cutoff
                )
                future_map[future] = video_id

            for future in concurrent.futures.as_completed(future_map):
                vid = future_map[future]
                processed_video_ids_count += 1
                try:
                    result_data = future.result()
                    if result_data["new_video_added"]:
                        new_video_count += 1
                        # Update the highest timestamp of a video *actually added* in this run
                        highest_ts_of_newly_added_video_this_run = max(highest_ts_of_newly_added_video_this_run, result_data["upload_timestamp"])
                    if result_data["transcript_fetched"]:
                        transcript_fetched_count += 1
                    if result_data["transcript_failed"]:
                        transcript_failed_count += 1
                    if result_data["transcript_unavailable"]:
                        transcript_unavailable_count += 1

                except Exception as exc:
                    logger.error(f"Video processing task for {vid} generated exception: {exc}", exc_info=True)

        logger.info(f"Finished parallel processing for {len(video_ids)} submitted videos.")

        # NEW LOGIC for updating channel timestamp
        if highest_ts_of_newly_added_video_this_run > true_latest_known_video_ts_in_db:
            # We actually added one or more videos that are newer than what we previously knew from the DB.
            # Update the channel's timestamp to the newest one we just added.
            crud.update_channel_timestamp(db, channel_id, highest_ts_of_newly_added_video_this_run)
            logger.info(f"Updated last_checked_timestamp for channel {channel_id} to {datetime.fromtimestamp(highest_ts_of_newly_added_video_this_run, tz=timezone.utc).isoformat()} (new videos added).")
        # The cases for 'video_ids is None' (Supadata call failed) or 'not video_ids' (Supadata returned empty list) are handled earlier by updating to now_ts.
        # This 'elif' covers the case where Supadata returned videos, but none were new enough to be added.
        elif video_ids: # This implies video_ids is not None and not empty, but no new videos were *added*
            logger.info(f"Channel {channel_id}: Checked {len(video_ids)} videos from Supadata. No videos were found and added that were newer than the current DB high-water mark of {datetime.fromtimestamp(true_latest_known_video_ts_in_db, tz=timezone.utc).isoformat() if true_latest_known_video_ts_in_db > 0 else 'None'}.")
            # DO NOT update last_checked_timestamp to now() in this case.

    except SupadataAPIError as e:
        logger.error(f"Supadata API Error processing channel {channel_id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error processing channel {channel_id}: {e}", exc_info=True)
    finally:
         logger.info(f"Channel {channel_id} Summary: Processed IDs={processed_video_ids_count}, New Videos Added={new_video_count}, Transcripts Fetched={transcript_fetched_count}, Transcripts Failed={transcript_failed_count}, Transcripts Unavailable={transcript_unavailable_count}")

def run_youtube_fetcher(max_age_days: int):
    logger.info(f"--- Starting YouTube Fetcher Run (Max Age Days: {max_age_days}) ---")
    start_time = time.time()
    db_gen = get_db()
    db = next(db_gen)
    client = SupadataClient() # Reads API key from env var

    processed_channels_count = 0
    try:
        # 1. Get active game-influencer mappings
        mappings = crud.get_active_game_influencer_mappings(db)
        logger.info(f"Found {len(mappings)} active game-influencer mappings.")
        
        # Store channels processed in this run to avoid duplicates if one influencer maps to multiple active games
        channels_processed_this_run = set()

        for mapping in mappings:
            if not mapping.influencer or not mapping.influencer.channels:
                logger.warning(f"Skipping mapping for Game ID {mapping.game_id} / Influencer ID {mapping.influencer_id} due to missing influencer or channel data.")
                continue

            for channel in mapping.influencer.channels:
                if channel.id in channels_processed_this_run:
                     logger.debug(f"Channel {channel.id} already processed in this run, skipping.")
                     continue
                
                process_channel(db, client, channel, max_age_days) # Pass max_age_days
                channels_processed_this_run.add(channel.id)
                processed_channels_count += 1

    except Exception as e:
        logger.critical(f"An uncaught exception occurred during the fetcher run: {e}", exc_info=True)
    finally:
        end_time = time.time()
        logger.info(f"--- YouTube Fetcher Run Finished --- Took {end_time - start_time:.2f} seconds. Processed {processed_channels_count} unique channels.")
        # Close DB session?
        # db.close() # Might not be needed if get_db uses context manager internally
        # For now, assume session is managed by get_db caller or context

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch new YouTube videos and transcripts for tracked influencers.")
    parser.add_argument(
        "--max-age-days", 
        type=int, 
        default=7, 
        help="Safety net: only process videos uploaded within the last X days on the first run for a channel (default: 7)."
    )
    args = parser.parse_args()
    
    run_youtube_fetcher(args.max_age_days) 