# Steam Review Analysis Tool

This project fetches, translates, analyzes, and stores Steam game reviews to provide insights and generate reports.

## Overview

The system consists of:

1.  **Backend Data Pipeline:**
    *   Fetches new reviews periodically for tracked games using the Steam API.
    *   Stores review data in a PostgreSQL database.
    *   Translates non-English reviews using the OpenAI API.
    *   Performs structured analysis (sentiment, themes, etc.) on each review using the OpenAI API.
    *   Uses SQLAlchemy for ORM and Alembic for database migrations.
2.  **Streamlit Web Frontend:**
    *   Provides a simple UI to view tracked games.
    *   Allows users to manage the list of tracked games (add, activate/deactivate).
    *   Generates on-demand multi-sheet Excel reports summarizing reviews for a selected game and date range.

## Local Development Setup

1.  **Prerequisites:**
    *   Python 3.11+ (check `runtime.txt` for specific version)
    *   Docker and Docker Compose
    *   Git

2.  **Clone Repository:**
    ```bash
    git clone <repository_url>
    cd steamreviews
    ```

3.  **Create Virtual Environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Environment:**
    *   Copy `env.example` to `.env`.
    *   Edit `.env` and add your `OPENAI_API_KEY`.
    *   Ensure `DATABASE_URL` is set correctly for the local Docker database (see step 6).
        *   Default expected: `DATABASE_URL=postgresql://steam_user:steam_password@localhost:5433/steam_reviews_db`

6.  **Start PostgreSQL Database:**
    *   Make sure Docker Desktop is running.
    *   Run: `docker compose up -d db`

7.  **Initialize Database Schema:**
    *   Apply the initial Alembic migration:
        ```bash
        alembic upgrade head
        ```
    *   (Optional) Add initial apps to track:
        ```bash
        docker exec <container_id> psql -U steam_user -d steam_reviews_db -c "INSERT INTO tracked_apps ..."
        # Replace <container_id> with the actual ID from `docker ps`
        ```

8.  **Run Backend Pipeline (Optional):**
    *   To manually trigger the full fetch/translate/analyze pipeline:
        ```bash
        bash run_pipeline.sh
        ```
    *   Or run individual steps:
        ```bash
        python -m src.main_fetcher
        python -m src.run_translator
        python -m src.run_analyzer
        ```

9.  **Run Streamlit App:**
    ```bash
    streamlit run streamlit_app.py
    ```
    *   Access the app at `http://localhost:8501`.

## Project Structure

*   `.cursor/`: Agent notes, docs, rules, tools.
*   `alembic/`: Database migration scripts.
*   `scripts/`: Utility scripts (e.g., `create_tables.py`, `backfill_reviews.py`).
*   `src/`: Main application source code.
    *   `database/`: SQLAlchemy models, connection, CRUD operations.
    *   `processing/`: Translation and analysis logic.
    *   `reporting/`: Excel report generation logic.
    *   `constants.py`: Shared constants like `LANGUAGE_MAP`.
    *   `main_fetcher.py`: Orchestrates fetching new reviews.
    *   `run_translator.py`: Processes pending translations.
    *   `run_analyzer.py`: Processes pending analyses.
    *   `openai_client.py`: Handles OpenAI API calls.
    *   `steam_client.py`: Handles Steam API calls.
*   `streamlit_app.py`: The Streamlit web frontend.
*   `alembic.ini`: Alembic configuration.
*   `docker-compose.yml`: Docker configuration for local database.
*   `Procfile`: Heroku process definition.
*   `requirements.txt`: Python dependencies.
*   `runtime.txt`: Python version for Heroku.
*   `run_pipeline.sh`: Script to run the backend pipeline steps.

## Deployment

This application is designed for deployment to Heroku using the configuration specified in `Procfile`, `runtime.txt`, and `heroku_spec.md`. 