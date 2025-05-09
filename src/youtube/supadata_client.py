import os
import requests
import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import time # Added for retry delay

logger = logging.getLogger(__name__)

# Default Supadata API base URL
SUPADATA_API_BASE_URL = "https://api.supadata.ai/v1/youtube"

class SupadataAPIError(Exception):
    """Custom exception for Supadata API errors."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Supadata API Error {status_code}: {message}")

class SupadataClient:
    """Client for interacting with the Supadata YouTube API."""

    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY_SECONDS = 5
    REQUEST_TIMEOUT_SECONDS = 30 # Existing timeout

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SUPADATA_API_KEY")
        if not self.api_key:
            # Log warning but allow initialization; methods will fail if key still missing
            logger.warning("Supadata API key not provided via argument or SUPADATA_API_KEY env var.")
            # raise ValueError("Supadata API key is required.")
        self.base_url = SUPADATA_API_BASE_URL

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Optional[Dict | List]:
        """Internal helper for making authenticated API requests with retries."""
        if not self.api_key:
            logger.error("Cannot make Supadata API request: API key is missing.")
            return None

        url = f"{self.base_url}{endpoint}"
        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json"
        }

        last_exception = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.debug(f"Making Supadata API request (Attempt {attempt + 1}/{self.MAX_RETRIES + 1}): {method} {url} | Params: {params} | Body: {data}")
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=data,
                    timeout=self.REQUEST_TIMEOUT_SECONDS
                )
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                if response.status_code == 204:
                     logger.debug(f"Received 204 No Content response from {url}")
                     return None
                if not response.content:
                     logger.debug(f"Received empty response body from {url} with status {response.status_code}")
                     return None

                return response.json()

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                try:
                    error_details = e.response.json()
                    logger.error(f"Supadata API HTTP Error {status_code} for {url} (Attempt {attempt + 1}): {error_details}", exc_info=False)
                except json.JSONDecodeError:
                    logger.error(f"Supadata API HTTP Error {status_code} for {url} (Attempt {attempt + 1}). Response not JSON: {e.response.text[:200]}", exc_info=False)
                # For HTTP errors (4xx, 5xx), decide if retry is appropriate.
                # Generally, client errors (4xx) shouldn't be retried unless it's a rate limit (429).
                # Server errors (5xx) are good candidates for retries.
                if 500 <= status_code < 600:
                    last_exception = e
                    if attempt < self.MAX_RETRIES:
                        delay = self.INITIAL_RETRY_DELAY_SECONDS * (2 ** attempt)
                        logger.warning(f"Retrying in {delay}s due to HTTP {status_code}...")
                        time.sleep(delay)
                        continue # Go to next attempt
                    else:
                        logger.error(f"Max retries reached for HTTP {status_code} error.")
                        return None # Or raise last_exception
                else: # Non-retryable HTTP error (e.g., 400, 401, 403, 404)
                    return None # Indicate failure immediately

            except requests.exceptions.RequestException as e: # Catches ConnectTimeout, ReadTimeout, ConnectionError etc.
                last_exception = e
                logger.warning(f"RequestException connecting to Supadata API at {url} (Attempt {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES:
                    delay = self.INITIAL_RETRY_DELAY_SECONDS * (2 ** attempt)
                    logger.warning(f"Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"Max retries reached for RequestException.")
                    return None # Or raise last_exception

            except json.JSONDecodeError as e:
                 # This error occurs after a successful request but with invalid JSON response.
                 # Usually not a candidate for retry unless the API is known to sometimes return malformed JSON temporarily.
                 logger.error(f"Failed to decode JSON response from {url} (Attempt {attempt + 1}): {e}", exc_info=True)
                 # If response object exists and has text, log it
                 try:
                     if 'response' in locals() and response.text:
                         logger.debug(f"Raw response causing JSON error: {response.text[:500]}")
                 except Exception:
                     pass # Avoid error in logging
                 return None # Don't retry JSON decode errors by default

            except Exception as e:
                 # Catch-all for other unexpected errors
                 logger.error(f"An unexpected error occurred during Supadata API request to {url} (Attempt {attempt + 1}): {e}", exc_info=True)
                 last_exception = e # Store it in case we need to raise it after retries
                 # Decide if these are retryable - for now, let's not retry generic Exceptions
                 return None # Or raise e if it should halt immediately

        # If loop finishes without returning (e.g. max retries for retryable exceptions)
        logger.error(f"All retry attempts failed for {method} {url}. Last error: {last_exception}")
        return None # Or raise last_exception if preferred

    def get_channel_videos(self, channel_handle: str, limit: int = 50, type: str = "video") -> Optional[List[str]]:
        """Fetches recent video IDs for a channel using its handle (e.g., @handle)."""
        endpoint = "/channel/videos"
        params = {
            "id": channel_handle, # Use handle as the ID parameter
            "limit": limit,
            "type": type
        }
        logger.info(f"Fetching channel videos for {channel_handle} with limit={limit}, type={type}")
        response_data = self._request("GET", endpoint, params=params)

        if response_data and isinstance(response_data, dict) and "videoIds" in response_data and isinstance(response_data["videoIds"], list):
            video_ids = response_data["videoIds"]
            logger.info(f"Successfully fetched {len(video_ids)} video IDs for channel handle {channel_handle}.")
            return video_ids
        else:
            logger.warning(f"Could not fetch video IDs or unexpected format for channel handle {channel_handle}. Response: {response_data}")
            return None

    def get_channel_details_by_handle(self, channel_handle: str) -> Optional[Dict[str, Any]]:
        """Fetches channel details using the channel handle (@handle).
           Assumes the API endpoint is /channel and accepts the handle via 'id' param.
           Hoping this returns the canonical UC... channel ID.
        """
        endpoint = "/channel" # Endpoint based on docs example
        params = {"id": channel_handle}
        logger.info(f"Fetching channel details for handle: {channel_handle}")
        response_data = self._request("GET", endpoint, params=params)
        
        if response_data and isinstance(response_data, dict):
            # Check if the expected 'id' field (the UC... one) is present
            if 'id' in response_data:
                logger.info(f"Successfully fetched channel details for handle {channel_handle}. Found ID: {response_data['id']}")
                return response_data
            else:
                 logger.warning(f"Fetched channel details for handle {channel_handle}, but response is missing 'id' key. Response: {response_data}")
                 return None # Return None if the critical UC... ID is missing
        else:
            logger.warning(f"Could not fetch channel details or unexpected format for handle {channel_handle}. Response: {response_data}")
            return None

    def get_video_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Fetches metadata for a specific video ID."""
        endpoint = "/video"
        params = {"id": video_id}
        logger.debug(f"Fetching metadata for video ID: {video_id}")
        response_data = self._request("GET", endpoint, params=params)
        # Add validation if needed
        if response_data and isinstance(response_data, dict):
             logger.debug(f"Successfully fetched metadata for video {video_id}.")
             return response_data
        else:
             logger.warning(f"Could not fetch metadata for video {video_id}. Response: {response_data}")
             return None

    def get_transcript(self, video_id: str, lang: str = "en", text: bool = True) -> Optional[str]:
        """Fetches the transcript for a video ID.
        Ref: https://supadata.ai/documentation/youtube/get-transcript
        """
        endpoint = "/transcript"
        params = {
            "videoId": video_id, # Correct parameter name
            "lang": lang,
            "text": str(text).lower() # API expects string 'true'/'false' based on curl example, ensure lowercase bool string
        }
        logger.debug(f"Fetching {lang} transcript ({'text' if text else 'structured'}) for video ID: {video_id}")
        response_data = self._request("GET", endpoint, params=params)

        # Transcript text is in the 'content' key according to docs
        if response_data and isinstance(response_data, dict):
            transcript_content = response_data.get("content") # Correct response key
            if transcript_content and isinstance(transcript_content, str):
                logger.debug(f"Successfully fetched transcript for video {video_id}.")
                return transcript_content
            elif transcript_content is None and response_data.get("availableLangs") is not None:
                 # Handle case where transcript might be unavailable in requested lang but available in others
                 logger.warning(f"Transcript for video {video_id} not found in requested language '{lang}'. Available: {response_data.get('availableLangs')}")
                 # We specifically want English for now, so treat as unavailable if not found in 'en'
                 # If we wanted fallbacks, logic would go here.
                 if lang == 'en': # If we asked for english and didn't get it
                      return "UNAVAILABLE"
                 else:
                      return None # Failed for other languages requested
            else:
                logger.warning(f"'content' key not found or not a string in transcript response for video {video_id}. Response keys: {response_data.keys()}")
                return None
        else:
            logger.warning(f"Could not fetch transcript or unexpected format for video {video_id}. Response: {response_data}")
            # Check for specific unavailability errors based on status code or error message if API provides them
            # For now, assume None means failure unless specific checks added in _request indicate 404 etc.
            # Let's refine the check for UNAVAILABLE - the fetcher expects this string marker
            # It's hard to know from just None if it was 404 or other error. For now, keep it None.
            # The fetcher needs updating to handle None better if it's not an explicit UNAVAILABLE.
            return None

# Example usage (for direct testing if needed)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    load_dotenv()

    if not os.getenv("SUPADATA_API_KEY"):
        print("\nERROR: SUPADATA_API_KEY environment variable not set.")
    else:
        client = SupadataClient()

        # --- Test Get Channel Videos (using handle) ---
        test_channel_handle = "@MrBeast" # Example handle
        print(f"\n--- Testing get_channel_videos for handle: {test_channel_handle} ---")
        video_ids = client.get_channel_videos(channel_handle=test_channel_handle, limit=5)
        if video_ids:
            print(f"Found Video IDs: {video_ids}")
            test_video_id = video_ids[0]

            # --- Test Get Video Metadata ---
            print(f"\n--- Testing get_video_metadata for ID: {test_video_id} ---")
            metadata = client.get_video_metadata(test_video_id)
            if metadata:
                print(f"Found Metadata (Title): {metadata.get('title', 'N/A')}")
                print(f"Found Metadata (Upload Date): {metadata.get('uploadDate', 'N/A')}") # Key names may vary
            else:
                print("Failed to get metadata.")

            # --- Test Get Transcript ---
            print(f"\n--- Testing get_transcript for ID: {test_video_id} ---")
            transcript = client.get_transcript(test_video_id)
            if transcript:
                print(f"Found Transcript (first 100 chars): {transcript[:100]}...")
            else:
                print("Failed to get transcript (or transcript not available).")
        else:
            print("Failed to get video IDs.") 