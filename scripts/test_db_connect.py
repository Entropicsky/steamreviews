import logging
import sys
import os

# Adjust path to import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.database.connection import engine # Import the potentially problematic engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

def test_connection():
    logger.info("Attempting to test database connection...")
    if engine is None:
        logger.error("Engine object imported from connection.py is None. Initialization failed there.")
        return

    try:
        logger.info(f"Connecting using engine: {engine.url.render_as_string(hide_password=True)}")
        connection = engine.connect()
        logger.info("Successfully connected to the database!")
        connection.close()
        logger.info("Connection closed.")
    except Exception as e:
        logger.error(f"Failed to connect to database using the engine from connection.py: {e}")
        logger.exception("Connection Error Details:")

if __name__ == "__main__":
    test_connection() 