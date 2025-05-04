import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
import requests
from .models import Review, Author # Import from models.py

logger = logging.getLogger(__name__)

# Assume CACHE_DIR might be needed here or passed in
CACHE_DIR = os.getenv("CACHE_DIR", "data")
os.makedirs(CACHE_DIR, exist_ok=True)

class SteamAPI:
    """Steam API client for fetching reviews."""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }

    def fetch_chinese_reviews(self, appid: str, max_reviews: int = 200) -> List[Review]:
        """Fetch both Simplified and Traditional Chinese reviews."""
        # (Code remains the same as in prototype.py)
        per_language_max = max_reviews // 2
        simplified_reviews = self.fetch_reviews(appid, language="schinese", max_reviews=per_language_max)
        logger.info(f"Fetched {len(simplified_reviews)} Simplified Chinese reviews")
        traditional_reviews = self.fetch_reviews(appid, language="tchinese", max_reviews=per_language_max)
        logger.info(f"Fetched {len(traditional_reviews)} Traditional Chinese reviews")
        all_reviews = simplified_reviews + traditional_reviews
        logger.info(f"Combined total: {len(all_reviews)} Chinese reviews")
        return all_reviews
    def fetch_reviews(self, appid: str, language: str = "all", max_reviews: int = 100, after_timestamp: Optional[int] = None) -> tuple[List[Review], int, Optional[str]]:
        """Fetch reviews from Steam API, optionally only those newer than a timestamp.
           Returns list of reviews, highest timestamp seen, and next cursor.
        """
        # ... (Cache check logic REMOVED as it doesn't work well with 'all' and incremental) ...

        # Fetch from API
        base_url = f"https://store.steampowered.com/appreviews/{appid}"
        reviews = []
        cursor = "*"
        total_pages = 0
        latest_timestamp_in_batch = 0 # Renamed for clarity
        next_cursor = None # Initialize next_cursor
        logger.info(f"Starting fetch for appid {appid}, lang '{language}'" + (f", after {after_timestamp}" if after_timestamp else ""))

        while True:
            batch_size = 100 # Always fetch 100 per page for incremental
            # Remove max_reviews check here, handled by caller or timestamp

            try:
                params = {
                    'json': 1,
                    'cursor': cursor,
                    'num_per_page': batch_size,
                    'review_type': 'all',
                    'language': language, # Pass the requested language ('all' or specific)
                    'purchase_type': 'all',
                    'filter': 'recent',
                }
                logger.info(f"Fetching page {total_pages + 1} of {language} reviews with cursor: {cursor}")
                response = requests.get(base_url, params=params, headers=self.headers, timeout=15) # Increased timeout slightly
                if response.status_code != 200:
                    logger.error(f"Steam API error: {response.status_code} - {response.text}")
                    break
                try:
                    data = response.json()
                    logger.info(f"Response received: success={data.get('success')}, num_reviews={len(data.get('reviews', []))}")
                    next_cursor = data.get('cursor') # Store the cursor for the next potential page
                except Exception as e:
                    logger.error(f"Error decoding JSON response: {e}")
                    logger.error(f"Raw response content: {response.text[:1000]}")
                    break
                if not data.get('success', 0) == 1:
                    logger.error(f"Steam API returned error: {data}")
                    break
                if 'reviews' not in data:
                    logger.error("No reviews field in response")
                    break
                batch = data['reviews']
                if not batch:
                    logger.info(f"No more {language} reviews to fetch (empty batch).")
                    break

                new_reviews_in_batch = []
                stop_fetching = False
                current_batch_latest_ts = 0
                for review_data in batch:
                    review_language = review_data.get('language', 'unknown') # Get actual language from review
                    review_timestamp = review_data.get('timestamp_created', 0)
                    current_batch_latest_ts = max(current_batch_latest_ts, review_timestamp)

                    # Check timestamp cutoff
                    if after_timestamp and review_timestamp <= after_timestamp:
                        logger.info(f"Reached timestamp cutoff ({review_timestamp} <= {after_timestamp}). Stopping fetch.")
                        stop_fetching = True
                        break # Stop processing this batch

                    # Pass the actual review_language to _process_review
                    processed_review = self._process_review(review_data, appid, review_language)
                    new_reviews_in_batch.append(processed_review)

                # Update overall list and latest timestamp
                reviews.extend(new_reviews_in_batch)
                latest_timestamp_in_batch = max(latest_timestamp_in_batch, current_batch_latest_ts)
                logger.info(f"Processed {len(new_reviews_in_batch)} new reviews from batch, total fetched this run: {len(reviews)}")

                # Check if we should stop after processing the batch
                if stop_fetching:
                    break

                # If Steam didn't provide a next cursor, stop pagination
                if not next_cursor:
                    logger.info("No next cursor provided by Steam API. Ending pagination.")
                    break
                
                cursor = next_cursor # Use the new cursor for the next iteration
                total_pages += 1
                time.sleep(1.5) # Slightly longer sleep

            except Exception as e:
                logger.error(f"Error during review fetching loop: {str(e)}")
                break

        logger.info(f"Fetch complete: Processed {total_pages} pages, fetched {len(reviews)} new {language} reviews.")
        logger.info(f"Highest timestamp encountered in fetched reviews: {latest_timestamp_in_batch}")

        # --- Cache saving is removed - Caching full results doesn't make sense for incremental fetches --- 
        # The caller (main_fetcher) will handle storing results in DB.

        # Return list, latest timestamp, and the cursor for the *next* page
        return reviews, latest_timestamp_in_batch, next_cursor
        
    def _process_review(self, review_data: Dict, appid: str, language: str) -> Review:
        """Process a single review JSON dict into a Review object."""
        try:
            author_data = review_data.get('author', {})
            author = Author(
                steamid=author_data.get('steamid', 'unknown'),
                num_games_owned=author_data.get('num_games_owned', 0),
                num_reviews=author_data.get('num_reviews', 0),
                playtime_forever=author_data.get('playtime_forever', 0),
                playtime_last_two_weeks=author_data.get('playtime_last_two_weeks', 0),
                playtime_at_review=author_data.get('playtime_at_review', 0),
                last_played=author_data.get('last_played', 0)
            )

            # Convert score to float, handle potential None or non-numeric values
            try:
                weighted_score = float(review_data.get('weighted_vote_score', 0.0))
            except (ValueError, TypeError):
                weighted_score = 0.0

            return Review(
                recommendationid=review_data.get('recommendationid', 'unknown'),
                appid=appid,
                author=author,
                language=language,
                review_text=review_data.get('review', ''),
                timestamp_created=review_data.get('timestamp_created', 0),
                timestamp_updated=review_data.get('timestamp_updated', 0),
                voted_up=review_data.get('voted_up', False),
                votes_up=review_data.get('votes_up', 0),
                votes_funny=review_data.get('votes_funny', 0),
                weighted_vote_score=weighted_score,
                comment_count=review_data.get('comment_count', 0),
                steam_purchase=review_data.get('steam_purchase', False),
                received_for_free=review_data.get('received_for_free', False),
                written_during_early_access=review_data.get('written_during_early_access', False),
                developer_response=review_data.get('developer_response'), # Can be None
                timestamp_dev_responded=review_data.get('timestamp_dev_responded') # Can be None
            )

        except Exception as e:
            logger.error(f"Error processing review {review_data.get('recommendationid')}: {e}")
            # Return a minimal valid review with default author
            return Review(
                recommendationid=review_data.get('recommendationid', 'error'),
                appid=appid,
                author=Author(steamid='unknown'), # Default author
                language=language,
                review_text='Error processing review',
                timestamp_created=0,
                timestamp_updated=0,
                voted_up=False
                # Other fields default to 0/False/None via dataclass definition
            )