import logging
import datetime # Import datetime module
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func as sql_func # Alias func to avoid conflict

from . import models
from .connection import get_db # Use get_db for session management

logger = logging.getLogger(__name__)

def get_active_tracked_apps(db: Session) -> List[models.TrackedApp]:
    """Fetches all active tracked app objects from the database."""
    try:
        # Return the full TrackedApp object
        return db.query(models.TrackedApp)\
                 .filter(models.TrackedApp.is_active == True)\
                 .order_by(models.TrackedApp.name)\
                 .all()
    except Exception as e:
        logger.error(f"Error fetching active tracked apps: {e}")
        return []

def get_all_tracked_apps(db: Session) -> List[models.TrackedApp]:
    """Fetches all tracked apps (active and inactive) from the database."""
    try:
        return db.query(models.TrackedApp).order_by(models.TrackedApp.name).all()
    except Exception as e:
        logger.error(f"Error fetching all tracked apps: {e}")
        return []

def update_app_active_status(db: Session, app_id: int, is_active: bool):
    """Updates the is_active status for a specific app."""
    try:
        db.query(models.TrackedApp).filter(models.TrackedApp.app_id == app_id).update({'is_active': is_active})
        db.commit()
        logger.info(f"Updated app {app_id} active status to {is_active}")
    except Exception as e:
        logger.error(f"Error updating active status for app {app_id}: {e}")
        db.rollback()

def add_tracked_app(db: Session, app_id: int, name: Optional[str] = None):
    """Adds a new app to track, ignoring if it already exists."""
    try:
        stmt = insert(models.TrackedApp).values(
            app_id=app_id,
            name=name,
            last_fetched_timestamp=0, # Start fresh
            is_active=True
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=['app_id'])
        db.execute(stmt)
        db.commit()
        logger.info(f"Attempted to add tracked app: {app_id} - {name}")
        # Check if it was actually inserted (or ignored)
        # Optional: query back to confirm or just log attempt
    except Exception as e:
        logger.error(f"Error adding tracked app {app_id}: {e}")
        db.rollback()

def update_last_fetch_time(db: Session, app_id: int, timestamp: int):
    """Updates the last_fetched_timestamp for a specific app."""
    try:
        db.query(models.TrackedApp).filter(models.TrackedApp.app_id == app_id).update({'last_fetched_timestamp': timestamp})
        db.commit()
        logger.info(f"Updated last_fetched_timestamp for app_id {app_id} to {timestamp}")
    except Exception as e:
        logger.error(f"Error updating last_fetch_time for app {app_id}: {e}")
        db.rollback()

def add_reviews_bulk(db: Session, reviews_data: List[Dict[str, Any]]):
    """Adds multiple reviews to the database, ignoring conflicts on recommendationid."""
    if not reviews_data:
        logger.info("No new reviews to add.")
        return

    try:
        # Prepare for bulk insert with ON CONFLICT DO NOTHING
        stmt = insert(models.Review).values(reviews_data)
        # Using PostgreSQL specific syntax for ON CONFLICT
        stmt = stmt.on_conflict_do_nothing(index_elements=['recommendationid'])

        db.execute(stmt)
        db.commit()
        logger.info(f"Successfully processed bulk insert/ignore for {len(reviews_data)} reviews.")
    except Exception as e:
        logger.error(f"Error during bulk insert reviews: {e}")
        db.rollback()

# --- Potentially Add More CRUD Functions As Needed ---
# Example: Function to get reviews needing translation
def get_reviews_needing_translation(db: Session, limit: int = 100) -> List[models.Review]:
    try:
        return db.query(models.Review)\
                 .filter(models.Review.translation_status == 'pending', models.Review.original_language != 'english')\
                 .limit(limit)\
                 .all()
    except Exception as e:
        logger.error(f"Error fetching reviews needing translation: {e}")
        return []

# Example: Function to update a single review's translation
def update_review_translation(db: Session, recommendation_id: int, translation: str, model: str, status: str):
    try:
        db.query(models.Review).filter(models.Review.recommendationid == recommendation_id).update({
            models.Review.english_translation: translation,
            models.Review.translation_model: model,
            models.Review.translation_status: status
        })
        db.commit()
    except Exception as e:
        logger.error(f"Error updating translation for review {recommendation_id}: {e}")
        db.rollback()

# Example: Function to get reviews needing analysis
def get_reviews_needing_analysis(db: Session, limit: int = 100) -> List[models.Review]:
     try:
        return db.query(models.Review)\
                 .filter(models.Review.analysis_status == 'pending', 
                         models.Review.translation_status.in_(['translated', 'not_required']))\
                 .limit(limit)\
                 .all()
     except Exception as e:
        logger.error(f"Error fetching reviews needing analysis: {e}")
        return []

# Example: Function to update analysis fields
def update_review_analysis(db: Session, recommendation_id: int, analysis_data: dict, status: str):
    try:
        # Prepare update dictionary, handling potential missing keys from analysis_data
        update_dict = {
            models.Review.analyzed_sentiment: analysis_data.get('analyzed_sentiment'),
            models.Review.positive_themes: analysis_data.get('positive_themes'),
            models.Review.negative_themes: analysis_data.get('negative_themes'),
            models.Review.feature_requests: analysis_data.get('feature_requests'),
            models.Review.bug_reports: analysis_data.get('bug_reports'),
            models.Review.llm_analysis_model: analysis_data.get('llm_analysis_model'),
            models.Review.llm_analysis_timestamp: datetime.datetime.now(datetime.timezone.utc),
            models.Review.analysis_status: status
        }
        db.query(models.Review).filter(models.Review.recommendationid == recommendation_id).update(update_dict)
        db.commit()
    except Exception as e:
        logger.error(f"Error updating analysis for review {recommendation_id}: {e}")
        db.rollback()

# --- New CRUD Functions for Reporting ---

def get_reviews_for_app_since(db: Session, app_id: int, start_timestamp: int) -> List[models.Review]:
    """Fetches all reviews for a given app_id created at or after a specific timestamp."""
    try:
        return db.query(models.Review)\
                 .filter(models.Review.app_id == app_id, 
                         models.Review.timestamp_created >= start_timestamp)\
                 .order_by(models.Review.timestamp_created.desc())\
                 .all()
    except Exception as e:
        logger.error(f"Error fetching reviews for app {app_id} since {start_timestamp}: {e}")
        return []

# Placeholder for next function
def get_distinct_languages_for_app_since(db: Session, app_id: int, start_timestamp: int) -> List[str]:
    """Fetches distinct original_language values for reviews for a given app_id created at or after a specific timestamp."""
    try:
        results = db.query(models.Review.original_language)\
                    .filter(models.Review.app_id == app_id, 
                            models.Review.timestamp_created >= start_timestamp)\
                    .distinct()\
                    .all()
        # Results are tuples, extract the first element (the language string)
        return [result[0] for result in results if result[0]]
    except Exception as e:
        logger.error(f"Error fetching distinct languages for app {app_id} since {start_timestamp}: {e}")
        return []

# --- New CRUD Function for Streamlit --- 
def get_app_last_update_time(db: Session, app_id: int) -> Optional[int]:
    """Fetches the last_fetched_timestamp for a specific app_id."""
    try:
        result = db.query(models.TrackedApp.last_fetched_timestamp)\
                   .filter(models.TrackedApp.app_id == app_id)\
                   .scalar()
        return result
    except Exception as e:
        logger.error(f"Error fetching last update time for app {app_id}: {e}")
        return None

def get_max_review_timestamp_for_app(db: Session, app_id: int) -> Optional[int]:
    """Gets the maximum timestamp_created for a given app_id from the reviews table."""
    try:
        max_timestamp = db.query(sql_func.max(models.Review.timestamp_created))\
                        .filter(models.Review.app_id == app_id)\
                        .scalar()
        logger.info(f"Max timestamp found in DB for app {app_id}: {max_timestamp}")
        return max_timestamp
    except Exception as e:
         logger.error(f"Error querying max timestamp for app {app_id}: {e}")
         return None

# Placeholder for next function
# def ... 