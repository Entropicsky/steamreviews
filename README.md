# Steam Review Analysis Tool

This project fetches, translates, analyzes, and stores Steam game reviews to provide insights and generate reports, with options for on-demand generation via a web UI or scheduled delivery to Slack.

## Overview

The system consists of:

1.  **Backend Data Pipeline:**
    *   Fetches new reviews periodically for tracked games using the Steam API.
    *   Stores review data in a PostgreSQL database.
    *   Translates non-English reviews using the OpenAI API.
    *   Performs structured analysis (sentiment, themes, etc.) on each review using the OpenAI API.
    *   Uses SQLAlchemy for ORM and Alembic for database migrations.
2.  **Streamlit Web Frontend (Optional):**
    *   *(Currently enabled in `heroku.yml` as the `web` process)*
    *   Provides a simple UI to view tracked games.
    *   Allows users to manage the list of tracked games (add, activate/deactivate).
    *   Generates on-demand multi-sheet Excel reports summarizing reviews for a selected game and date range.
3.  **Scheduled Reporting Script:**
    *   `run_scheduled_report.py`: Generates weekly or monthly Excel reports for a specific App ID.
    *   Calculates the appropriate date range (last week or last month).
    *   Calls the same report generation logic used by the frontend.
    *   Uploads the generated Excel file directly to a specified Slack channel using a Slack Bot Token.
    *   Designed to be run via a scheduler like `cron`.

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
    *   **For Scheduled Slack Reports:**
        *   `SLACK_BOT_TOKEN`: Your Slack Bot token (starting `xoxb-`).
        *   `DEFAULT_SLACK_CHANNEL_ID`: The default Slack channel ID (e.g., `C123ABC456`) to post reports to if `--channel-id` isn't specified when running the script.

6.  **Start PostgreSQL Database (Local):**
    *   Ensure Docker Desktop is running.
    *   Run: `docker compose up -d db`

7.  **Initialize Database Schema:**
    *   Apply Alembic migrations:
        ```bash
        alembic upgrade head
        ```

## Running the Application

### Backend Pipeline

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

### Streamlit Web App (If Enabled)

```bash
streamlit run streamlit_app.py
```
Access at `http://localhost:8501`.

### Scheduled Slack Reports

This script generates a report for a specified time period and posts it to Slack.

**Prerequisites:**

*   Environment variables `SLACK_BOT_TOKEN` and (`DEFAULT_SLACK_CHANNEL_ID` or `--channel-id` argument) must be set.
*   A Slack Bot must be created with the `files:write` permission and added to the target channel(s).

**Manual Execution (Local):**

```bash
# Example: Weekly report for App ID 12345 to default channel
python run_scheduled_report.py --app-id 12345 --timespan weekly

# Example: Monthly report for App ID 67890 to specific channel CABCDEF123
python run_scheduled_report.py --app-id 67890 --timespan monthly --channel-id CABCDEF123
```

**Scheduling with Cron (Example):**

Create crontab entries (e.g., using `crontab -e`) on a server where the project code, dependencies, and environment variables are available.

```cron
# Example: Run weekly report for App ID 12345 every Monday at 8:00 AM
# Ensure paths and environment setup (e.g., activating venv or setting vars) are correct for your cron environment
0 8 * * 1 /path/to/.venv/bin/python /path/to/steamreviews/run_scheduled_report.py --app-id 12345 --timespan weekly >> /path/to/logs/steam_report_cron.log 2>&1

# Example: Run monthly report for App ID 12345 on the 1st of the month at 9:00 AM
0 9 1 * * /path/to/.venv/bin/python /path/to/steamreviews/run_scheduled_report.py --app-id 12345 --timespan monthly >> /path/to/logs/steam_report_cron.log 2>&1
```

**Slack Setup:**

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
*   `src/`: Main application source code.
    *   `database/`: SQLAlchemy models, connection, CRUD operations.
    *   `processing/`: Translation and analysis logic.
    *   `reporting/`: Excel report generation logic.
    *   `utils/`: Utility functions (e.g., R2 uploader - *currently removed*).
    *   `constants.py`: Shared constants.
    *   `main_fetcher.py`: Orchestrates fetching new reviews.
    *   `run_translator.py`: Processes pending translations.
    *   `run_analyzer.py`: Processes pending analyses.
    *   `openai_client.py`: Handles OpenAI API calls.
    *   `steam_client.py`: Handles Steam API calls.
*   `streamlit_app.py`: The Streamlit web frontend.
*   `run_scheduled_report.py`: Script for scheduled Slack reports.
*   `alembic.ini`: Alembic configuration.
*   `docker-compose.yml`: Docker configuration for local database.
*   `heroku.yml`: Heroku process definitions.
*   `requirements.txt`: Python dependencies.
*   `run_pipeline.sh`: Script to run the backend pipeline steps.
*   `.env.example`: Example environment file.
*   `README.md`: This file.

## Deployment (Heroku)

This application is currently configured for deployment to Heroku via `heroku.yml`.

*   It uses a Docker build defined in `Dockerfile`.
*   The `web` process type runs the Streamlit application.
*   Required Heroku Config Vars (Set via Dashboard or CLI):
    *   `DATABASE_URL`
    *   `OPENAI_API_KEY`
    *   `SLACK_BOT_TOKEN` (if using scheduled reports via Heroku Scheduler + `run_scheduled_report.py`)
    *   `DEFAULT_SLACK_CHANNEL_ID` (optional default for scheduled reports)

*(Note: The previous API server implementation for Zapier integration has been removed but the spec remains in `.cursor/notes/`)* 