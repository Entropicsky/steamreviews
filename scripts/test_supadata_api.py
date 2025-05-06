#!/usr/bin/env python
# scripts/test_supadata_api.py
import os
import sys
import logging
import requests
from dotenv import load_dotenv
import json

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Configure logging
# Use DEBUG level to capture detailed request/response info
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
# TARGET_CHANNEL_ID = "UCk0q5N3Wz9yG4rSg1Vv6MVA" # Weak3n's Channel ID (UC format - caused error)
TARGET_CHANNEL_ID = "@Weak3n" # Weak3n's Handle (Based on docs example format)
LIMIT = 50
VIDEO_TYPE = "video"
SUPADATA_BASE_URL = "https://api.supadata.ai/v1"
ENDPOINT = f"/youtube/channel/videos"
TARGET_URL = f"{SUPADATA_BASE_URL}{ENDPOINT}"
# --- End Configuration ---

def test_supadata_channel_videos():
    logger.info("--- Starting Supadata API Direct Test ---")
    load_dotenv()
    api_key = os.getenv("SUPADATA_API_KEY")

    if not api_key:
        logger.error("CRITICAL: SUPADATA_API_KEY not found in environment variables (.env file or exported).")
        return

    headers = {
        "x-api-key": api_key,
        "Accept": "application/json" # Explicitly request JSON
    }
    params = {
        "id": TARGET_CHANNEL_ID,
        "limit": LIMIT,
        "type": VIDEO_TYPE
    }

    logger.debug(f"Target URL: {TARGET_URL}")
    logger.debug(f"Request Headers: {{'x-api-key': '******', 'Accept': 'application/json'}}") # Mask key in logs
    logger.debug(f"Request Params: {params}")

    try:
        response = requests.get(TARGET_URL, headers=headers, params=params, timeout=30) # Added timeout

        logger.info(f"Request URL Sent: {response.request.url}") # Log the final URL with params
        logger.info(f"Response Status Code: {response.status_code}")
        logger.debug(f"Response Headers: {response.headers}")

        # Check if the response content type is JSON before trying to parse
        content_type = response.headers.get('Content-Type', '')
        logger.debug(f"Response Content-Type: {content_type}")

        if response.status_code == 200:
            if 'application/json' in content_type:
                try:
                    response_data = response.json()
                    logger.info("Successfully received and parsed JSON response.")
                    logger.debug(f"Response JSON Data:\n{json.dumps(response_data, indent=2)}")
                    # Log specific details if needed
                    if isinstance(response_data, list):
                         logger.info(f"Number of videos returned: {len(response_data)}")
                    elif isinstance(response_data, dict) and 'items' in response_data:
                         logger.info(f"Number of videos returned (in items): {len(response_data['items'])}")
                except json.JSONDecodeError:
                    logger.error("Status code was 200, but failed to decode JSON response body.")
                    logger.debug(f"Raw Response Body (first 500 chars):\n{response.text[:500]}")
            else:
                logger.warning(f"Status code was 200, but Content-Type was '{content_type}', not JSON.")
                logger.debug(f"Raw Response Body (first 500 chars):\n{response.text[:500]}")
        else:
            logger.error(f"API returned non-200 status code: {response.status_code}")
            # Log response body for non-200 codes as it might contain error details
            logger.error(f"Raw Response Body (first 500 chars):\n{response.text[:500]}")

    except requests.exceptions.RequestException as e:
        logger.error(f"An error occurred during the API request: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)

    logger.info("--- Supadata API Direct Test Finished ---")

if __name__ == "__main__":
    test_supadata_channel_videos() 