# Steam Review & YouTube Feedback Analysis Tool

This project fetches, translates, analyzes, and stores Steam game reviews and YouTube video feedback to provide insights and generate reports.

## Overview

The system consists of:

1.  **Backend Data Pipelines:**
    *   **Steam:** Fetches new reviews periodically for tracked games using the Steam API, stores them, translates non-English reviews (OpenAI), and performs structured analysis (OpenAI).
    *   **YouTube:** Fetches new videos/transcripts periodically for tracked influencer channels using the Supadata API, stores them, and performs structured analysis (OpenAI) for relevance and feedback.
    *   **Common:** Uses a PostgreSQL database, SQLAlchemy for ORM, and Alembic for database migrations.
2.  **Streamlit Web Frontend:**
    *   Provides a unified UI to manage tracked games, influencers, and channels.
    *   Allows viewing of analyzed feedback from both Steam and YouTube.
    *   Generates on-demand multi-sheet Excel reports summarizing feedback for selected games and date ranges.
3.  **Scheduled Reporting Scripts:**
    *   `run_scheduled_report.py`: Generates weekly or monthly **Steam review** Excel reports and uploads to Slack.
    *   `scripts/youtube_slack_reporter.py`: Generates daily, weekly, or monthly **YouTube feedback** Excel reports and uploads to Slack.

## Local Development Setup

1.  **Prerequisites:**
    *   Python 3.11+ (Check Python version used in `Dockerfile` if deployed)
    *   Docker and Docker Compose (For local PostgreSQL)
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

5.  **Configure Environment (`.env` file):**
    *   Copy `env.example` to `.env`.
    *   **Required:**
        *   `OPENAI_API_KEY`: Your OpenAI API key.
        *   `DATABASE_URL`: Connection string for the PostgreSQL database.
            *   Local Docker default: `DATABASE_URL=postgresql://steam_user:steam_password@localhost:5433/steam_reviews_db`
        *   `SUPADATA_API_KEY`: Your Supadata API key (for YouTube data).
    *   **For Scheduled Slack Reports:**
        *   `SLACK_BOT_TOKEN`: Your Slack Bot token (starting `xoxb-`).
        *   `DEFAULT_SLACK_CHANNEL_ID`: The default Slack channel ID (e.g., `C123ABC456`) to post reports to if `--channel-id` isn't specified when running the Slack reporter scripts.
        *   `TEST_SLACK_CHANNEL_ID` (Optional): A channel ID used for testing the Slack client directly (`python -m src.slack_client`).

6.  **Start PostgreSQL Database (Local):**
    *   Ensure Docker Desktop is running.
    *   Run: `docker compose up -d db`

7.  **Initialize Database Schema:**
    *   Apply Alembic migrations:
        ```bash
        alembic upgrade head
        ```

## Running the Application

### Backend Pipelines

*   **Steam Pipeline:** To manually trigger the full fetch/translate/analyze pipeline for Steam reviews:
    ```bash
    bash run_pipeline.sh 
    ```
    *   Or run individual Steam steps:
        ```bash
        python -m src.main_fetcher
        python -m src.run_translator
        python -m src.run_analyzer
        ```
*   **YouTube Pipeline:** To manually trigger the full fetch/analyze pipeline for YouTube feedback:
    ```bash
    bash run_youtube_pipeline.sh
    ```
    *   Or run individual YouTube steps:
        ```bash
        # Optional arguments: --max-age-days (default: 7)
        python -m scripts.youtube_fetcher [--max-age-days DAYS]
        python -m scripts.youtube_analyzer_worker
        ```

### Streamlit Web App

```bash
streamlit run streamlit_app.py
```
Access at `http://localhost:8501`. Navigate using the sidebar to manage Steam/YouTube settings or view feedback.

### Scheduled Slack Reports

These scripts generate reports for a specified time period and post them to Slack.

**Prerequisites:**

*   Environment variables `SLACK_BOT_TOKEN` and (`DEFAULT_SLACK_CHANNEL_ID` or `--channel-id` argument) must be set.
*   A Slack Bot must be created with the `files:write` permission and added to the target channel(s).

**Manual Execution (Local):**

*   **Steam:**
    ```bash
    # Example: Weekly report for App ID 12345 to default channel
    python run_scheduled_report.py --app-id 12345 --timespan weekly
    
    # Example: Monthly report for App ID 67890 to specific channel CABCDEF123
    python run_scheduled_report.py --app-id 67890 --timespan monthly --channel-id CABCDEF123
    ```
*   **YouTube:**
    ```bash
    # Example: Daily report for Game ID 1 to default channel
    python -m scripts.youtube_slack_reporter --game-id 1 --period last_day
    
    # Example: Weekly report for Game ID 1 to specific channel CABCDEF123 with custom message
    python -m scripts.youtube_slack_reporter --game-id 1 --period last_week --channel-id CABCDEF123 --message "Weekly YouTube Digest"
    ```

**Scheduling with Cron/Scheduler (Example - see `run_scheduled_report.py` for more):**

Similar cron setup as shown for Steam, but pointing to `scripts/youtube_slack_reporter.py` with appropriate arguments (e.g., `--period last_day` for daily runs).

**Slack Setup:** (Same as before)

1.  Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app ("From scratch").
2.  Navigate to "OAuth & Permissions".
3.  Under "Bot Token Scopes", add the `files:write` scope.
4.  Click "Install to Workspace" and allow permissions.
5.  Copy the "Bot User OAuth Token" (starts `xoxb-`) - this is your `SLACK_BOT_TOKEN`.
6.  Invite the created bot user to the target Slack channel(s).
7.  Find the Channel ID by right-clicking the channel name in Slack and selecting "Copy link". The ID starts with `C` or `G`.

## Project Structure

*   `.cursor/`: Agent notes, docs, rules, tools.
*   `alembic/`: Database migration scripts.
*   `scripts/`: Standalone scripts for pipeline tasks, seeding, testing, reporting.
    *   `youtube_fetcher.py`: Fetches YouTube video/transcript data.
    *   `youtube_analyzer_worker.py`: Analyzes fetched YouTube transcripts.
    *   `youtube_slack_reporter.py`: Generates & uploads YouTube reports to Slack.
    *   `seed_youtube_test_data.py`, `test_supadata_api.py`, etc.: Utility/test scripts.
*   `src/`: Main application source code.
    *   `database/`: SQLAlchemy models, connection, CRUD operations (`crud.py` for Steam, `crud_youtube.py` for YouTube).
    *   `processing/`: (Currently Steam) Translation and analysis logic.
    *   `reporting/`: Excel report generation logic (`excel_generator.py` for Steam, `youtube_report_generator.py` for YouTube).
    *   `utils/`: Utility functions.
    *   `youtube/`: YouTube-specific Supadata client and analyzer logic.
    *   `openai_client.py`: Handles OpenAI API calls.
    *   `steam_client.py`: Handles Steam API calls.
    *   `constants.py`: Shared constants.
    *   `main_fetcher.py`: Orchestrates fetching new Steam reviews.
    *   `run_translator.py`: Processes pending Steam translations.
    *   `run_analyzer.py`: Processes pending Steam analyses.
*   `streamlit_app.py`: The Streamlit web frontend (handles both Steam & YouTube).
*   `run_scheduled_report.py`: Script for scheduled **Steam** Slack reports.
*   `alembic.ini`: Alembic configuration.
*   `docker-compose.yml`: Docker configuration for local database.
*   `heroku.yml`: Heroku process definitions.
*   `requirements.txt`: Python dependencies.
*   `run_pipeline.sh`: Script to run the **Steam** backend pipeline steps.
*   `run_youtube_pipeline.sh`: Script to run the **YouTube** backend pipeline steps.
*   `.env.example`: Example environment file.
*   `README.md`: This file.

## Deployment (Heroku)

This application is currently configured for deployment to Heroku via `heroku.yml`.

*   It uses a Docker build defined in `Dockerfile`.
*   The `web` process type runs the Streamlit application.
*   Required Heroku Config Vars (Set via Dashboard or CLI):
    *   `DATABASE_URL`
    *   `OPENAI_API_KEY`
    *   `SUPADATA_API_KEY`
    *   `SLACK_BOT_TOKEN` (if using scheduled Slack reports)
    *   `DEFAULT_SLACK_CHANNEL_ID` (optional default for scheduled reports)

*(Note: The previous API server implementation for Zapier integration has been removed but the spec remains in `.cursor/notes/`)* 