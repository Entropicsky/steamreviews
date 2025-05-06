# Development Notebook

## May 4, 2024

### Project Reset and Refocus
- Project approach has been reset to take a more methodical, step-by-step approach
- Focus shifted to using OpenAI's Responses API and the newer gpt-4.1 model
- Initial goal: Create a simple prototype script before building full application

### Research Notes
- OpenAI's Responses API replaces the older Chat Completions API
  - Documentation in `.cursor/docs/OAIResponsesAPI.md` and `.cursor/docs/openaidocs.md`
  - Offers improved capabilities over previous APIs
  - Requires slightly different implementation approach
- gpt-4.1 model offers larger context window compared to previous models
  - Will enable better analysis of large batches of reviews
  - Should provide higher quality translations
- Steam API access using format: `https://store.steampowered.com/appreviews/{appid}`
  - Can filter by language, review type, etc.
  - Need to handle pagination via cursor parameter
  - Requires rate limiting (1 second between requests recommended)

### Technical Considerations
- OpenAI configuration via environment variables:
  - OPENAI_API_KEY defined in .env file
  - OPENAI_MODEL="gpt-4.1" defined in .env file
- Starting with specific target:
  - App ID: 3228590
  - 200 Chinese reviews
  - Later will expand to configurable parameters
- Output formats to consider:
  - PDF report with translations and summaries
  - Excel export with raw data
  - Simple web UI (Streamlit or Flask)

### Development Plan
- Start with simple prototype script
  - Focus on core functionality (fetch, translate, summarize)
  - No UI for initial prototype
- Use the prototype to validate approach and identify challenges
- Refine into modular application with proper architecture
- Add UI and export functionality

### Next Steps
- Implement prototype script using provided Steam API example code
- Set up OpenAI client with Responses API
- Test translation capabilities with batch processing
- Develop summary prompts for gpt-4.1 model
- Validate approach before proceeding to full application

## Supadata API Findings (YouTube Feedback Feature)

*   **Channel Identifier:** The `/youtube/channel/videos` endpoint requires the channel **handle** (e.g., `@Weak3n`) passed in the `id` parameter, *not* the standard `UC...` channel ID. Using the `UC...` ID resulted in a `502 Bad Gateway` error with the message `{"error":"youtube-api-error","message":"An error occurred with the YouTube API","details":"This channel does not exist."}`.
*   **URL Construction:** The base URL provided in Supadata docs (`https://api.supadata.ai/v1/youtube`) already includes the `/youtube` path segment. Endpoint paths used with this base URL (e.g., for channel videos, video metadata, transcripts) should *not* also start with `/youtube`, otherwise it leads to duplicated paths (e.g., `/youtube/youtube/channel/videos`) and `404 Not Found` errors.
*   **Transcript Fetching:** The client code currently requests transcripts using `format: "text"`. Need to verify the exact response structure from Supadata for the `/youtube/transcript` endpoint (e.g., what key contains the text) when we successfully fetch one.

## General Notes
*   Using OpenAI Responses API (`messages` parameter) and requesting JSON output via `response_format={'type': 'json_object'}`.
*   Database seeding script (`seed_youtube_test_data.py`) created for testing.
*   Direct API test script (`test_supadata_api.py`) created for debugging. 