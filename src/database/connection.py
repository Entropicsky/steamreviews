import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
# from sqlalchemy.dialects import postgresql # Not needed

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
ENGINE_URL = DATABASE_URL # Use original URL directly for psycopg2

if not DATABASE_URL:
    logger.error("DATABASE_URL environment variable not set. Exiting.")
else:
    # Use the original DATABASE_URL for logging/display if needed
    logger.info(f"[DB Connection] Using DATABASE_URL: {DATABASE_URL}") # Log original URL

# Create engine
try:
    # Remove explicit dialect reference
    
    if ENGINE_URL: # Use ENGINE_URL which is same as DATABASE_URL now
        engine = create_engine(ENGINE_URL)
        logger.info("[DB Connection] SQLAlchemy engine created using psycopg2.")
    else:
         engine = None
         logger.error("[DB Connection] Could not determine valid ENGINE_URL.")
except Exception as e:
    logger.error(f"[DB Connection] Failed to create SQLAlchemy engine: {e}")
    engine = None

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