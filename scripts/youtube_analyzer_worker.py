#!/usr/bin/env python3
"""
YouTube Feedback Analyzer Worker Script

Queries the database for videos with fetched transcripts that need analysis,
runs the YouTubeFeedbackAnalyzer on them, and stores the structured results.

Designed to be run as a scheduled job, ideally after the fetcher script.
"""

import logging
import sys
import os
import time

# Adjust path to import from src
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(SRC_DIR)

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database import crud_youtube as crud
from src.youtube.analyzer import YouTubeFeedbackAnalyzer # Assuming analyzer is in this path

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
BATCH_SIZE = 20 # Number of videos to process per worker run

def run_youtube_analyzer():
    logger.info("--- Starting YouTube Analyzer Run ---")
    start_time = time.time()
    db_gen = get_db()
    db = next(db_gen)
    analyzer = YouTubeFeedbackAnalyzer() # Initialize analyzer (uses placeholder API call for now)

    processed_count = 0
    failed_count = 0
    irrelevant_count = 0
    relevant_count = 0

    try:
        # 1. Get videos needing analysis
        videos_to_analyze = crud.get_videos_for_analysis(db, limit=BATCH_SIZE)
        logger.info(f"Found {len(videos_to_analyze)} videos needing analysis.")

        if not videos_to_analyze:
            logger.info("No videos pending analysis found.")
            return

        for video in videos_to_analyze:
            processed_count += 1
            logger.info(f"Analyzing video: {video.id} (Title: {video.title})")

            # 2. Get the transcript text
            # Assuming English transcript was fetched by the fetcher
            transcript_record = crud.get_transcript(db, video.id, language='en')
            if not transcript_record or not transcript_record.transcript_text:
                logger.error(f"Transcript text not found for video {video.id}, marking analysis as failed.")
                crud.update_video_analysis_status(db, video.id, 'failed')
                failed_count += 1
                continue

            # 3. Get the associated game name for context
            # Need to traverse relationships: video -> channel -> influencer -> mapping -> game
            # This could be optimized with a direct query or by adding game_id to Video?
            # For now, using relationships:
            game_name = None
            if video.channel and video.channel.influencer and video.channel.influencer.game_mappings:
                # Find the *first* active mapping for this influencer to get *a* game name
                # In theory, an influencer could map to multiple games.
                # The relevance check needs a specific game context.
                # TODO: Decide how to handle multiple game mappings if an influencer covers several games.
                # Option 1: Pass all game names and let LLM figure it out? (Complex prompt)
                # Option 2: Analyze once per game mapping? (Might run LLM multiple times on same transcript)
                # Option 3: Assume fetcher only fetches for *relevant* channels/games? (Needs fetcher logic change)
                # FOR NOW: Use the game name from the first active mapping found.
                first_active_mapping = next((m for m in video.channel.influencer.game_mappings if m.is_active and m.game and m.game.is_active), None)
                if first_active_mapping:
                    game_name = first_active_mapping.game.name
            
            if not game_name:
                 logger.error(f"Could not determine relevant game name for video {video.id} via mappings, marking analysis as failed.")
                 crud.update_video_analysis_status(db, video.id, 'failed')
                 failed_count += 1
                 continue

            # 4. Call the analyzer
            try:
                analysis_result_dict = analyzer.analyze_video_transcript(
                    transcript_text=transcript_record.transcript_text,
                    game_name=game_name
                )
            except Exception as e:
                 logger.error(f"Exception during analysis call for video {video.id}: {e}", exc_info=True)
                 analysis_result_dict = None # Treat exceptions as failure

            # 5. Process results
            if analysis_result_dict:
                # Store results in VideoFeedbackAnalysis table
                added_analysis = crud.add_or_update_analysis(db, video.id, analysis_result_dict)
                if added_analysis:
                    logger.info(f"Successfully stored analysis for video {video.id}. Relevant: {analysis_result_dict.get('is_relevant')}")
                    if analysis_result_dict.get('is_relevant', False):
                         relevant_count += 1
                    else:
                         irrelevant_count += 1
                else:
                    logger.error(f"Failed to store analysis results for video {video.id} in DB.")
                    # Status already set to 'failed' within add_or_update_analysis on error
                    failed_count += 1
            else:
                # Analysis failed (e.g., LLM error, parsing error)
                logger.error(f"Analysis failed for video {video.id}. Marking status as failed.")
                crud.update_video_analysis_status(db, video.id, 'failed')
                failed_count += 1
            
            # Optional delay between analyses?
            time.sleep(1) # Small delay

    except Exception as e:
        logger.critical(f"An uncaught exception occurred during the analyzer run: {e}", exc_info=True)
    finally:
        end_time = time.time()
        logger.info(f"--- YouTube Analyzer Run Finished --- Took {end_time - start_time:.2f} seconds.")
        logger.info(f"Summary: Processed={processed_count}, Relevant={relevant_count}, Irrelevant={irrelevant_count}, Failed={failed_count}")
        # db.close() # Manage session as needed

if __name__ == "__main__":
    run_youtube_analyzer() 