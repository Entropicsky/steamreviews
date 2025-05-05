import os, sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
# Remove direct create_engine import if not needed
# from sqlalchemy import create_engine 

from alembic import context

# Remove explicit driver imports
# import psycopg2 
# from sqlalchemy.dialects import postgresql

# Remove manual sys.path manipulation - rely on execution context/PYTHONPATH
# alembic_dir = os.path.dirname(__file__)
# project_root = os.path.abspath(os.path.join(alembic_dir, '..'))
# src_path = os.path.join(project_root, 'src')
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)

# Import Base - Ensure this path works relative to where alembic is run
# If run from root with -m, this might need adjustment, but let's try first.
# Assuming PYTHONPATH or execution context handles finding 'src'
try:
    from src.database.models import Base 
except ImportError:
     # Fallback if src isn't found directly (e.g., path issue)
     # This might indicate a deeper problem needing PYTHONPATH adjustment
     sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
     from src.database.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata # Now use the imported Base

# other values from the config, defined by the needs of env.py,
# can be acquired:-
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

# Remove dotenv loading - rely on Heroku env vars
# from dotenv import load_dotenv
# load_dotenv(...) 
db_url = os.getenv('DATABASE_URL')
if not db_url:
     # Use config object first, then env var as fallback
     db_url = config.get_main_option("sqlalchemy.url")
     if not db_url:
        raise ValueError("DATABASE_URL not found in environment or alembic.ini")

# Ensure URL uses postgresql:// scheme for psycopg2
if db_url.startswith("postgresql+psycopg://"): # Correct if we accidentally left this from previous attempt
    db_url = db_url.replace("postgresql+psycopg://", "postgresql://", 1)
elif db_url.startswith("postgres://"): # Heroku default
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Update config with corrected URL if needed
config.set_main_option('sqlalchemy.url', db_url)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Use standard engine_from_config
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    if connectable is None:
         raise RuntimeError("Application database engine is not initialized!")

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
