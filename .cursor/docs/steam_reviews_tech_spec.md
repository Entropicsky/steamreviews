# Steam Reviews Analysis Tool - Technical Specification

## 1. Overview

This tool will fetch, analyze, translate, and summarize Steam game reviews, with a particular focus on translating Chinese reviews to English using the OpenAI Responses API and gpt-4.1 model.

## 2. System Architecture

The system will follow a modular architecture with the following components:

### 2.1. Data Collection Module
- Responsible for fetching reviews from Steam's public API
- Will handle pagination, filtering, and rate limiting
- Parameters: game ID, language filter, review type (positive/negative), etc.
- Will use the provided SteamAPI class as a starting point

### 2.2. Translation Module
- Integrates with OpenAI's Responses API (rather than Chat Completions)
- Uses the newer gpt-4.1 model with larger context window
- Handles batch translations of reviews from Chinese to English
- Caches translations to prevent redundant API calls
- Takes advantage of the Responses API's enhanced capabilities

### 2.3. Analysis Module
- Uses gpt-4.1 to analyze and summarize review content
- Identifies common themes, sentiment, and trends
- Generates both high-level summaries and detailed analysis
- Leverages the large context window of gpt-4.1 for better analysis

### 2.4. User Interface
- Initially a simple command-line script for prototype testing
- Later evolves into either a Streamlit or Flask web application
- Allows specification of game ID, language preferences, and time ranges
- Exports data in both PDF and Excel formats

## 3. Development Approach

### 3.1. Prototype Phase
1. Create a simple script targeting app ID 3228590 specifically
2. Pull 200 Chinese reviews
3. Translate using OpenAI Responses API
4. Generate basic trend summaries
5. Test and validate the approach

### 3.2. Full Application Phase
1. Generalize the prototype into a modular application
2. Add UI layer (Streamlit or Flask)
3. Implement additional features (language selection, date ranges)
4. Add export options (PDF, Excel)
5. Implement caching and optimization

## 4. API Integrations

### 4.1. Steam API
- Will use public Steam Store API to fetch reviews
- Endpoint: https://store.steampowered.com/appreviews/{appid}
- Key parameters: json=1, language, filter, num_per_page, cursor
- Rate limiting considerations as per Steam's policies

### 4.2. OpenAI Responses API
- Uses new Responses API (not the older Chat Completions)
- Requires API key from .env file
- Uses gpt-4.1 model (OPENAI_MODEL environment variable)
- Takes advantage of enhanced context window for better analysis

## 5. Data Flow

1. User selects a game and review filtering parameters
2. System fetches reviews matching the criteria from Steam
3. Chinese reviews are sent to OpenAI for translation using Responses API
4. All reviews (original and translated) are analyzed using gpt-4.1
5. System generates summary reports and trend analysis
6. Results are presented to the user and available for export

## 6. Output Formats

- In-app display of reviews and summaries
- PDF export with formatted translations and analysis
- Excel export with raw data for further analysis
- Summary statistics and visualizations

## 7. Technical Requirements

- Python 3.8+
- OpenAI Python SDK (latest version for Responses API support)
- Requests for Steam API calls
- Streamlit or Flask for web UI (in full application phase)
- Pandas for data manipulation
- FPDF or similar for PDF generation
- OpenPyXL for Excel export capabilities
- Python-dotenv for environment variable management 