#!/usr/bin/env python3
"""
Setup script to add initial test data for YouTube feedback testing.
"""
import logging
import sys
import os

# Adjust path to import from src
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.append(SRC_DIR)

from src.database.connection import get_db
from src.database import crud_youtube as crud

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- Test Data Configuration ---
GAME_NAME = "SMITE 2"
INFLUENCER_NAME = "Weak3n"
# Use the handle URL directly as Supadata supports it for channel ID
CHANNEL_ID_OR_HANDLE = "@Weak3n" 
SLACK_CHANNEL = "#smite2-youtube-test" # Example slack channel

def setup_data():
    logger.info("--- Setting up YouTube Feedback Test Data ---")
    db_gen = get_db()
    db = next(db_gen)

    try:
        # 1. Add Game
        game = crud.add_game(db, name=GAME_NAME, slack_channel_id=SLACK_CHANNEL)
        if not game:
            logger.error(f"Failed to add or get game: {GAME_NAME}")
            return
        logger.info(f"Ensured Game exists: {game.name} (ID: {game.id})")

        # 2. Add Influencer
        influencer = crud.add_influencer(db, name=INFLUENCER_NAME)
        if not influencer:
            logger.error(f"Failed to add or get influencer: {INFLUENCER_NAME}")
            return
        logger.info(f"Ensured Influencer exists: {influencer.name} (ID: {influencer.id})")

        # 3. Add YouTube Channel (linked to influencer)
        # Supadata client uses the handle URL directly as 'id'
        # We store the handle itself in the 'handle' column
        channel = crud.add_or_update_channel(db, channel_id=CHANNEL_ID_OR_HANDLE, 
                                            influencer_id=influencer.id, 
                                            handle=CHANNEL_ID_OR_HANDLE,
                                            channel_name=INFLUENCER_NAME) # Use influencer name as default channel name
        if not channel:
            logger.error(f"Failed to add or update channel: {CHANNEL_ID_OR_HANDLE}")
            return
        # Note: We store the handle URL (@Weak3n) as the primary key (id) here,
        # because that's what Supadata accepts. If Supadata resolves it to a 
        # canonical ID (UC...) internally, our DB model might need adjustment later,
        # but this matches the API usage for now.
        logger.info(f"Ensured Channel exists: {channel.id} (Handle: {channel.handle}) linked to Influencer ID: {channel.influencer_id}")

        # 4. Add Game-Influencer Mapping
        mapping = crud.add_game_influencer_mapping(db, game_id=game.id, influencer_id=influencer.id)
        if not mapping:
            logger.error(f"Failed to add mapping for Game {game.id} and Influencer {influencer.id}")
            return
        logger.info(f"Ensured Mapping exists for Game ID: {mapping.game_id} and Influencer ID: {mapping.influencer_id}, Active: {mapping.is_active}")

        logger.info("--- Test Data Setup Complete ---")

    except Exception as e:
        logger.critical(f"An error occurred during test data setup: {e}", exc_info=True)
    finally:
        # Close session?
        pass 

if __name__ == "__main__":
    setup_data() 