# src/youtube/analyzer.py
import os
import json
import logging
import re
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator

# Attempt to import the actual client, handle potential ImportError if structure changes
try:
    from src.openai_client import call_openai_api, OPENAI_MODEL
except ImportError:
    logging.error("Could not import call_openai_api from src.openai_client. Ensure it exists and check Python path.")
    # Define a dummy function to allow script to load but fail at runtime
    def call_openai_api(*args, **kwargs):
        raise NotImplementedError("OpenAI client function not found.")
    OPENAI_MODEL = "gpt-4o" # Default fallback

logger = logging.getLogger(__name__)

# --- Pydantic Model for Structured Output ---
# Mirroring ReviewAnalysis structure where applicable
class YouTubeFeedbackAnalysisResult(BaseModel):
    is_relevant: bool = Field(..., description="True if the video is significantly about the specified game.")
    summary: Optional[str] = Field(None, description="Concise developer-focused summary if relevant, otherwise null.")
    analyzed_sentiment: Optional[str] = Field(None, description="Overall sentiment (e.g., Positive, Negative, Mixed, Neutral) if relevant.")
    positive_themes: Optional[list[str]] = Field(None, description="List of positive themes/keywords mentioned if relevant.")
    negative_themes: Optional[list[str]] = Field(None, description="List of negative themes/keywords mentioned if relevant.")
    bug_reports: Optional[list[str]] = Field(None, description="List of specific bug reports mentioned if relevant.")
    feature_requests: Optional[list[str]] = Field(None, description="List of specific feature requests mentioned if relevant.")
    balance_feedback: Optional[list[str]] = Field(None, description="List of specific feedback points about game balance if relevant.")
    gameplay_loop_feedback: Optional[list[str]] = Field(None, description="List of specific feedback points about the core gameplay loop if relevant.")
    monetization_feedback: Optional[list[str]] = Field(None, description="List of specific feedback points about monetization if relevant.")

    @field_validator('summary', 'analyzed_sentiment', 'positive_themes', 'negative_themes', 'bug_reports', 'feature_requests', 'balance_feedback', 'gameplay_loop_feedback', 'monetization_feedback', mode='before')
    @classmethod
    def set_none_if_not_relevant(cls, v, info: Any):
        # Access other field data via info.data
        if 'is_relevant' in info.data and not info.data['is_relevant']:
            return None
        return v

# --- Analyzer Class ---

class YouTubeFeedbackAnalyzer:
    def __init__(self, api_key: Optional[str] = None, model: str = OPENAI_MODEL):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        if not self.api_key:
            logger.warning("OpenAI API key not found in environment variables (OPENAI_API_KEY).")
            # Raise an error or handle as appropriate - for now, log a warning
            # raise ValueError("OpenAI API key is required.")

    def analyze_video_transcript(self, transcript_text: str, game_name: str) -> Optional[Dict[str, Any]]:
        """Analyzes a transcript for relevance and extracts structured feedback using OpenAI."""
        if not self.api_key:
            logger.error("Cannot analyze transcript: OpenAI API key is missing.")
            return None
        if not transcript_text:
            logger.warning("Cannot analyze empty transcript.")
            # Return a specific structure indicating no analysis possible?
            # For now, return None, but the caller should handle this.
            # Or perhaps return {'is_relevant': False}? Decided None for now.
            return None

        # Limit transcript length to avoid excessive token usage (simple truncation for now)
        # TODO: Implement smarter chunking or summarization for very long transcripts
        MAX_TRANSCRIPT_CHARS = 20000 # Example limit, adjust based on model/cost
        truncated_transcript = transcript_text[:MAX_TRANSCRIPT_CHARS]
        if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
            logger.warning(f"Transcript for analysis truncated to {MAX_TRANSCRIPT_CHARS} chars.")

        # Define the prompt content for the user message
        prompt_content = (
            f"""Analyze the following YouTube video transcript text specifically regarding the game '{game_name}'.
Determine if the video is primarily about or contains significant discussion of '{game_name}'.

If it IS relevant to '{game_name}', provide:
1.  A **detailed, structured summary** using markdown sections (e.g., `### Section Title`) and bullet points (`*` or `-`). This summary should **only** include content relevant to game developers, such as:
    *   Key feedback points (positive and negative)
    *   Balance discussions (items, characters, mechanics)
    *   Bugs or technical issues mentioned
    *   Feature requests or suggestions
    *   Player experience comments (UI, onboarding, progression)
    *   Monetization feedback
    *   Exclude video intros, outros, sponsor messages, unrelated chatter, and calls to action (like/subscribe).
2.  An overall sentiment score (e.g., Positive, Negative, Mixed, Neutral).
3.  A list of positive themes mentioned (e.g., "Fun gameplay", "Good graphics").
4.  A list of negative themes mentioned (e.g., "Server issues", "Confusing UI", "Balance problems").
5.  Specific bug reports mentioned.
6.  Specific feature requests mentioned.
7.  Specific feedback on game balance.
8.  Specific feedback on the core gameplay loop.
9.  Specific feedback on monetization aspects (if any).

If the video is NOT relevant to '{game_name}' (e.g., different game, general channel update, unrelated topic), only state that it is not relevant by setting `is_relevant` to false.

Format the entire response STRICTLY as a JSON object matching the following Pydantic model:
```json
{json.dumps(YouTubeFeedbackAnalysisResult.model_json_schema(), indent=2)}
```
Ensure the output is ONLY the JSON object, with no surrounding text or markdown formatting.

Transcript Text:
---
{truncated_transcript}
---

JSON Response:
"""
        )

        # Prepare messages for OpenAI Responses API
        messages = [
            {"role": "system", "content": "You are an AI assistant analyzing YouTube video transcripts for game feedback. Respond ONLY with the JSON structure requested based on the provided Pydantic schema."},
            {"role": "user", "content": prompt_content}
        ]

        # Define API call parameters
        # Max output tokens might need adjustment based on expected JSON size
        api_params = {
            "messages": messages, # Use 'messages' for Responses API
            "model": self.model,
            "max_tokens": 2048, # Max output tokens
            "temperature": 0.2, # Lower temperature for more deterministic JSON output
            # "response_format": {"type": "json_object"} # THIS IS NOT SUPPORTED BY THE RESPONSES API in current library
        }

        try:
            logger.debug(f"Sending request to OpenAI API for analysis (Model: {self.model})...")
            raw_response_content = call_openai_api(**api_params)

            if not raw_response_content:
                logger.error("Received empty response from OpenAI API.")
                return None

            if raw_response_content == "[REFUSAL: CONTENT_FILTERING]":
                logger.warning("OpenAI request refused due to content filtering.")
                # Decide how to handle refusal - maybe mark as failed analysis?
                # Returning None for now, DB status will be updated by caller.
                return None

            # Attempt to parse the JSON response
            try:
                # The response *should* be just the JSON object due to response_format
                analysis_data = json.loads(raw_response_content)
                logger.debug("Successfully parsed JSON response from OpenAI.")

                # Validate with Pydantic
                try:
                    validated_analysis = YouTubeFeedbackAnalysisResult(**analysis_data)
                    logger.info("Analysis validation successful.")
                    return validated_analysis.model_dump() # Return as dict
                except Exception as pydantic_error:
                    logger.error(f"Pydantic validation failed for OpenAI response: {pydantic_error}", exc_info=True)
                    logger.error(f"Invalid data received: {analysis_data}")
                    return None # Or handle error more specifically

            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON response from OpenAI: {raw_response_content}", exc_info=True)
                return None
            except Exception as e:
                logger.error(f"Unexpected error processing OpenAI response: {e}", exc_info=True)
                return None

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}", exc_info=True)
            return None

# --- Main Execution Block (for testing) ---

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s')
    load_dotenv()

    # Example Usage (replace with actual transcript)
    # Make sure OPENAI_API_KEY is set in your .env file or environment
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("CRITICAL: OPENAI_API_KEY environment variable not set. Exiting.")
    else:
        analyzer = YouTubeFeedbackAnalyzer()
        # Example transcript (shortened)
        example_transcript = """
        Welcome back everyone! Today we're diving deep into SMITE 2. The gameplay feels really smooth, much better than the original. 
        However, I've been experiencing some weird server lag, especially during team fights. 
        The new god, Hecate, seems a bit overpowered right now, maybe needs a slight nerf to her scaling? 
        Also, the item shop UI is a bit confusing to navigate compared to the old one. 
        It would be great if they added a practice mode for the new map features. 
        Overall, a solid improvement, but needs some polish. What do you guys think?
        """
        game = "SMITE 2"
        
        logger.info(f"Analyzing example transcript for game: {game}")
        analysis_result = analyzer.analyze_video_transcript(example_transcript, game)

        if analysis_result:
            logger.info("Analysis Result:")
            print(json.dumps(analysis_result, indent=2))
        else:
            logger.error("Analysis failed.") 