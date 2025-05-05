# Project Checklist

## Setup Phase
- [x] Create project documentation structure
- [x] Create virtual environment
- [x] Define overall project architecture
- [x] Create technical specification
- [x] Identify key dependencies

## Prototype Development Phase
- [x] Create a simple prototype script that:
  - [x] Sets up OpenAI client using Responses API
  - [x] Fetches 200 Chinese reviews from Steam for app ID 3228590
  - [x] Translates reviews using gpt-4.1 model
  - [x] Generates a summary of trends and insights
  - [x] Outputs results in a readable format
- [x] Refactor prototype for modularity (models, steam_client, openai_client)
- [x] Add command-line arguments for language, app_id, max_reviews
- [x] Add Excel output with multiple sheets
- [x] Implement structured JSON analysis output with Pydantic validation
- [x] Implement unique output directories per run

## Backend Data Pipeline Development Phase (V1)

### Phase 1: Database Setup & ORM
*   [x] **1.1:** Install necessary DB driver (`psycopg2-binary`) and ORM (`SQLAlchemy`).
    *   [x] Add to `requirements.txt`.
    *   [x] Run `pip install -r requirements.txt`.
*   [x] **1.2:** Define SQLAlchemy ORM models (`TrackedApp`, `Review`) in `src/database/models.py`.
*   [x] **1.3:** Set up database connection logic in `src/database/connection.py`.
*   [x] **1.4:** Write script (`scripts/create_tables.py`) to initialize DB schema.
    *   [x] **Test:** Verify tables created correctly.
*   [x] **1.5:** Implement basic CRUD helpers in `src/database/crud.py`.
    *   [ ] **Test:** Unit test CRUD functions.

### Phase 2: Steam Client Refactoring (Incremental Fetching)
*   [x] **2.1:** Modify `SteamAPI.fetch_reviews` for `after_timestamp` parameter.
*   [x] **2.2:** Implement incremental fetching logic (stop on older timestamp).
*   [x] **2.3:** Ensure `fetch_reviews` returns new reviews list and latest timestamp.
    *   [x] **Test:** Unit test `fetch_reviews` with mocked API calls.

### Phase 3: Main Fetcher/Orchestrator Script
*   [x] **3.1:** Create `src/main_fetcher.py`.
*   [x] **3.2:** Implement logic: get apps, loop, call `fetch_reviews`.
    *   [ ] **Test:** Run fetcher, verify Steam client calls (mocked).
*   [x] **3.3:** Implement logic: insert new raw reviews into DB (handle conflicts).
    *   [x] **Test:** Run fetcher, verify DB inserts and status flags.
*   [x] **3.4:** Implement logic: update `last_fetched_timestamp` in DB.
    *   [x] **Test:** Verify timestamp update after fetch.

### Phase 4: Data Processing Services
*   [x] **4.1:** Refactor `Translator` service (`src/processing/translator.py`?).
*   [x] **4.2:** Implement translation processing loop (query pending, call translator, update DB).
    *   [x] **Test:** Seed DB, run translator, verify DB updates/errors.
*   [x] **4.3:** Create `ReviewAnalyzer` service (`src/processing/analyzer.py`?) with Pydantic model and JSON prompt.
*   [x] **4.4:** Implement analysis processing loop (query pending, call analyzer, update DB).
    *   [x] **Test:** Seed DB, run analyzer, verify DB updates/errors.

### Phase 5: Scheduling & Final Setup
*   [x] **5.1:** Consolidate environment variables in `.env`.
*   [x] **5.2:** Create/document run command/script.
*   [ ] **5.3 (Manual):** Set up system `cron` job.
    *   [ ] **Test:** Trigger cron job, monitor logs, check DB for end-to-end success.

## Frontend & Reporting Phase (V1) 

### Phase 1: Backend Adjustments (Database CRUD)
*   [x] **1.1:** Implement `get_reviews_for_app_since` function in `src/database/crud.py`.
    *   [ ] **Test:** Add unit test for `get_reviews_for_app_since` (using test session/data).
*   [x] **1.2:** Implement `get_distinct_languages_for_app_since` function in `src/database/crud.py`.
    *   [ ] **Test:** Add unit test for `get_distinct_languages_for_app_since`.
*   [x] **1.3:** Modify `get_active_tracked_apps` to return `app_id` and `name`.
    *   [ ] **Test:** Update unit test for `get_active_tracked_apps`.

### Phase 2: Reporting Module (`src/reporting/excel_generator.py`)
*   [x] **2.1:** Create `src/reporting/__init__.py`.
*   [x] **2.2:** Create `src/reporting/excel_generator.py`.
*   [x] **2.3:** Implement `generate_summary_report` function skeleton (accept args, get DB session, basic structure).
*   [x] **2.4:** Implement DB query logic within `generate_summary_report` using new CRUD functions. Handle 'no reviews found'.
*   [x] **2.5:** Implement data grouping by language.
*   [x] **2.6:** Implement LLM call logic for *per-language* summary (define prompt, call API, parse JSON).
    *   [ ] **Test:** Mock LLM call, verify prompt generation and handling of successful/failed JSON parsing.
*   [x] **2.7:** Implement Excel sheet writing for *per-language* summary and raw data.
*   [x] **2.8:** Implement LLM call logic for *overall* summary.
    *   [ ] **Test:** Mock LLM call, verify prompt and parsing.
*   [x] **2.9:** Implement Excel sheet writing for *overall* summary.
*   [x] **2.10:** Implement final Excel generation to `BytesIO` and return value.
*   [x] **2.11:** Add robust error handling (DB, LLM, Excel writing).
    *   [ ] **Test:** Integration test `generate_summary_report` with mocked DB/LLM errors.
    *   [x] **Test:** Integration test with live DB (local Docker) and mocked LLM.

### Phase 3: Streamlit Application (`streamlit_app.py`)
*   [x] **3.1:** Add `streamlit` and `gunicorn` to `requirements.txt`.
    *   [x] Run `pip install -r requirements.txt`.
*   [x] **3.2:** Create `src/frontend/app.py`.
*   [x] **3.3:** Implement basic Streamlit layout (title).
*   [x] **3.4:** Implement DB connection and fetching of tracked apps for dropdown.
    *   [ ] **Test:** Run `streamlit run src/frontend/app.py` locally, verify dropdown populates.
*   [x] **3.5:** Implement date input widget.
*   [x] **3.6:** Implement "Generate Report" button and basic click handler.
*   [x] **3.7:** Integrate `generate_summary_report` call within button handler (with spinner).
*   [x] **3.8:** Implement download button logic using returned bytes.
*   [x] **3.9:** Implement error display logic (`st.error`).
    *   [ ] **Test:** Manually test full flow locally: select app/date, click generate, verify download works, test error conditions (no reviews, LLM error from reporting module).

### Phase 4: Heroku Deployment Preparation
*   [x] **4.1:** Create/update `Procfile` with `web` (Streamlit) and `worker` (pipeline script) commands.
*   [x] **4.2:** Verify all dependencies are correctly listed in `requirements.txt`.
*   [x] **4.3 (Manual):** Add Heroku Git remote.
*   [x] **4.4 (Manual):** Provision Heroku app, Heroku Postgres add-on, and Heroku Scheduler add-on.
*   [x] **4.5 (Manual):** Set Heroku Config Vars (`DATABASE_URL` from add-on, `OPENAI_API_KEY`, etc.).
*   [x] **4.6 (Manual):** Configure Heroku Scheduler to run `python -m src.main_fetcher` (and potentially translator/analyzer separately or via `run_pipeline.sh`) on a schedule.
*   [ ] **4.7 (Deferred but Recommended):** Implement Alembic for DB migrations.
    *   [x] **1.3:** Create `runtime.txt` specifying Python version.
    *   [x] **1.4:** Initialize Alembic (`alembic init alembic`).
    *   [x] **1.5:** Configure `alembic.ini` (db url).
    *   [x] **1.6:** Configure `alembic/env.py` (import Base, set metadata).
    *   [x] **1.7:** Generate initial Alembic migration (`alembic revision --autogenerate`).
        *   [x] **Test:** Review generated migration script.
*   [x] **4.8 (Manual):** Deploy to Heroku (`git push heroku main`).
    *   [x] **Test:** Access the deployed Streamlit app, test report generation. Monitor Heroku logs for scheduler jobs and web app activity.

## Heroku Deployment Phase (V1)

### Phase 1: Code & Config Prep
*   [x] **1.1:** Add `alembic` to `requirements.txt` and install.
*   [x] **1.2:** Create `Procfile` for Heroku (`web`, `release`).
*   [x] **1.3:** Create `runtime.txt` specifying Python version.
*   [x] **1.4:** Initialize Alembic (`alembic init alembic`).
*   [x] **1.5:** Configure `alembic.ini` (db url).
*   [x] **1.6:** Configure `alembic/env.py` (import Base, set metadata).
*   [x] **1.7:** Generate initial Alembic migration (`alembic revision --autogenerate`).
    *   [x] **Test:** Review generated migration script.
*   [x] **1.8:** Apply migration locally (`alembic upgrade head`).
    *   [x] **Test:** Verify local DB schema matches models.

### Phase 2: Streamlit Enhancements
*   [x] **2.1:** Add CRUD function `get_app_last_update_time(db, app_id)`.
    *   [ ] **Test:** Unit test new CRUD function.
*   [x] **2.2:** Update `streamlit_app.py` to fetch and display "Data current as of..." time.
    *   [x] **Test:** Run Streamlit locally, verify time display.

### Phase 3: Backfilling Script
*   [x] **3.1:** Create `scripts/backfill_reviews.py` with `app_id` argument.
*   [x] **3.2:** Implement logic to fetch *all* reviews (no timestamp filter).
*   [x] **3.3:** Implement logic to insert fetched reviews using `add_reviews_bulk`.
*   [x] **3.4:** Add logging and rate limiting/sleep.
    *   [x] **Test:** Run backfill script locally against a test app ID with few reviews, verify DB insertion.

### Phase 4: Heroku Setup & Deployment (Manual Steps Required)
*   [x] **4.1 (Manual):** Create Heroku app.
*   [x] **4.2 (Manual):** Add Heroku Postgres addon.
*   [x] **4.3 (Manual):** Add Heroku Scheduler addon.
*   [x] **4.4 (Manual):** Set Heroku Config Vars (API Keys, ensure DATABASE_URL is correct).
*   [x] **4.5 (Manual):** Add Heroku Git remote.
*   [x] **4.6:** Commit all code changes to Git.
*   [x] **4.7 (Manual):** Push code to Heroku (`git push heroku main`).
*   [x] **4.8 (Manual):** Monitor build/release logs. Verify `alembic upgrade head` runs.
    *   [x] **Test:** Check Heroku Postgres schema matches models.

### Phase 5: Production Backfill & Scheduling (Manual Steps Required)
*   [x] **5.1 (Manual):** Look up Smite 2 App ID.
*   [x] **5.2 (Manual):** Run backfill script on Heroku for Dead Zone Rogue (`heroku run ...`).
*   [x] **5.3 (Manual):** Run backfill script on Heroku for Smite 2 (`heroku run ...`).
    *   [x] **Test:** Monitor backfill logs. Verify data populates Heroku DB.
*   [x] **5.4 (Manual):** Configure Heroku Scheduler job (`bash run_pipeline.sh` or similar, e.g., Hourly).
    *   [x] **Test:** Trigger scheduler job manually. Monitor logs. Verify DB updates (`last_fetched_timestamp`, new reviews, processing status changes).
*   [x] **5.5 (Manual):** Test deployed Streamlit app, including report generation.

## Future Phases (Post-Deployment)
- [ ] Explore Vector DB integration for semantic search/summarization
- [ ] Add admin interface for managing tracked apps
- [ ] Performance optimizations for reporting
- [ ] Add more sophisticated UI features
- [ ] Implement unit tests deferred from backend phase
- [ ] Comprehensive end-to-end testing with larger datasets

## Optimization Phase: Async Report Generation

*   [ ] **1.1:** Verify/Implement async support in `src.openai_client` (`aget_llm_summary`).
    *   [ ] **Test:** Add/Update unit tests for async OpenAI client method.
*   [ ] **1.2:** Refactor `src.reporting.excel_generator.generate_summary_report` to `async def`.
*   [ ] **1.3:** Implement gathering of async LLM call coroutines (per-language and overall).
*   [ ] **1.4:** Implement concurrent execution using `asyncio.gather` with `return_exceptions=True`.
*   [ ] **1.5:** Implement processing logic for `gather` results (handling exceptions and successful summaries).
    *   [ ] **Test:** Add unit tests for `generate_summary_report` mocking client and testing `gather` results handling.
*   [ ] **1.6:** Update `streamlit_app.py` button handler to use `asyncio.run()` to call the async report function.
*   [ ] **1.7 (Testing):** Perform integration tests locally (measuring time, verifying output, testing LLM error handling).
*   [ ] **1.8 (Testing):** Perform manual tests in Streamlit app locally (verify UI speed, output, error handling).
*   [ ] **1.9 (Deploy):** Deploy changes to Heroku.
*   [ ] **1.10 (Test):** Test functionality on deployed Heroku app. 