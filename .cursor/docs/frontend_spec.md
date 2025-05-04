# Steam Review Analysis System - Frontend & Reporting Spec V1

## 1. Overview

This document describes the initial version (V1) of the web frontend and reporting system for the Steam Review Analysis application. The goal is to provide a simple interface for users to select a tracked game, specify a date range (start date), and download a multi-sheet Excel report summarizing the reviews processed by the backend data pipeline.

This V1 focuses on on-demand report generation based on data already present in the PostgreSQL database, assuming the backend pipeline (`main_fetcher`, `run_translator`, `run_analyzer`) runs periodically via a scheduler (e.g., cron) to keep the database reasonably up-to-date.

## 2. Architecture & Technology

*   **Web Framework:** Streamlit
*   **Core Logic:** Python
*   **Data Source:** PostgreSQL database (via SQLAlchemy ORM defined in `src/database`)
*   **Reporting Library:** Pandas, OpenPyXL
*   **Deployment Target:** Heroku

```mermaid
graph TD
    U[User Browser] --> S[Streamlit App (streamlit_app.py)];
    S -- Selects App/Date --> S;
    S -- Clicks Generate --> RG[Reporting Module (src/reporting/excel_generator.py)];
    RG -- Gets Tracked App Names --> DB{PostgreSQL DB};
    RG -- Gets Reviews Since Date --> DB;
    RG -- Gets Distinct Languages --> DB;
    DB -- Returns Data --> RG;
    RG -- Groups Data by Language --> RG;
    RG -- Sends Summary Request (Per Lang) --> OAI[OpenAI API Client (Analyze)];
    OAI -- Returns Structured Summary --> RG;
    RG -- Sends Summary Request (Overall) --> OAI;
    OAI -- Returns Structured Summary --> RG;
    RG -- Formats Excel Data (Bytes) --> S;
    S -- Provides Download Link --> U;

    style DB fill:#f9f,stroke:#333,stroke-width:2px
    style OAI fill:#cfc,stroke:#333,stroke-width:1px

```

## 3. Components

### 3.1. Streamlit Application (`streamlit_app.py`)

*   **Location:** Project root directory.
*   **Functionality:**
    *   Displays a title.
    *   Connects to the database using `src/database/connection.py`.
    *   Fetches the list of tracked applications (`app_id`, `name`) from the `tracked_apps` table using `src/database/crud.py`.
    *   Presents a dropdown (`st.selectbox`) allowing the user to select a game by name (mapping to `app_id`).
    *   Presents a date input (`st.date_input`) for the user to select the "Reviews since" date.
    *   Displays a button (`st.button`) labeled "Generate & Download Report".
    *   When the button is clicked:
        *   Validates that an app and date are selected.
        *   Displays a spinner (`st.spinner`) to indicate processing.
        *   Converts the selected date to a Unix timestamp (start of day, UTC).
        *   Calls the `generate_summary_report` function from the Reporting Module, passing the selected `app_id` and `start_timestamp`.
        *   Handles potential errors returned from the reporting function (e.g., database errors, no reviews found, LLM errors) and displays an appropriate message (`st.error`).
        *   If successful, receives the generated Excel file as bytes.
        *   Uses `st.download_button` to offer the bytes for download, providing a descriptive filename (e.g., `SteamAnalysis_AppName_Since_YYYY-MM-DD.xlsx`).

### 3.2. Reporting Module (`src/reporting/excel_generator.py`)

*   **Location:** `src/reporting/` directory (new).
*   **Main Function:** `generate_summary_report(app_id: int, start_timestamp: int) -> bytes`.
*   **Functionality:**
    1.  **Database Query:** Gets a database session. Uses new CRUD functions (`get_reviews_for_app_since`, `get_distinct_languages_for_app_since`) to fetch all relevant `Review` objects (including translations and structured analysis columns) from the database for the given `app_id` and `start_timestamp`.
    2.  **Data Preparation:** If reviews are found, converts the list of `Review` objects into a Pandas DataFrame.
    3.  **Excel Initialization:** Creates an in-memory Excel workbook using `io.BytesIO` and `pd.ExcelWriter`.
    4.  **Per-Language Processing:**
        *   Loops through each distinct `original_language` found in the fetched reviews.
        *   Filters the DataFrame for the current language.
        *   **LLM Summary (Per-Language):** Prepares the input text (concatenated `english_translation` or `original_review_text` for English) for the filtered reviews. Calls `call_openai_api` (from `src/openai_client.py`) with a focused prompt requesting a structured JSON summary (sentiment, themes, etc., similar to `ReviewAnalysisResult` but summarizing the *batch*) for *this specific language subset*. Parses and validates the JSON response.
        *   **Excel Sheet Creation (Per-Language):**
            *   Creates a `Summary_{language_code}` sheet.
            *   Calculates basic stats (counts, %) for this language subset and writes them to the sheet.
            *   Writes the structured LLM summary (parsed from JSON) below the stats.
            *   Creates a `Reviews_{language_code}` sheet.
            *   Writes the filtered raw review DataFrame (selected columns, potentially formatted) to this sheet.
    5.  **Overall Summary Processing:**
        *   **LLM Summary (Overall):** Prepares input text using *all* fetched reviews for the period. Calls `call_openai_api` to get a structured JSON summary for the overall dataset.
        *   **Excel Sheet Creation (Overall):**
            *   Creates a `Summary_Overall` sheet.
            *   Calculates overall stats (counts, %) and writes them.
            *   Writes the overall structured LLM summary below the stats.
    6.  **Finalization:** Saves the `ExcelWriter` content to the `BytesIO` buffer.
    7.  **Return:** Returns the `bytes` content of the Excel file.
*   **Error Handling:** Includes `try...except` blocks for database queries, LLM calls, and Excel writing.

### 3.3. Database CRUD Additions (`src/database/crud.py`)

*   Add function `get_reviews_for_app_since(db: Session, app_id: int, start_timestamp: int) -> List[models.Review]`: Filters `reviews` table by `app_id` and `timestamp_created >= start_timestamp`.
*   Add function `get_distinct_languages_for_app_since(db: Session, app_id: int, start_timestamp: int) -> List[str]`: Gets distinct `original_language` values matching the app/time criteria.
*   Potentially modify `get_active_tracked_apps` to also return the app `name` for the dropdown.

### 3.4. LLM Integration (Summarization)

*   Requires new focused prompts for summarizing a *batch* of reviews (per-language and overall) into the structured JSON format (similar to `ReviewAnalysisResult` schema).
*   These calls will happen on-demand within the `generate_summary_report` function.

## 4. Deployment (Heroku)

*   **`Procfile`:**
    *   `web: streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0`
    *   `worker: ./run_pipeline.sh` (or use Heroku Scheduler add-on to trigger fetch/translate/analyze periodically, which is generally preferred over a continuously running worker dyno for scheduled tasks).
*   **`requirements.txt`:** Ensure `streamlit`, `gunicorn` are added.
*   **Environment Variables:** Ensure `DATABASE_URL` (provided by Heroku Postgres add-on), `OPENAI_API_KEY`, etc., are configured as Heroku Config Vars.
*   **Database Migrations:** Plan to introduce Alembic before deploying significant schema changes after the initial setup.

## 5. Testing Strategy

*   **CRUD Functions:** Unit test new DB query functions.
*   **Reporting Module:** Unit test helper functions (e.g., data formatting). Integration test `generate_summary_report` by connecting to the test DB (Docker), mocking LLM calls initially, then potentially doing limited live LLM calls.
*   **Streamlit App:** Manual testing locally (`streamlit run streamlit_app.py`). Test UI elements, date handling, button clicks, error display, and successful download generation.
*   **End-to-End (Local):** Run the backend pipeline (`run_pipeline.sh`), then run the Streamlit app locally to generate a report against the populated local DB. 