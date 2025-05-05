#!/usr/bin/env python3
import os
import logging
import argparse
import datetime
import asyncio
import tempfile
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

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

async def run_report_and_upload(app_id: int, timespan: str, channel_id: str):
    """Generates report, uploads to Slack, and cleans up."""
    if not SLACK_BOT_TOKEN:
        logger.error("SLACK_BOT_TOKEN environment variable not set. Cannot upload to Slack.")
        return
    if not channel_id:
        logger.error("Slack channel ID not provided or set in environment (DEFAULT_SLACK_CHANNEL_ID).")
        return

    logger.info(f"Starting scheduled report generation for App ID: {app_id}, Timespan: {timespan}")

    # 1. Calculate start_timestamp
    now_utc = datetime.datetime.now(datetime.timezone.utc)
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
            # This should ideally be caught by argparse choices, but double-check
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
            # Optionally send an error message to Slack?
            return
        logger.info(f"Report generation successful. Size: {len(report_bytes)} bytes.")
    except Exception as e:
        logger.exception(f"Error during report generation: {e}")
        # Optionally send an error message to Slack?
        return

    # 3. Save bytes to a temporary file
    # Using tempfile ensures it gets cleaned up even if Slack upload fails
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_file:
        tmp_file_path = tmp_file.name
        tmp_file.write(report_bytes)
        logger.info(f"Report saved to temporary file: {tmp_file_path}")
    
    # 4. Upload to Slack
    try:
        client = AsyncWebClient(token=SLACK_BOT_TOKEN)
        filename = f"steam_reviews_{app_id}_{timespan}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"
        response = await client.files_upload_v2(
            channel=channel_id,
            filepath=tmp_file_path,
            filename=filename,
            initial_comment=f"Steam Reviews Summary Report for App ID {app_id} ({timespan} - {time_period_desc})",
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

    args = parser.parse_args()

    # Run the async function
    asyncio.run(run_report_and_upload(args.app_id, args.timespan, args.channel_id))

if __name__ == "__main__":
    main() 