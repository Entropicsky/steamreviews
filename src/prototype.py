#!/usr/bin/env python3
"""
Steam Reviews Translation and Analysis Prototype - Refactored

Fetches Steam reviews for a specified App ID and language, translates them,
runs analysis, and saves results to JSON and Excel.

Usage:
    python -m src.prototype --language <lang_code> [--app-id <id>] [--max-reviews <num>]

Example:
    python -m src.prototype --language japanese --app-id 570 --max-reviews 100
"""

import os
import sys
import json
import time
import logging
import argparse # Import argparse
from typing import List, Dict, Any, Optional
from dataclasses import asdict
import pandas as pd

# Import refactored components
from .models import Review, AnalysisResponse # Import the Pydantic model
from .steam_client import SteamAPI
from .openai_client import call_openai_api, OPENAI_MODEL # Import call_openai_api and OPENAI_MODEL
from pydantic import ValidationError
from .constants import LANGUAGE_MAP # Import from constants

# Configure logging (basic setup)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Configuration (Defaults and Env Vars) ---
DEFAULT_APP_ID = "3228590"
DEFAULT_MAX_REVIEWS = 200
CACHE_DIR = os.getenv("CACHE_DIR", "data") # Cache dir still from env
OUTPUT_DIR = CACHE_DIR # Output files go to the same cache dir for simplicity

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)


# --- Analyzer Class ---
class Analyzer:
    """Analyzes translated reviews for trends and insights."""

    def __init__(self, target_language_code: str, model: str = OPENAI_MODEL):
        self.model = model
        self.language_code = target_language_code # Store language for context

    def generate_summary(self, reviews: List[Review]) -> Dict[str, Any]:
        """Generate a summary, requesting JSON and manually parsing."""
        logger.info("Generating review summary")

        language_name = LANGUAGE_MAP.get(self.language_code, self.language_code)

        total_reviews = len(reviews)
        if total_reviews == 0:
            logger.warning("No reviews provided for analysis.")
            return {"total_reviews_processed": 0, "analysis": {"error": "No reviews to analyze."}}

        positive_reviews = sum(1 for r in reviews if r.voted_up)
        negative_reviews = total_reviews - positive_reviews
        positive_percent = (positive_reviews / total_reviews) * 100 if total_reviews > 0 else 0
        # Language counts based on the *fetched* language, not just hardcoded Chinese
        language_counts = {}
        for r in reviews:
            lang_name = LANGUAGE_MAP.get(r.language, r.language)
            language_counts[lang_name] = language_counts.get(lang_name, 0) + 1

        # Prepare review text & metadata for analysis
        analysis_input_data = []
        for review in reviews:
            if review.translated_text and not review.translated_text.startswith("[Translation") and not review.translated_text.startswith("[REFUSAL"):
                sentiment = "positive" if review.voted_up else "negative"
                lang_name_for_input = LANGUAGE_MAP.get(review.language, review.language)
                playtime_hours = review.author.playtime_at_review / 60 if review.author.playtime_at_review else 0
                # Construct input string with metadata
                review_context = (
                    f"Review (ID: {review.recommendationid}, Lang: {lang_name_for_input}, Sentiment: {sentiment}, "
                    f"Playtime: {playtime_hours:.1f} hrs, Votes Up: {review.votes_up}): "
                    f"{review.translated_text}"
                )
                analysis_input_data.append(review_context)

        # Limit input size for analysis prompt
        sampled_reviews_for_analysis = analysis_input_data[:150] # Sample up to 150 reviews with metadata
        analysis_input_text = "\n---\n".join(sampled_reviews_for_analysis)

        # Rough token estimation (adjust if needed)
        estimated_tokens = len(analysis_input_text) / 3
        logger.info(f"Preparing {len(sampled_reviews_for_analysis)} reviews with metadata for analysis (approx. {estimated_tokens:.0f} tokens).")

        # Check if input is empty after filtering
        if not analysis_input_text.strip():
             logger.warning("No valid translated text available for analysis.")
             analysis_result = {"error": "Analysis failed: No valid translated text found."}
        else:
            # Re-add JSON schema description for the prompt
            json_schema_description = """{
  "overall_sentiment": "<Brief summary text>",
  "positive_themes": ["<Theme 1>", ...],
  "negative_themes": ["<Theme 1>", ...],
  "feature_analysis": "<Comments text>",
  "player_suggestions": ["<Suggestion 1>", ...],
  "developer_opportunities": "<Opportunities text>",
  "playtime_engagement_insights": "<Insights text>",
  "cultural_insights": "<Insights text or null>"
}"""

            try:
                # --- Analysis Prompt (Updated to mention specific language) ---
                prompt = [
                    {
                        "role": "system",
                        "content": f"""You are an expert game analyst... 
Analyze the following set of Steam game reviews (originally written in {language_name}, translated to English), including the provided metadata...
**IMPORTANT: Respond *only* with a valid JSON object adhering strictly to the following structure...:**

```json
{json_schema_description}
```

Populate the values based on the reviews... Consider the metadata..."""
                    },
                    {
                        "role": "user",
                        "content": f"Analyze these {len(sampled_reviews_for_analysis)} translated {language_name} Steam reviews with metadata and respond with JSON:\n\n{analysis_input_text}"
                    }
                ]

                # Use the reverted API call (expects string back)
                analysis_response_text = call_openai_api(
                    prompt=prompt,
                    model=self.model,
                    max_tokens=3500,
                    temperature=0.5
                    # No response_model here
                )

                # Manually parse the response string as JSON
                if analysis_response_text:
                    if analysis_response_text.startswith("[REFUSAL:"):
                         logger.warning(f"Analysis request refused by model: {analysis_response_text}")
                         analysis_result = {"error": "Model refused analysis request", "refusal_message": analysis_response_text}
                    else:
                        try:
                            # Attempt to find JSON block and parse
                            json_start = analysis_response_text.find('{')
                            json_end = analysis_response_text.rfind('}')
                            if json_start != -1 and json_end != -1:
                                json_string = analysis_response_text[json_start:json_end+1]
                                # Parse raw JSON first
                                parsed_json = json.loads(json_string)
                                # Validate with Pydantic model
                                try:
                                    # Store the validated Pydantic object itself
                                    analysis_result = AnalysisResponse(**parsed_json)
                                    logger.info("Successfully parsed and validated JSON analysis.")
                                except ValidationError as val_err:
                                    logger.error(f"Validation failed for parsed JSON: {val_err}")
                                    # Store error dict, including the raw parsed JSON for debugging
                                    analysis_result = {"error": "Parsed JSON failed Pydantic validation", "raw_json": parsed_json}
                            else:
                                raise ValueError("No JSON object found in response.")
                        except (json.JSONDecodeError, ValueError) as json_e:
                            logger.error(f"Failed to parse analysis JSON: {json_e}\nRaw response:\n{analysis_response_text}")
                            analysis_result = {"error": "Failed to parse analysis JSON from AI.", "raw_response": analysis_response_text}
                else:
                    analysis_result = {"error": "Analysis generation failed (API returned None or empty string)."}
                    logger.error("Analysis generation failed (API returned None or empty)." + (f" Raw Response: {analysis_response_text}" if analysis_response_text is not None else ""))

            except Exception as e:
                logger.error(f"Analysis error during API call or processing: {e}")
                analysis_result = {"error": f"Error generating analysis: {str(e)}"}

        # Compile the summary
        summary = {
            "language_analyzed": language_name,
            "total_reviews_processed": total_reviews,
            "positive_reviews": positive_reviews,
            "negative_reviews": negative_reviews,
            "positive_percent": positive_percent,
            "language_counts": language_counts, # Include counts of original languages fetched
            "analysis": analysis_result
        }
        logger.info("Summary generation complete")
        return summary


# --- Main Execution ---
def main():
    """Main function to parse args and run the workflow."""

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Fetch, translate, and analyze Steam reviews.")
    parser.add_argument("-l", "--language", required=True, choices=LANGUAGE_MAP.keys(),
                        help="Target language code for reviews (e.g., japanese, schinese)")
    parser.add_argument("-a", "--app-id", default=DEFAULT_APP_ID,
                        help=f"Steam App ID (default: {DEFAULT_APP_ID})")
    parser.add_argument("-m", "--max-reviews", type=int, default=DEFAULT_MAX_REVIEWS,
                        help=f"Maximum number of reviews to fetch (default: {DEFAULT_MAX_REVIEWS})")
    args = parser.parse_args()

    # Use parsed arguments
    app_id = args.app_id
    max_reviews = args.max_reviews
    language_code = args.language
    language_name = LANGUAGE_MAP.get(language_code, language_code)

    logger.info(f"Starting Steam Reviews Analysis for App ID: {app_id}, Language: {language_name} ({language_code})")
    logger.info(f"Max reviews to fetch: {max_reviews}")

    # 1. Fetch reviews for the specified language
    steam_api = SteamAPI()
    logger.info(f"Fetching {language_name} reviews...")
    reviews = steam_api.fetch_reviews(app_id, language=language_code, max_reviews=max_reviews)

    if not reviews:
        logger.warning("No reviews fetched. Exiting.")
        sys.exit(0)
    logger.info(f"Fetched {len(reviews)} total {language_name} reviews")

    # 2. Translate reviews (This logic will move to a separate processing script)
    # translator = Translator(target_language_code=language_code, app_id=app_id)
    # translated_reviews = translator.batch_translate(reviews)
    # logger.info(f"Attempted translation for {len(translated_reviews)} reviews")
    # Placeholder for now - assume reviews are translated/English for analysis
    translated_reviews = reviews # TEMPORARY - REMOVE WHEN TRANSLATION SCRIPT EXISTS
    logger.warning("SKIPPING ACTUAL TRANSLATION STEP - USING ORIGINAL TEXT FOR ANALYSIS")
    for r in translated_reviews:
         if r.language != 'english':
              r.translated_text = r.original_review_text # Use original as placeholder
         else:
              r.translated_text = r.original_review_text

    # 3. Analyze reviews (Analyzer needs language_code for context)
    analyzer = Analyzer(target_language_code=language_code)
    summary = analyzer.generate_summary(translated_reviews)

    # 4. Output results
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    # Include language code in directory/filenames
    run_dir_name = f"{timestamp}_{app_id}_{language_code}"
    run_output_dir = os.path.join(OUTPUT_DIR, run_dir_name)
    try:
        os.makedirs(run_output_dir, exist_ok=True)
        logger.info(f"Created unique output directory: {run_output_dir}")
    except OSError as e:
        logger.error(f"Failed to create output directory {run_output_dir}: {e}")
        run_output_dir = OUTPUT_DIR

    base_filename = f"steam_analysis_{app_id}_{language_code}" # Add lang to filename
    json_output_file = os.path.join(run_output_dir, f"{base_filename}.json")
    excel_output_file = os.path.join(run_output_dir, f"{base_filename}.xlsx")

    # Prepare data for output
    # Raw review data (flattened)
    review_dicts = [r.to_dict() for r in translated_reviews]
    flat_review_dicts = []
    for r_dict in review_dicts:
        author_info = r_dict.pop('author', {}) # Remove author dict
        for key, value in author_info.items():
            r_dict[f'author_{key}'] = value # Add prefixed keys
        flat_review_dicts.append(r_dict)
    reviews_df = pd.DataFrame(flat_review_dicts)

    # Summary statistics
    summary_stats_data = {
        'Metric': [
            'Language Analyzed',
            'Total Reviews Processed',
            'Positive Reviews',
            'Negative Reviews',
            'Positive Percentage'
        ] + list(summary.get('language_counts', {}).keys()), # Add dynamic language counts
        'Value': [
            summary.get('language_analyzed', 'N/A'),
            summary.get('total_reviews_processed', 'N/A'),
            summary.get('positive_reviews', 'N/A'),
            summary.get('negative_reviews', 'N/A'),
            f"{summary.get('positive_percent', 0):.1f}%"
        ] + list(summary.get('language_counts', {}).values()) # Add dynamic language counts
    }
    summary_stats_df = pd.DataFrame(summary_stats_data)

    # Get the analysis result (now a Pydantic object or error dict)
    analysis_data = summary.get('analysis', None)

    # --- Save Outputs ---

    # Save detailed JSON output
    # Note: If analysis_data is a Pydantic object, we need to convert it for JSON
    try:
        analysis_for_json = analysis_data
        if isinstance(analysis_data, AnalysisResponse):
            analysis_for_json = analysis_data.model_dump() # Use pydantic's method

        output_data = {
            "app_id": app_id,
            "language_analyzed": language_name,
            "summary_stats": summary_stats_df.to_dict('records'), # Save stats too
            "analysis": analysis_for_json, # Save parsed dict or error dict
            "reviews": [r.to_dict() for r in translated_reviews]
        }
        with open(json_output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Detailed analysis and reviews saved to {json_output_file}")
    except Exception as e:
        logger.error(f"Error saving JSON analysis: {e}")

    # Save multi-sheet Excel file
    try:
        with pd.ExcelWriter(excel_output_file, engine='openpyxl') as writer:
            # Write Reviews sheet
            # Reorder columns for readability (optional)
            cols_order = ['recommendationid', 'appid', 'language', 'voted_up', 'sentiment',
                          'review_text', 'translated_text',
                          'timestamp_created', 'timestamp_updated', 'created_date',
                          'votes_up', 'votes_funny', 'weighted_vote_score', 'comment_count',
                          'author_steamid', 'author_num_games_owned', 'author_num_reviews',
                          'author_playtime_forever', 'author_playtime_at_review',
                          'author_playtime_last_two_weeks', 'author_last_played',
                          'steam_purchase', 'received_for_free', 'written_during_early_access',
                          'developer_response', 'timestamp_dev_responded']
            df_cols = [col for col in cols_order if col in reviews_df.columns]
            reviews_df_ordered = reviews_df[df_cols]
            reviews_df_ordered.to_excel(writer, sheet_name='Reviews', index=False)
            logger.info(f"'Reviews' sheet written to {excel_output_file}")

            # --- Write Structured Summary Sheet ---
            current_row = 0
            summary_stats_df.to_excel(writer, sheet_name='Summary', index=False, startrow=current_row)
            current_row += len(summary_stats_df) + 2

            # Write AI Analysis (handle Pydantic object or error dict)
            if isinstance(analysis_data, AnalysisResponse):
                # Iterate through fields of the Pydantic model
                for field_name, field_value in analysis_data:
                    section_title = field_name.replace('_', ' ').title()
                    title_df = pd.DataFrame([section_title], columns=['Analysis Section'])
                    title_df.to_excel(writer, sheet_name='Summary', index=False, header=False, startrow=current_row)
                    current_row += 1

                    if isinstance(field_value, list):
                        list_df = pd.DataFrame(field_value, columns=['Details'])
                        list_df.to_excel(writer, sheet_name='Summary', index=False, header=False, startrow=current_row)
                        current_row += len(list_df)
                    elif field_value is not None: # Handle strings and potentially None for optional fields
                        text_df = pd.DataFrame([str(field_value)], columns=['Details'])
                        text_df.to_excel(writer, sheet_name='Summary', index=False, header=False, startrow=current_row)
                        current_row += 1
                    else: # Handle None case explicitly if needed, or just skip/add placeholder
                        current_row += 1 # Increment row even if value is None

                    current_row += 1 # Blank row between sections

            elif isinstance(analysis_data, dict) and 'error' in analysis_data:
                # Write error message if analysis failed
                error_df = pd.DataFrame([analysis_data['error']], columns=['Analysis Error'])
                error_df.to_excel(writer, sheet_name='Summary', index=False, startrow=current_row)
                current_row += 2
                if 'raw_response' in analysis_data:
                    raw_resp_df = pd.DataFrame([analysis_data['raw_response']], columns=['Raw AI Response'])
                    raw_resp_df.to_excel(writer, sheet_name='Summary', index=False, startrow=current_row)
                elif 'refusal_message' in analysis_data:
                     refusal_df = pd.DataFrame([analysis_data['refusal_message']], columns=['Refusal Message'])
                     refusal_df.to_excel(writer, sheet_name='Summary', index=False, startrow=current_row)

            else:
                 # Fallback if analysis is somehow None or unexpected format
                 fallback_df = pd.DataFrame(["Analysis data missing or in unexpected format."], columns=['Analysis Status'])
                 fallback_df.to_excel(writer, sheet_name='Summary', index=False, startrow=current_row)

            logger.info(f"'Summary' sheet written to {excel_output_file}")

        logger.info(f"Multi-sheet Excel file saved: {excel_output_file}")
    except Exception as e:
        logger.error(f"Error saving Excel file: {e}")

    # 5. Print summary to console
    print("\n" + "="*50)
    print(f" STEAM REVIEWS ANALYSIS - APP ID: {app_id} - LANGUAGE: {language_name} ({language_code})")
    print("="*50)
    # Print summary stats table from DataFrame for consistency
    print(summary_stats_df.to_string(index=False, header=True))
    print("\nANALYSIS (JSON/Object):")
    analysis_print = analysis_data
    if isinstance(analysis_data, AnalysisResponse):
        analysis_print = analysis_data.model_dump()
    print(json.dumps(analysis_print, indent=2, ensure_ascii=False))
    print("\n" + "="*50)
    print(f"Detailed output saved to: {json_output_file}")
    print(f"Review data saved to:    {excel_output_file}")
    print("="*50)


if __name__ == "__main__":
    main() 