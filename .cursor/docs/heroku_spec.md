# Steam Review Analysis System - Heroku Deployment Spec V1

## 1. Overview

This document outlines the process for deploying the Steam Review Analysis application (backend pipeline and V1 Streamlit frontend) to Heroku. It covers initial setup, database schema management using Alembic, backfilling historical review data, configuring scheduled jobs using Heroku Scheduler, and adding necessary frontend indicators.

## 2. Deployment Strategy

*   **Platform:** Heroku
*   **Web Dyno:** Runs the Streamlit application (`web` process in Procfile).
*   **Database:** Heroku Postgres Add-on.
*   **Scheduling:** Heroku Scheduler Add-on to trigger data pipeline tasks periodically (e.g., hourly).
*   **Schema Management:** Alembic for database migrations.
*   **Environment Config:** Heroku Config Vars (for `DATABASE_URL`, `OPENAI_API_KEY`, etc.).

## 3. Prerequisites (Manual User Actions)

1.  **Heroku Account & CLI:** User needs a Heroku account and the Heroku CLI installed and logged in.
2.  **Create Heroku App:** User creates a new Heroku application (`heroku create your-app-name`).
3.  **Add Postgres Add-on:** User provisions a Heroku Postgres database (`heroku addons:create heroku-postgresql:basic` or similar tier).
4.  **Add Scheduler Add-on:** User adds the Heroku Scheduler add-on (`heroku addons:create scheduler:standard`).
5.  **Set Config Vars:** User sets necessary environment variables in Heroku dashboard or via CLI (`heroku config:set VAR=value`), including:
    *   `OPENAI_API_KEY`
    *   `OPENAI_MODEL` (optional, defaults in code)
    *   `CACHE_DIR` (can likely default to `/tmp` or be omitted if cache isn't critical in Heroku ephemeral filesystem)
    *   `DATABASE_URL` (This is usually set automatically by the Postgres add-on, but verify).
6.  **Add Git Remote:** User adds Heroku remote to the local Git repository (`heroku git:remote -a your-app-name`).

## 4. Code Preparation & Configuration

1.  **`requirements.txt`:** Ensure all production dependencies are listed, including `streamlit`, `gunicorn`, `SQLAlchemy`, `psycopg2-binary`, `python-dotenv`, `requests`, `openai`, `tenacity`, `pandas`, `openpyxl`, `pydantic`, and `alembic`.
2.  **`Procfile`:** Create/confirm the `Procfile` in the project root:
    ```Procfile
    web: gunicorn streamlit_app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0
    release: alembic upgrade head
    # Worker process for pipeline (alternative to scheduler)
    # worker: python -m src.run_pipeline
    ```
    *   **`web`:** Runs Streamlit using `gunicorn` on the Heroku-assigned `$PORT`.
    *   **`release`:** Automatically runs database migrations (`alembic upgrade head`) during each new deployment/release.
3.  **`runtime.txt`:** Create a `runtime.txt` file specifying the Python version (e.g., `python-3.11.7`).
4.  **Alembic Setup:**
    *   Install Alembic (`pip install alembic`). Add to `requirements.txt`.
    *   Initialize Alembic (`alembic init alembic`).
    *   Configure `alembic.ini` to find the database URL (using `os.getenv("DATABASE_URL")`).
    *   Configure `alembic/env.py`:
        *   Import `Base` from `src.database.models`.
        *   Set `target_metadata = Base.metadata`.
        *   Ensure it reads `DATABASE_URL` from the environment.
    *   Generate initial migration script: `alembic revision --autogenerate -m "Initial schema setup"` (Run this *after* the models are stable).
    *   Apply initial migration locally: `alembic upgrade head`.
5.  **Streamlit App (`streamlit_app.py`):**
    *   Add logic to fetch and display the `last_fetched_timestamp` from the `tracked_apps` table for the selected app, converting it to a readable format (e.g., "Data current as of YYYY-MM-DD HH:MM UTC"). This requires a new CRUD function.

## 5. Database Backfilling

1.  **Target App IDs:** Initially target Dead Zone Rogue (`3228590`) and Smite 2 (App ID TBD - needs lookup).
2.  **Backfill Script (`scripts/backfill_reviews.py`):**
    *   Create a new script that takes an `app_id` as an argument.
    *   It should *not* use the `after_timestamp` logic.
    *   It should fetch *all* reviews page by page using the Steam API cursor, starting from the beginning (`cursor='*'`).
    *   For each batch of reviews fetched, it should convert them to the DB format (like `main_fetcher.py`) and insert them using `crud.add_reviews_bulk` (`ON CONFLICT DO NOTHING` handles overlaps safely).
    *   Include logging to track progress (e.g., page number, reviews processed).
    *   Consider rate limiting / sleep intervals to avoid hammering the Steam API.
3.  **Execution:**
    *   Run this script manually (potentially via `heroku run`) against the *production* Heroku database *after* deployment for each target App ID.
    *   Example: `heroku run python scripts/backfill_reviews.py --app-id 3228590`
    *   The `main_fetcher` will then take over incremental updates based on the timestamps established by the backfill.

## 6. Scheduling (Heroku Scheduler)

1.  **Task Definition:** Configure Heroku Scheduler via the dashboard or `heroku run`.
2.  **Command:** Set the scheduler task command. Options:
    *   **Recommended:** Run the pipeline script: `bash run_pipeline.sh` (Ensure script uses absolute paths or handles execution context correctly). This runs fetch, translate, analyze sequentially.
    *   **Alternative:** Schedule individual components: `python -m src.main_fetcher`, `python -m src.run_translator`, `python -m src.run_analyzer` with appropriate frequencies and dependencies (more complex setup).
3.  **Frequency:** Set the desired frequency (e.g., `Hourly`, `Daily @ 00:00`). Hourly seems appropriate based on the requirement for up-to-date data.
4.  **Monitoring:** Monitor scheduler logs via Heroku dashboard or CLI (`heroku logs --source app --dyno scheduler`) to ensure jobs run successfully.

## 7. Deployment Process

1.  Ensure all code changes (Alembic setup, Streamlit updates, Procfile, requirements.txt, runtime.txt) are committed to Git.
2.  Ensure Heroku app, addons, and config vars are set up (Manual Steps).
3.  Push code to Heroku: `git push heroku main`.
4.  Monitor the build and release phase logs (`heroku logs --tail`). Verify Alembic migrations run successfully during the release phase.
5.  Manually run the backfill script for target App IDs: `heroku run python scripts/backfill_reviews.py --app-id <ID>`.
6.  Verify the Streamlit app is accessible and functional.
7.  Verify the Heroku Scheduler job runs successfully on its next scheduled interval.

## 8. Post-Deployment (Optional V1.1+)

*   **Cloudflare:** Set up Cloudflare for DNS and potentially Access Control (requires configuring domain and Cloudflare settings). This is outside the scope of the initial Heroku deployment.
*   **Admin Interface:** Create a simple way (another Streamlit page, basic script) to add/deactivate apps in the `tracked_apps` table. 