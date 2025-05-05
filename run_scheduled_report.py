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
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logger.info(f"Loaded environment variables from {dotenv_path}")
else:
    logger.info(".env file not found in script directory, relying on system environment variables.")

# --- Import project modules --- 
# Assuming this script is run from the project root
from src.reporting.excel_generator import generate_summary_report

# --- Configuration from Environment Variables --- 
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
DEFAULT_SLACK_CHANNEL_ID = os.getenv("DEFAULT_SLACK_CHANNEL_ID") # e.g., C1234567890

async def run_report_and_upload(app_id: int, timespan: str, channel_id: str, custom_message: Optional[str] = None):
    """Generates report, uploads to Slack, and cleans up, checking schedule first."""
    if not SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN environment variable not set. Cannot upload to Slack.")
        return
    if not channel_id:
        logger.error("Slack channel ID not provided or set in environment (DEFAULT_SLACK_CHANNEL_ID).")
        return

    # --- Check if today is the correct day to run based on timespan --- 
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_utc_date = now_utc.date()

    if timespan == 'weekly':
        # 0 = Monday, 1 = Tuesday, ..., 6 = Sunday
        if today_utc_date.weekday() != 0: # Check if it's NOT Monday
            logger.info(f"Today ({today_utc_date.strftime('%A')}) is not Monday. Skipping weekly report run.")
            return
        logger.info("Today is Monday, proceeding with weekly report run.")
    elif timespan == 'monthly':
        if today_utc_date.day != 1: # Check if it's NOT the 1st of the month
            logger.info(f"Today ({today_utc_date.day}) is not the 1st of the month. Skipping monthly report run.")
            return
        logger.info("Today is the 1st of the month, proceeding with monthly report run.")
    # --- End schedule check --- 
    
    logger.info(f"Starting scheduled report generation for App ID: {app_id}, Timespan: {timespan}")

    # 1. Calculate start_timestamp
    try:
        if timespan == 'weekly':
            start_of_this_week = now_utc - datetime.timedelta(days=now_utc.weekday())
            start_of_last_week = start_of_this_week - datetime.timedelta(weeks=1)
            start_datetime_utc = start_of_last_week.replace(hour=0, minute=0, second=0, microsecond=0)
            start_timestamp = int(start_datetime_utc.timestamp())
            time_period_desc = f"last week ({start_datetime_utc.strftime('%Y-%m-%d')} to {(start_of_this_week - datetime.timedelta(days=1)).strftime('%Y-%m-%d')})"
        elif timespan == 'monthly':
            first_day_this_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_day_last_month = first_day_this_month - datetime.timedelta(days=1)
            start_datetime_utc = last_day_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_timestamp = int(start_datetime_utc.timestamp())
            time_period_desc = f"last month ({start_datetime_utc.strftime('%Y-%m')})"
        else:
            logger.error(f"Invalid timespan '{timespan}' received.")
            return
        logger.info(f"Calculated start timestamp: {start_timestamp} ({start_datetime_utc}) for period: {time_period_desc}")
    except Exception as e:
        logger.exception(f"Error calculating start timestamp: {e}")
        return

    # 2. Generate the report
    report_bytes = None
    try:
        report_bytes = await generate_summary_report(app_id, start_timestamp)
        if not report_bytes:
            logger.error("Report generation returned empty bytes.")
            return
        logger.info(f"Report generation successful. Size: {len(report_bytes)} bytes.")
    except Exception as e:
        logger.exception(f"Error during report generation: {e}")
        return

    # 3. Save bytes to a temporary file
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_file:
        tmp_file_path = tmp_file.name
        tmp_file.write(report_bytes)
        logger.info(f"Report saved to temporary file: {tmp_file_path}")
    
    # 4. Upload to Slack
    try:
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        filename = f"steam_reviews_{app_id}_{timespan}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"
        
        # Construct the initial comment
        base_comment = f"Steam Reviews Summary Report for App ID {app_id} ({timespan} - {time_period_desc})"
        if custom_message:
            initial_comment = f"{custom_message}\n\n{base_comment}"
        else:
            initial_comment = base_comment
            
        logger.info(f"Attempting Slack upload with: channel='{channel_id}', file='{tmp_file_path}', filename='{filename}'")
        response = await client.files_upload_v2(
            channel=channel_id,
            file=tmp_file_path,
            filename=filename,
            initial_comment=initial_comment, # Use constructed comment
            title=f"Steam Reviews {timespan.capitalize()} Report"
        )
        if response.get("ok"):
            logger.info(f"Successfully uploaded report '{filename}' to Slack channel {channel_id}.")
        else:
            logger.error(f"Slack API error during file upload: {response.get('error')}")

    except SlackApiError as e:
        logger.error(f"Slack API Error: {e.response['error']}")
    except Exception as e:
        logger.exception(f"Unexpected error during Slack upload: {e}")
    finally:
        # 5. Clean up the temporary file
        if os.path.exists(tmp_file_path):
            try:
                os.remove(tmp_file_path)
                logger.info(f"Removed temporary file: {tmp_file_path}")
            except Exception as e:
                logger.error(f"Error removing temporary file {tmp_file_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Generate Steam review report and upload to Slack.")
    parser.add_argument("--app-id", type=int, required=True, help="Steam App ID for the report.")
    parser.add_argument("--timespan", type=str, required=True, choices=['weekly', 'monthly'], help="Time period for the report ('weekly' or 'monthly').")
    parser.add_argument("--channel-id", type=str, default=DEFAULT_SLACK_CHANNEL_ID, help="Slack Channel ID to upload the report to (overrides DEFAULT_SLACK_CHANNEL_ID env var).")
    parser.add_argument("--message", type=str, default=None, help="Optional custom message to include with the Slack post.")

    args = parser.parse_args()

    # Run the async function, passing the new message argument
    asyncio.run(run_report_and_upload(args.app_id, args.timespan, args.channel_id, args.message))

if __name__ == "__main__":
    main() 