#!/usr/bin/env python3
import os
import logging
import argparse
import datetime
import asyncio
import tempfile
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables (needed for DB, OpenAI, Slack Token)
# Assumes script is run from project root or .env is findable
from dotenv import load_dotenv

# Add project root to Python path to allow src imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
import sys
sys.path.insert(0, PROJECT_ROOT)

# Find and load .env file
dotenv_path = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logger.info(f"Loaded environment variables from {dotenv_path}")
else:
    logger.info(".env file not found in project root, relying on system environment variables.")
    load_dotenv() # Try default search path

# --- Import project modules ---
from src.reporting.youtube_report_generator import generate_youtube_summary_report
from src.database.connection import get_db
from src.database import crud_youtube as crud # To get game details like name/slack channel

# --- Configuration from Environment Variables --- 
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
DEFAULT_SLACK_CHANNEL_ID = os.getenv("DEFAULT_SLACK_CHANNEL_ID") # Fallback if not in DB

async def run_youtube_report_and_upload(game_id: int, period: str, channel_id_override: Optional[str] = None, custom_message: Optional[str] = None):
    """Generates YouTube feedback report and uploads to Slack."""
    if not SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN environment variable not set. Cannot upload to Slack.")
        return

    logger.info(f"Starting YouTube report generation for Game ID: {game_id}, Period: {period}")

    # --- Get Game Info (Name, Slack Channel) ---
    target_channel_id = None
    game_name = f"Game ID {game_id}" # Default name
    db_session = None
    try:
        db_gen = get_db()
        db_session = next(db_gen)
        game = crud.get_game_by_id(db_session, game_id)
        if game:
            game_name = game.name
            target_channel_id = game.slack_channel_id
            logger.info(f"Found game: {game_name}. Target Slack Channel from DB: {target_channel_id}")
        else:
            logger.error(f"Game with ID {game_id} not found in database.")
            return
    except Exception as e:
        logger.exception(f"Error fetching game details from database: {e}")
        return
    finally:
        if db_session:
            try:
                 next(db_gen) # Close session
            except StopIteration:
                 pass # Already closed
            except Exception as db_close_err:
                 logger.error(f"Error closing DB session after fetching game info: {db_close_err}")

    # --- Determine final Slack Channel ID ---
    if channel_id_override:
         final_channel_id = channel_id_override
         logger.info(f"Using provided channel override: {final_channel_id}")
    elif target_channel_id:
         final_channel_id = target_channel_id
    else:
         final_channel_id = DEFAULT_SLACK_CHANNEL_ID
         logger.warning(f"No specific channel ID found in DB or override, using default: {final_channel_id}")
    
    if not final_channel_id:
        logger.error("No target Slack channel ID determined (DB, override, or default). Cannot upload.")
        return

    # --- Calculate Date Range ---
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    end_date = now_utc
    time_period_desc = ""
    try:
        if period == 'last_day':
            start_date = (now_utc - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            time_period_desc = f"last 24 hours (approx, starting {start_date.strftime('%Y-%m-%d')})"
        elif period == 'last_week':
            start_date = (now_utc - datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            time_period_desc = f"last 7 days (starting {start_date.strftime('%Y-%m-%d')})"
        elif period == 'last_month':
            start_date = (now_utc - datetime.timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0) # Approx month
            time_period_desc = f"last 30 days (starting {start_date.strftime('%Y-%m-%d')})"
        else:
            logger.error(f"Invalid period '{period}' received.")
            return
        logger.info(f"Calculated date range: {start_date} to {end_date}")
    except Exception as e:
        logger.exception(f"Error calculating date range: {e}")
        return

    # --- Generate the report --- 
    report_bytes = None
    db_session = None # Need a fresh session for the generator
    try:
        db_gen = get_db()
        db_session = next(db_gen)
        report_bytes = await generate_youtube_summary_report(db_session, game_id, start_date, end_date)
        if not report_bytes:
            logger.error("YouTube report generation returned empty bytes.")
            # Maybe send a Slack message saying no data? For now, just return.
            return
        logger.info(f"YouTube report generation successful. Size: {len(report_bytes)} bytes.")
    except Exception as e:
        logger.exception(f"Error during YouTube report generation: {e}")
        return
    finally:
         if db_session:
            try:
                 next(db_gen) # Close session
            except StopIteration:
                 pass
            except Exception as db_close_err:
                 logger.error(f"Error closing DB session after generating report: {db_close_err}")

    # --- Save bytes to a temporary file ---
    tmp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_file:
            tmp_file_path = tmp_file.name
            tmp_file.write(report_bytes)
            logger.info(f"Report saved to temporary file: {tmp_file_path}")
    except Exception as e:
        logger.exception(f"Error saving report to temporary file: {e}")
        return # Can't upload if we can't save
    
    # --- Upload to Slack --- 
    try:
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        filename = f"youtube_feedback_{game_id}_{period}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"
        
        # Construct the initial comment
        base_comment = f"YouTube Feedback Summary Report for {game_name} ({period} - {time_period_desc})"
        if custom_message:
            initial_comment = f"{custom_message}\n\n{base_comment}"
        else:
            initial_comment = base_comment
            
        logger.info(f"Attempting Slack upload with: channel='{final_channel_id}', file='{tmp_file_path}', filename='{filename}'")
        response = await client.files_upload_v2(
            channel=final_channel_id,
            file=tmp_file_path,
            filename=filename,
            initial_comment=initial_comment, # Use constructed comment
            title=f"{game_name} YouTube Feedback {period.replace('_', ' ').capitalize()} Report"
        )
        if response.get("ok"):
            logger.info(f"Successfully uploaded report '{filename}' to Slack channel {final_channel_id}.")
        else:
            logger.error(f"Slack API error during file upload: {response.get('error')}")

    except SlackApiError as e:
        logger.error(f"Slack API Error: {e.response['error']}")
    except Exception as e:
        logger.exception(f"Unexpected error during Slack upload: {e}")
    finally:
        # --- Clean up the temporary file ---
        if tmp_file_path and os.path.exists(tmp_file_path):
            try:
                os.remove(tmp_file_path)
                logger.info(f"Removed temporary file: {tmp_file_path}")
            except Exception as e:
                logger.error(f"Error removing temporary file {tmp_file_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Generate YouTube feedback report and upload to Slack.")
    parser.add_argument("--game-id", type=int, required=True, help="Database Game ID for the report.")
    parser.add_argument("--period", type=str, required=True, choices=['last_day', 'last_week', 'last_month'], help="Time period for the report.")
    parser.add_argument("--channel-id", type=str, default=None, help="Slack Channel ID to upload the report to (overrides channel ID set in DB for the game, and DEFAULT_SLACK_CHANNEL_ID env var).")
    parser.add_argument("--message", type=str, default=None, help="Optional custom message to include with the Slack post.")

    args = parser.parse_args()

    # Run the async function
    asyncio.run(run_youtube_report_and_upload(args.game_id, args.period, args.channel_id, args.message))

if __name__ == "__main__":
    main() 