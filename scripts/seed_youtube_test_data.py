#!/usr/bin/env python
# scripts/seed_youtube_test_data.py
import logging
import os
import sys
from dotenv import load_dotenv

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.database.connection import get_db
from src.database.crud_youtube import (
    add_game,
    add_influencer,
    add_or_update_channel,
    add_game_influencer_mapping,
    get_game_by_id,
    get_influencer_by_id,
    get_channel_by_id
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
GAME_NAME = "SMITE 2"
GAME_STEAM_APP_ID = None # Or set if known, e.g., 1107350 (actual ID might differ)
GAME_SLACK_CHANNEL_ID = "C0YTTEST1" # Placeholder

INFLUENCER_NAME = "Weak3n"
INFLUENCER_NOTES = "SMITE focused YouTuber."

CHANNEL_ID = "UCk0q5N3Wz9yG4rSg1Vv6MVA"
CHANNEL_NAME = "Weak3n"
CHANNEL_HANDLE = "@Weak3n"
# --- End Configuration ---

def seed_data():
    logger.info("Starting database seeding for YouTube feedback testing...")
    load_dotenv() # Load environment variables for database connection etc.

    db_gen = get_db()
    db = next(db_gen)

    try:
        # 1. Add Game
        logger.info(f"Adding/Verifying Game: {GAME_NAME}")
        game = add_game(db, name=GAME_NAME, steam_app_id=GAME_STEAM_APP_ID, slack_channel_id=GAME_SLACK_CHANNEL_ID)
        if not game:
            logger.error(f"Failed to add or find game: {GAME_NAME}. Aborting.")
            return
        logger.info(f"Using Game ID: {game.id}")
        game_id = game.id

        # 2. Add Influencer
        logger.info(f"Adding/Verifying Influencer: {INFLUENCER_NAME}")
        influencer = add_influencer(db, name=INFLUENCER_NAME, notes=INFLUENCER_NOTES)
        if not influencer:
            logger.error(f"Failed to add or find influencer: {INFLUENCER_NAME}. Aborting.")
            return
        logger.info(f"Using Influencer ID: {influencer.id}")
        influencer_id = influencer.id

        # 3. Add YouTube Channel
        logger.info(f"Adding/Updating YouTube Channel: {CHANNEL_NAME} ({CHANNEL_ID})")
        channel = add_or_update_channel(db, channel_id=CHANNEL_ID, influencer_id=influencer_id, channel_name=CHANNEL_NAME, handle=CHANNEL_HANDLE)
        if not channel:
            logger.error(f"Failed to add or update channel: {CHANNEL_ID}. Aborting.")
            return
        logger.info(f"Using Channel ID: {channel.id}")

        # 4. Add Game-Influencer Mapping
        logger.info(f"Adding/Verifying Mapping between Game {game_id} and Influencer {influencer_id}")
        mapping = add_game_influencer_mapping(db, game_id=game_id, influencer_id=influencer_id, is_active=True)
        if not mapping:
            logger.error(f"Failed to add or find mapping for Game {game_id} and Influencer {influencer_id}. Aborting.")
            return
        logger.info(f"Mapping confirmed/added (GameID: {mapping.game_id}, InfluencerID: {mapping.influencer_id}, Active: {mapping.is_active})")

        logger.info("Seeding completed successfully.")

        # Verification (Optional)
        logger.info("--- Verification ---")
        verify_game = get_game_by_id(db, game_id)
        verify_influencer = get_influencer_by_id(db, influencer_id)
        verify_channel = get_channel_by_id(db, CHANNEL_ID)
        logger.info(f"Game: {verify_game.name if verify_game else 'Not Found'}")
        logger.info(f"Influencer: {verify_influencer.name if verify_influencer else 'Not Found'}")
        logger.info(f"Channel: {verify_channel.channel_name if verify_channel else 'Not Found'} (Influencer ID: {verify_channel.influencer_id if verify_channel else 'N/A'})")
        logger.info(f"Mapping: Game {mapping.game_id}, Influencer {mapping.influencer_id}, Active {mapping.is_active}")
        logger.info("--------------------")


    except Exception as e:
        logger.error(f"An error occurred during seeding: {e}", exc_info=True)
    finally:
        if db:
            db.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    seed_data() 