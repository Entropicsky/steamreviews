# Agent Notes

## Project: Steam Reviews Analysis Tool

### Project Overview
This tool will analyze Steam reviews for games, with a special focus on translating Chinese reviews to English using the OpenAI Responses API and gpt-4.1 model.

### Project Status
- Project reset for methodical approach
- Documentation and planning updated
- Prototype script development in progress

### Development Approach
- Two-phase development:
  1. Simple prototype script focused on specific app ID (3228590)
  2. Full application with UI and expanded features
- Starting with command-line prototype to validate core functionality
- Using provided Steam API code as starting point

### Documentation Structure
- Project checklist: `.cursor/notes/project_checklist.md`
- Development notebook: `.cursor/notes/notebook.md`
- Technical specification: `.cursor/docs/steam_reviews_tech_spec.md`
- API documentation: `.cursor/docs/OAIResponsesAPI.md` and `.cursor/docs/openaidocs.md`

### Project Dependencies
- OpenAI Python SDK (latest version for Responses API support)
- Python dotenv for environment variables
- Requests for API calls
- JSON/CSV processing
- Later: Streamlit or Flask, PDF/Excel generation libraries

### User Preferences
- Focus on Chinese to English translation of reviews
- Initial focus on app ID 3228590
- Later enable configuration for different games and parameters
- Output in readable format, eventually PDF and Excel options

### Important Technical Notes
- Using OpenAI's Responses API (not the older Chat Completions API)
- Using gpt-4.1 model with larger context window
- Configure via environment variables (OPENAI_API_KEY, OPENAI_MODEL="gpt-4.1")
- Steam API pagination handled via cursor parameter
- Need to implement proper rate limiting

### Important Reminders
- Check documentation regularly
- Update project checklist as progress is made
- Document technical decisions in the notebook
- Maintain modular approach for easy extension

## Key Learnings & Preferences
*   **User:** Stewart Chisam (Slack ID U03DTH4NY)
*   **OpenAI API:** MUST use the **Responses API** format (`messages: [...]`) for chat/instruction-based tasks, not older APIs. Use `response_format={'type': 'json_object'}` when JSON output is required.
*   **Supadata API:** Requires the **channel handle** (e.g., `@Weak3n`) instead of the `UC...` channel ID for the `/youtube/channel/videos` endpoint. Watch out for URL construction - base URL ends in `/youtube`, so endpoint paths should *not* start with `/youtube`.
*   **Code Structure:** Follow existing patterns (database/crud, processing services, scripts, frontend pages). Keep functions and files focused (SRP).
*   **Error Handling:** Implement robust error handling, especially around API calls and database transactions.
*   **Dependencies:** Use `requirements.txt` and `.env` for managing dependencies and environment variables.
*   **Testing:** Create test scripts (like `scripts/test_supadata_api.py`) for isolated testing. Aim for unit/integration tests eventually.
*   **Documentation:** Maintain this file, `notebook.md`, and `project_checklist.md`.

## Current Focus: YouTube Feedback Feature
*   **Status:** Backend components (DB, Supadata Client, Fetcher, Analyzer, Worker) are implemented.
*   **Blocker:** End-to-end testing was interrupted. The `last_checked_timestamp` for the test channel (`@Weak3n`) is currently set such that the fetcher skips all recent videos. Need to re-run the fetcher to completion OR manually reset the timestamp to allow fetching/processing of new videos.
*   **Next Steps (Backend):**
    1. Resolve timestamp issue (re-run fetcher or reset DB timestamp).
    2. Run fetcher (`scripts/youtube_fetcher.py`) to add videos/transcripts.
    3. Run analyzer (`scripts/youtube_analyzer_worker.py`) to process them.
    4. Verify results in the database.
*   **Pointers:**
    *   Tech Spec: `.cursor/notes/youtube_feedback_tech_spec.md`
    *   Checklist: `.cursor/notes/project_checklist.md`
    *   DB Models/CRUD: `src/database/models.py`, `src/database/crud_youtube.py`
    *   Supadata Client: `src/youtube/supadata_client.py`
    *   Analyzer: `src/youtube/analyzer.py`
    *   Scripts: `scripts/youtube_fetcher.py`, `scripts/youtube_analyzer_worker.py`, `scripts/seed_youtube_test_data.py`, `scripts/test_supadata_api.py`

## General Project Structure
*   `src/`: Main source code
    *   `database/`: SQLAlchemy models, connection, CRUD operations
    *   `frontend/`: Streamlit application code (currently `app.py` for Steam)
    *   `pages/`: Additional Streamlit pages (e.g., planned `youtube_feedback.py`)
    *   `processing/`: Data processing modules (translation, analysis for Steam)
    *   `reporting/`: Report generation (e.g., Excel for Steam)
    *   `steam/`: Steam-specific client code
    *   `youtube/`: YouTube-specific client and analyzer code
    *   `utils/`: Utility functions
    *   `openai_client.py`: Client for OpenAI API
*   `scripts/`: Standalone scripts for pipeline tasks, seeding, testing
*   `tests/`: (Should contain unit/integration tests)
*   `.cursor/`: Agent notes, documentation, tools
*   `.env`: Environment variables (needs `DATABASE_URL`, `OPENAI_API_KEY`, `SUPADATA_API_KEY`, etc.)
*   `requirements.txt`: Python dependencies
*   `Procfile`, `runtime.txt`, `heroku.yml`: For Heroku deployment
*   `alembic/`, `alembic.ini`: For database migrations 