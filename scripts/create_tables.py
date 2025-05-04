import logging
import sys
import os

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import engine and Base from the correct locations
from src.database.connection import engine
from src.database.models import Base

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_tables():
    logger.info("Attempting to create database tables...")
    if engine is None:
        logger.error("Database engine is not initialized. Cannot create tables. Check DATABASE_URL and DB server.")
        return

    try:
        logger.info(f"Connecting to engine: {engine.url.render_as_string(hide_password=True)}")
        Base.metadata.create_all(bind=engine)
        logger.info("Tables created successfully (if they didn't exist).")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        logger.error("Please ensure the database server is running and the DATABASE_URL in .env is correct.")

if __name__ == "__main__":
    create_tables() 