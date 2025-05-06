# YouTube Feedback Analysis - Technical Specification

## 1. Overview

This feature extends the existing Steam Review Analysis tool to incorporate feedback from YouTube videos related to specific games. It will monitor designated YouTube influencer channels, fetch video transcripts using the Supadata API, analyze the content for game relevance and structured feedback using OpenAI, store the results, and provide reporting/viewing capabilities through the existing Streamlit application and Slack notifications.

## 2. System Architecture & Components

The feature will integrate into the existing project structure, reusing components where possible and adding new ones specifically for YouTube data processing.

### 2.1. New Modules (`src/youtube/`)

*   **`supadata_client.py`**:
    *   Handles all interactions with the Supadata YouTube API (`https://api.supadata.ai/v1/youtube/...`).
    *   Uses the `SUPADATA_API_KEY` environment variable.
    *   Methods:
        *   `get_channel_videos(channel_id, limit, type)`: Fetches recent video IDs for a channel (Supadata endpoint: `/channel/videos`).
        *   `get_video_metadata(video_id)`: Fetches metadata for a single video (Supadata endpoint: `/video`). Used to get upload date, title, description etc.
        *   `get_transcript(video_id, lang, text)`: Fetches video transcript (Supadata endpoint: `/transcript`). Prioritize fetching English (`en`) text transcripts.
    *   Handles API authentication, request formatting, response parsing, basic error handling (rate limits, timeouts, API errors), and logging.
    *   Leverages the `requests` library.
*   **`analyzer.py`**:
    *   Responsible for interacting with the OpenAI API (using the **Responses API** via the existing `src.openai_client` if suitable, or a dedicated client).
    *   Uses `OPENAI_API_KEY`.
    *   Methods:
        *   `analyze_video_transcript(transcript_text, game_name)`:
            1.  **Relevance Check:** Determines if the transcript is relevant to the specified `game_name`. Returns a boolean flag/score.
            2.  **Summarization:** If relevant, generates a concise summary tailored for game developers.
            3.  **Structured Feedback Extraction:** Extracts predefined categories of feedback into a structured JSON format (similar to Steam reviews but with YouTube-specific categories).
    *   Defines Pydantic models for the structured JSON output schema.
    *   Handles prompt engineering for relevance, summary, and extraction. Manages API calls, response parsing, error handling, and logging.
*   **`models.py` / `schemas.py`**: (Optional, could integrate into `src/database/models.py` or keep separate)
    *   Pydantic models for API responses (Supadata) and LLM analysis results if needed beyond DB models.

### 2.2. Database (`src/database/`)

*   **`models.py`**:
    *   Extend with new SQLAlchemy models:
        *   `Game`: (May reuse/adapt existing `TrackedApp` if structure permits, or create new. Needs `id`, `name`).
        *   `Influencer`: (`id`, `name`, `notes`).
        *   `YouTubeChannel`: (`id` (Supadata channel ID), `influencer_id` (FK), `channel_name`, `handle`, `last_checked_timestamp`).
        *   `GameInfluencerMapping`: (`game_id` (FK), `influencer_id` (FK), `is_active`). (Primary key on `game_id, influencer_id`).
        *   `YouTubeVideo`: (`id` (Supadata video ID), `channel_id` (FK), `title`, `description`, `upload_date` (Timestamp), `duration`, `transcript_status` ('pending', 'fetched', 'failed', 'unavailable'), `analysis_status` ('pending', 'analyzed', 'irrelevant', 'failed')).
        *   `VideoTranscript`: (`video_id` (FK, PK), `language` (PK), `transcript_text`).
        *   `VideoFeedbackAnalysis`: (`video_id` (FK, PK), `llm_analysis_model`, `llm_analysis_timestamp`, `summary`, `is_relevant` (boolean), `analyzed_sentiment`, `positive_themes` (ARRAY[TEXT]), `negative_themes` (ARRAY[TEXT]), `bug_reports` (ARRAY[TEXT]), `feature_requests` (ARRAY[TEXT]), `balance_feedback` (ARRAY[TEXT]), `gameplay_loop_feedback` (ARRAY[TEXT]), `monetization_feedback` (ARRAY[TEXT])). Mirroring structure of `Review` analysis columns where applicable.
*   **`crud_youtube.py`**:
    *   Implement CRUD helper functions for the new models (e.g., `get_active_game_influencer_mappings`, `get_channel_by_id`, `update_channel_timestamp`, `add_video`, `get_videos_pending_analysis`, `add_transcript`, `add_feedback_analysis`, etc.).
*   **`connection.py`**: No changes expected, reuse existing DB connection setup.
*   **`alembic/`**: New migration script(s) needed to create the tables.

### 2.3. Scripts (`scripts/`)

*   **`youtube_fetcher.py`**:
    *   Scheduled job (via Heroku Scheduler).
    *   Gets active `GameInfluencerMapping` entries.
    *   For each associated `YouTubeChannel`, fetches new videos since `last_checked_timestamp` using `supadata_client.get_channel_videos` and `supadata_client.get_video_metadata`.
    *   For each new video:
        *   Stores basic video metadata (`YouTubeVideo` entry) with `transcript_status='pending'`, `analysis_status='pending'`.
        *   Attempts to fetch the English transcript using `supadata_client.get_transcript`.
        *   Stores transcript text in `VideoTranscript` and updates `YouTubeVideo.transcript_status` ('fetched', 'failed', 'unavailable').
    *   Updates `YouTubeChannel.last_checked_timestamp`.
    *   Handles errors gracefully and logs activity.
*   **`youtube_analyzer_worker.py`**:
    *   Scheduled job (or could be integrated into `youtube_fetcher.py` after transcript fetch).
    *   Queries for `YouTubeVideo` entries with `transcript_status='fetched'` and `analysis_status='pending'`.
    *   For each video:
        *   Retrieves transcript text from `VideoTranscript`.
        *   Calls `src.youtube.analyzer.analyze_video_transcript`, passing transcript and game name (from mapping).
        *   Parses the structured response.
        *   Stores results in `VideoFeedbackAnalysis`.
        *   Updates `YouTubeVideo.analysis_status` ('analyzed', 'irrelevant', 'failed').
    *   Handles errors, logs activity.
*   **`youtube_slack_reporter.py`**:
    *   Scheduled job (e.g., weekly per game).
    *   Accepts `game_id` and time period (e.g., 'last_week') as arguments.
    *   Queries `VideoFeedbackAnalysis` for the specified game/period.
    *   Generates a summary message (e.g., counts, key themes/summaries from analysis).
    *   Uses the existing Slack integration mechanism (`src/slack_client.py`? - Needs verification) to post the summary to the appropriate channel (requires mapping games to Slack channels, perhaps add `slack_channel_id` to `Game` table).
    *   Uses `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` (or fetched per game).

### 2.4. Frontend (`pages/`)

*   **`youtube_feedback.py`**:
    *   New Streamlit page.
    *   **Management Tab:**
        *   UI to view/add/edit `Games`.
        *   UI to view/add/edit `Influencers`.
        *   UI to manage `GameInfluencerMapping` (e.g., multi-select or table to link influencers to games).
        *   Uses `crud.py` and `crud_youtube.py` functions.
    *   **Feedback Viewer Tab:**
        *   Dropdown to select `Game`.
        *   Date range selector.
        *   Button to fetch and display analyzed feedback (`VideoFeedbackAnalysis` joined with `YouTubeVideo` and `YouTubeChannel`) for the selected game/period. Display in a table or using `st.expander` per video.
        *   Download button (Excel/CSV) for the displayed data.

## 3. Data Flow & Workflow

1.  **Manual Setup:** User adds Games, Influencers, and maps them via the Streamlit UI. Includes adding the YouTube Channel ID/URL for each influencer.
2.  **Scheduled Fetch (`youtube_fetcher.py`):**
    *   Runs periodically (e.g., hourly).
    *   Identifies channels to check based on active mappings.
    *   Calls Supadata API to find new videos since the channel's `last_checked_timestamp`.
    *   Calls Supadata API to get metadata for new videos. Stores metadata in `YouTubeVideo`.
    *   Calls Supadata API to get transcript for new videos. Stores text in `VideoTranscript`, updates status.
    *   Updates `last_checked_timestamp` for the channel.
3.  **Scheduled Analysis (`youtube_analyzer_worker.py`):**
    *   Runs periodically (e.g., hourly, shortly after fetcher).
    *   Finds videos needing analysis (`analysis_status='pending'`, `transcript_status='fetched'`).
    *   Calls OpenAI API via `analyzer.py` for relevance, summary, structured feedback.
    *   Stores analysis results in `VideoFeedbackAnalysis`, updates status.
4.  **Scheduled Reporting (`youtube_slack_reporter.py`):**
    *   Runs periodically (e.g., daily/weekly).
    *   Queries analyzed data for a specific game/period.
    *   Formats summary and posts to Slack.
5.  **User Interaction (Streamlit):**
    *   User manages games/influencers/mappings.
    *   User selects game/date range and views/downloads analyzed feedback.

## 4. API Integrations

*   **Supadata API:**
    *   Base URL: `https://api.supadata.ai/v1`
    *   Authentication: `x-api-key` header (from `SUPADATA_API_KEY` env var).
    *   Endpoints: `/youtube/channel/videos`, `/youtube/video`, `/youtube/transcript`.
    *   Consider rate limits and potential need for delays between requests.
*   **OpenAI API:**
    *   Use existing client setup if possible.
    *   Use **Responses API** with appropriate model (e.g., `gpt-4o` or `gpt-4-turbo`).
    *   Authentication: `OPENAI_API_KEY` env var.
*   **Slack API:**
    *   Use existing client/method for sending messages.
    *   Authentication: `SLACK_BOT_TOKEN` env var.
    *   Needs target `SLACK_CHANNEL_ID` (per game or default).

## 5. Deployment (Heroku)

*   **Dependencies:** Add any new Python libraries (e.g., `requests` if not already present, potentially `supadata-python` SDK if chosen over direct requests) to `requirements.txt`.
*   **Environment Variables:** Ensure `SUPADATA_API_KEY` is added to Heroku Config Vars. Verify `OPENAI_API_KEY`, `SLACK_BOT_TOKEN`, `DATABASE_URL` are present. Add per-game `SLACK_CHANNEL_ID`s if needed (or handle via DB).
*   **Database Migrations:**
    *   Generate migration script(s) using `alembic revision --autogenerate -m "Add YouTube feedback tables"`.
    *   Apply migrations **manually** after deployment using `heroku run alembic upgrade head`. The `release` phase in `heroku.yml` will **not** run migrations automatically.
*   **Processes (`heroku.yml` / Scheduler):**
    *   The `web` process remains unchanged (runs Streamlit).
    *   Use Heroku Scheduler (add-on) to run the new scripts:
        *   `python -m scripts.youtube_fetcher` (e.g., hourly)
        *   `python -m scripts.youtube_analyzer_worker` (e.g., hourly, offset from fetcher)
        *   `python -m scripts.youtube_slack_reporter --game-id <ID> --period last_week` (e.g., weekly per game)

## 6. Testing Strategy

*   **Unit Tests:** Test individual functions in `supadata_client.py`, `analyzer.py`, `crud_youtube.py` using mocking (e.g., `unittest.mock`).
*   **Integration Tests:** Test interactions between components (e.g., fetcher calling client and DB, analyzer calling OpenAI and DB). Test against a local Docker PostgreSQL instance.
*   **Streamlit Tests:** Use `streamlit.testing` if feasible for UI component checks. Manual testing for UI workflows.
*   **End-to-End Tests:** Simulate cron job runs locally, verify data flow through DB stages, check Slack output (mocked). Test full UI flow locally. Manual testing on Heroku staging/production.

## 7. Open Questions & Considerations

*   **Supadata API Limits/Costs:** Understand credit usage per endpoint. Implement delays if needed.
*   **LLM Prompt Refinement:** Iteratively improve prompts for relevance, summary, and feedback extraction quality.
*   **Error Handling:** Robust handling for API errors (Supadata, OpenAI, Slack), DB issues, unexpected data formats.
*   **Scalability:** Consider potential bottlenecks if tracking many influencers/channels (API limits, DB load, processing time). Async processing for API calls might be beneficial later.
*   **Schema Evolution:** How to handle changes to feedback categories extracted by the LLM?
*   **Data Backfilling:** Need a strategy/script if historical video analysis is required.
*   **Steam `TrackedApp` vs. `Game`:** Decide whether to merge/adapt the existing `TrackedApp` table or create a new `Game` table and potentially link them. Creating a new `Game` table might be cleaner separation.
*   **Slack Channel Mapping:** How to configure the target Slack channel per game for reports? (DB field, env var mapping?). A `slack_channel_id` field in the `Game` table seems most flexible. 