import logging
import json
from typing import Dict, Any, Optional, List

# Adjust path to import from sibling directories
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from pydantic import BaseModel, Field, ValidationError
from openai_client import call_openai_api, OPENAI_MODEL

logger = logging.getLogger(__name__)

# --- Pydantic Model for Structured Analysis --- 
# (Mirrors DB columns for analysis)
class ReviewAnalysisResult(BaseModel):
    analyzed_sentiment: Optional[str] = Field(None, description="Sentiment derived from LLM analysis ('Positive', 'Negative', 'Mixed', 'Neutral')")
    positive_themes: Optional[List[str]] = Field(None, description="List of positive themes identified")
    negative_themes: Optional[List[str]] = Field(None, description="List of negative themes identified")
    feature_requests: Optional[List[str]] = Field(None, description="List of feature requests identified")
    bug_reports: Optional[List[str]] = Field(None, description="List of bug reports identified")
    # Add other fields if the LLM should extract them

class ReviewAnalyzer:
    """Analyzes a single review text using an LLM for structured insights."""

    def __init__(self, model: str = OPENAI_MODEL):
        self.model = model

    def analyze_review_text(self, review_text: str) -> Dict[str, Any]:
        """Analyzes the text and returns a dictionary with structured data or an error."""
        
        if not review_text or not review_text.strip():
            logger.warning("Empty review text passed to analyzer.")
            return {"error": "Input text is empty."}

        # Define the desired JSON output structure for the prompt
        # This mirrors the Pydantic model
        json_schema_description = ReviewAnalysisResult.model_json_schema(mode='serialization')
        # Convert dict schema to string for prompt
        json_schema_string = json.dumps(json_schema_description, indent=2)

        # --- LLM Prompt for Structured Analysis --- 
        prompt = [
            {
                "role": "system",
                "content": f"""You are an expert text analyst. Analyze the following Steam review text.
Extract key information and respond *only* with a valid JSON object adhering strictly to the following JSON schema. 
Do not include any introductory text, explanations, or markdown formatting outside the JSON object.
Schema:
```json
{json_schema_string}
```
Populate the fields based *only* on the provided review text. If a category (e.g., bug_reports) has no relevant information, provide an empty list `[]` for array types or `null` for optional string types."""
            },
            {
                "role": "user",
                "content": f"Analyze this review text and respond with JSON:\n\n{review_text}"
            }
        ]

        try:
            logger.debug(f"Sending review text snippet for analysis: {review_text[:100]}...")
            analysis_response_text = call_openai_api(
                messages=prompt,
                model=self.model,
                temperature=0.2, # Low temp for extraction tasks
                max_tokens=1000 # Adjust as needed based on expected output size
            )

            # Parse and Validate
            if analysis_response_text:
                if analysis_response_text.startswith("[REFUSAL"):
                     logger.warning(f"Analysis request refused by model: {analysis_response_text}")
                     return {"error": "Model refused analysis request", "refusal_message": analysis_response_text}
                else:
                    try:
                        json_start = analysis_response_text.find('{')
                        json_end = analysis_response_text.rfind('}')
                        if json_start != -1 and json_end != -1:
                            json_string = analysis_response_text[json_start:json_end+1]
                            parsed_json = json.loads(json_string)
                            
                            # Validate with Pydantic
                            validated_data = ReviewAnalysisResult(**parsed_json)
                            logger.info("Successfully parsed and validated analysis JSON.")
                            # Return the validated data as a standard dict for DB update
                            # Include the model used in the result dict
                            result = validated_data.model_dump()
                            result['llm_analysis_model'] = self.model
                            return result
                        else:
                            raise ValueError("No JSON object found in response.")
                    except (json.JSONDecodeError, ValueError, ValidationError) as parse_err:
                        # Make logging more prominent and ensure raw response is logged
                        logger.exception(f"Failed to parse/validate analysis JSON. Error: {parse_err}. Raw response received from API:\n---\n{analysis_response_text}\n---")
                        return {"error": "Failed to parse/validate analysis JSON from AI.", "raw_response": analysis_response_text}
            else:
                 logger.error("Analysis generation failed (API returned None or empty string).")
                 return {"error": "Analysis generation failed (API returned None or empty)."}
        
        except Exception as e:
            logger.exception(f"Exception during analysis API call: {e}")
            return {"error": f"Exception during analysis: {str(e)}"} 