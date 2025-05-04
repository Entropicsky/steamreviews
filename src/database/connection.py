import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file to get DATABASE_URL
# Assume this runs relative to src/, so go up two levels for root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
dotenv_path = os.path.join(ROOT_DIR, '.env')
logger.info(f"[DB Connection] Attempting to load .env from: {dotenv_path}")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)
    logger.info(f"[DB Connection] Loaded .env from: {dotenv_path}")
else:
    logger.warning(f"[DB Connection] .env file not found at {dotenv_path}. Relying on system env for DATABASE_URL.")
    load_dotenv(override=True) # Fallback

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable not set. Exiting.")
    # In a real app, might raise or exit
    # For now, just log and let engine creation fail
else:
    # Mask password for logging
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(DATABASE_URL)
        if parsed.password:
             safe_netloc = f"{parsed.username}:***@{parsed.hostname}:{parsed.port}"
             safe_url_parts = list(parsed)
             safe_url_parts[1] = safe_netloc
             safe_url = urlunparse(safe_url_parts)
             logger.info(f"[DB Connection] Using DATABASE_URL: {safe_url}")
        else:
             logger.info(f"[DB Connection] Using DATABASE_URL: {DATABASE_URL}")
    except Exception:
        logger.info("[DB Connection] Using DATABASE_URL: (Could not parse for safe logging)")

# Create engine (will raise error if URL is invalid or DB not reachable)
try:
    engine = create_engine(DATABASE_URL)
    logger.info("[DB Connection] SQLAlchemy engine created.")
except Exception as e:
    logger.error(f"[DB Connection] Failed to create SQLAlchemy engine: {e}")
    # Optionally raise or exit if engine creation is critical at import time
    engine = None # Set engine to None to indicate failure

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logger.info("[DB Connection] SQLAlchemy SessionLocal created.")

# Dependency function
def get_db():
    if engine is None:
        logger.error("Database engine is not initialized. Cannot create session.")
        raise RuntimeError("Database engine failed to initialize.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 