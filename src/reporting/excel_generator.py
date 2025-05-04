import logging
import io
from typing import List, Dict, Any
import json

import pandas as pd
from sqlalchemy.orm import Session

# Adjust path for imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database import crud, models
from database.connection import get_db
from processing.analyzer import ReviewAnalysisResult # For LLM summary structure
from openai_client import call_openai_api, OPENAI_MODEL
from constants import LANGUAGE_MAP # Import from constants

logger = logging.getLogger(__name__)

# Placeholder for the main function
def generate_summary_report(app_id: int, start_timestamp: int) -> bytes:
    logger.info(f"Generating summary report for app {app_id} since timestamp {start_timestamp}")
    output = io.BytesIO()
    db_session_gen = get_db()
    db = next(db_session_gen)

    try:
        # Fetch reviews for the given app and time range
        logger.info(f"Fetching reviews for app {app_id} since {start_timestamp}...")
        reviews = crud.get_reviews_for_app_since(db, app_id, start_timestamp)

        if not reviews:
            logger.warning(f"No reviews found for app {app_id} since {start_timestamp}. Returning empty report.")
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame([{"Status": f"No reviews found for App ID {app_id} since timestamp {start_timestamp}"}]).to_excel(writer, sheet_name="Status", index=False)
            output.seek(0)
            return output.getvalue()

        logger.info(f"Fetched {len(reviews)} reviews for report generation.")

        # Get distinct languages for these reviews
        distinct_languages = crud.get_distinct_languages_for_app_since(db, app_id, start_timestamp)
        logger.info(f"Found distinct languages in results: {distinct_languages}")

        # Convert to DataFrame for easier manipulation
        reviews_df = pd.DataFrame([r.to_dict() for r in reviews])
        # Flatten author data
        if 'author' in reviews_df.columns:
            try:
                 author_df = pd.json_normalize(reviews_df['author'])
                 author_df.columns = [f"author_{col}" for col in author_df.columns]
                 reviews_df = pd.concat([reviews_df.drop(columns=['author']), author_df], axis=1)
            except Exception as e:
                 logger.error(f"Error flattening author data in DataFrame: {e}")

        # Initialize Excel Writer
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            
            # --- Step 2.5: Loop through languages --- 
            logger.info("Processing summaries and reviews per language...")
            all_language_summaries = {} # To store LLM results for overall summary later
            for lang_code in distinct_languages:
                lang_name = LANGUAGE_MAP.get(lang_code, lang_code) # Use imported map
                logger.info(f"-- Processing language: {lang_name} ({lang_code}) --")
                
                # Filter DataFrame for the current language
                lang_df = reviews_df[reviews_df['original_language'] == lang_code].copy()
                
                if lang_df.empty:
                     logger.warning(f"Skipping language {lang_code}, no reviews found after filtering.")
                     continue

                logger.info(f"Found {len(lang_df)} reviews for {lang_name}.")

                # === Step 2.6: LLM Summary (Per-Language) ===
                logger.info(f"Generating LLM summary for {lang_name}...")
                # Prepare text input - concatenate relevant text fields
                # Use english_translation if available and valid, else original if english
                texts_for_summary = []
                for _, row in lang_df.iterrows():
                    text = row.get('english_translation')
                    # Add check for refusal messages if stored
                    if text and isinstance(text, str) and not text.startswith('[Translation') and not text.startswith('[REFUSAL'):
                        texts_for_summary.append(f"Review (ID: {row.get('recommendationid')}): {text}")
                    elif row.get('original_language') == 'english' and row.get('original_review_text'):
                         # Use original if it was English and translation is missing/invalid
                         texts_for_summary.append(f"Review (ID: {row.get('recommendationid')}): {row.get('original_review_text')}")
                
                lang_summary_input_text = "\n---\n".join(texts_for_summary[:200]) # Limit input size
                lang_summary_data = {"error": "LLM Summary generation failed (Unknown reason)."} # Default error

                if not lang_summary_input_text.strip():
                    logger.warning(f"No valid text found for LLM summary for language {lang_code}.")
                    lang_summary_data = {"error": "No valid text input for summary."}
                else:
                    # Define schema for prompt (using the Pydantic model)
                    try:
                         json_schema_string = json.dumps(ReviewAnalysisResult.model_json_schema(mode='serialization'), indent=2)
                    except Exception as schema_err:
                         logger.error(f"Failed to generate JSON schema for prompt: {schema_err}")
                         json_schema_string = "{\"error\": \"Schema generation failed\"}" # Fallback schema

                    # Define prompt for per-language batch summary
                    prompt = [
                        {
                            "role": "system",
                            "content": f"""You are an expert game analyst. Summarize the key points from the following batch of Steam reviews, which were originally written in {lang_name}.
Focus on overall sentiment, common positive/negative themes, feature requests, and bug reports identified within THIS BATCH of reviews.
**IMPORTANT: Respond *only* with a valid JSON object adhering strictly to the following JSON schema. Do not include any text outside the JSON object:**
```json
{json_schema_string}
```
If a category has no relevant information in this batch, provide an empty list `[]` or `null`."""
                        },
                        {
                            "role": "user",
                            "content": f"Summarize this batch of {len(texts_for_summary)} translated {lang_name} Steam reviews:\n\n{lang_summary_input_text}"
                        }
                    ]

                    try:
                        # Call LLM
                        summary_response_text = call_openai_api(
                            prompt=prompt,
                            # Potentially use a different/cheaper model for summaries?
                            # model=OPENAI_SUMMARY_MODEL, 
                            temperature=0.3,
                            max_tokens=1500 
                        )
                        # Parse and validate
                        if summary_response_text and not summary_response_text.startswith("[REFUSAL"):
                            try:
                                json_start = summary_response_text.find('{')
                                json_end = summary_response_text.rfind('}')
                                if json_start != -1 and json_end != -1:
                                    json_string = summary_response_text[json_start:json_end+1]
                                    parsed_json = json.loads(json_string)
                                    validated_data = ReviewAnalysisResult(**parsed_json)
                                    lang_summary_data = validated_data.model_dump() # Store as dict
                                    logger.info(f"Successfully generated and validated summary for {lang_name}.")
                                else:
                                     raise ValueError("No JSON object found in summary response.")
                            except (json.JSONDecodeError, ValueError, ValidationError) as parse_err:
                                logger.error(f"Failed to parse/validate summary JSON for {lang_name}: {parse_err}\nRaw: {summary_response_text[:500]}...")
                                lang_summary_data = {"error": f"Failed to parse/validate summary JSON for {lang_name}", "raw_response": summary_response_text}
                        elif summary_response_text and summary_response_text.startswith("[REFUSAL"):
                            lang_summary_data = {"error": f"Summary request refused for {lang_name}", "refusal_message": summary_response_text}
                        else:
                             lang_summary_data = {"error": f"LLM summary call failed for {lang_name} (returned None/empty)."}
                    except Exception as api_err:
                         logger.exception(f"Error calling LLM for {lang_name} summary: {api_err}")
                         lang_summary_data = {"error": f"Exception during LLM call for {lang_name} summary."}   
                
                all_language_summaries[lang_code] = lang_summary_data # Store result
                # === End Step 2.6 ===

                # === Step 2.7: Excel Sheet Writing (Per-Language) ===
                logger.info(f"Writing Excel sheets for {lang_name}...")
                summary_sheet_name = f"Summary_{lang_code}"
                reviews_sheet_name = f"Reviews_{lang_code}"

                # --- Write Summary Sheet for Language ---
                current_row = 0
                # Calculate stats for this language subset
                lang_total = len(lang_df)
                lang_pos = len(lang_df[lang_df['voted_up'] == True])
                lang_neg = lang_total - lang_pos
                lang_pos_pct = (lang_pos / lang_total) * 100 if lang_total > 0 else 0

                lang_stats_data = {
                    'Metric': [
                        f'{lang_name} Reviews Processed',
                        'Positive Reviews',
                        'Negative Reviews',
                        'Positive Percentage'
                    ],
                    'Value': [
                        lang_total,
                        lang_pos,
                        lang_neg,
                        f"{lang_pos_pct:.1f}%"
                    ]
                }
                lang_stats_df = pd.DataFrame(lang_stats_data)
                lang_stats_df.to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)
                current_row += len(lang_stats_df) + 2

                # Write structured analysis below stats
                if isinstance(lang_summary_data, dict):
                    if 'error' in lang_summary_data:
                        error_df = pd.DataFrame([lang_summary_data.get('error')], columns=['Analysis Error'])
                        error_df.to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)
                        current_row += 2
                        # Optionally write raw response if available
                        if 'raw_response' in lang_summary_data:
                             pd.DataFrame([lang_summary_data['raw_response']], columns=['Raw AI Response']).to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)
                        elif 'refusal_message' in lang_summary_data:
                             pd.DataFrame([lang_summary_data['refusal_message']], columns=['Refusal Message']).to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)
                    else:
                        # Write parsed analysis data
                        for key, value in lang_summary_data.items():
                            section_title = key.replace('_', ' ').title()
                            pd.DataFrame([section_title], columns=['Analysis Section']).to_excel(writer, sheet_name=summary_sheet_name, index=False, header=False, startrow=current_row)
                            current_row += 1
                            if isinstance(value, list):
                                pd.DataFrame(value, columns=['Details']).to_excel(writer, sheet_name=summary_sheet_name, index=False, header=False, startrow=current_row)
                                current_row += len(value) if value else 1 # Inc row even if empty list
                            elif value is not None:
                                pd.DataFrame([str(value)], columns=['Details']).to_excel(writer, sheet_name=summary_sheet_name, index=False, header=False, startrow=current_row)
                                current_row += 1
                            else:
                                current_row += 1 # Increment row for None/null values
                            current_row += 1 # Blank row
                else:
                    pd.DataFrame(["Analysis data invalid"], columns=['Status']).to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)

                # --- Write Reviews Sheet for Language ---
                # Select and order columns for the raw data sheet
                review_cols_order = [
                    'recommendationid', 'voted_up', 'sentiment', # Add computed sentiment if desired
                    'original_review_text', 'english_translation',
                    'timestamp_created', 'timestamp_updated', # Consider formatting dates here?
                    'votes_up', 'votes_funny', 'weighted_vote_score', 'comment_count',
                    'author_steamid', 'author_playtime_forever', 'author_playtime_at_review',
                    'steam_purchase', 'received_for_free', 'written_during_early_access',
                    'developer_response'
                    # Add other author_* fields if desired
                ]
                # Add sentiment column (example)
                lang_df['sentiment'] = lang_df['voted_up'].apply(lambda x: 'Positive' if x else 'Negative')
                # Select only existing columns from the preferred order
                lang_df_cols = [col for col in review_cols_order if col in lang_df.columns]
                lang_df_ordered = lang_df[lang_df_cols]
                lang_df_ordered.to_excel(writer, sheet_name=reviews_sheet_name, index=False)
                logger.info(f"Written sheets {summary_sheet_name} and {reviews_sheet_name}.")
                # === End Step 2.7 ===

            # --- End Language Loop ---

            # === Step 2.8: LLM Summary (Overall) ===
            logger.info("Generating LLM summary for all fetched reviews...")
            # Prepare combined input text from ALL valid reviews fetched
            overall_texts_for_summary = []
            for _, row in reviews_df.iterrows(): # Use the original full DataFrame
                 text = row.get('english_translation')
                 if text and isinstance(text, str) and not text.startswith('[Translation') and not text.startswith('[REFUSAL'):
                    overall_texts_for_summary.append(f"Review (Lang: {row.get('original_language')}, ID: {row.get('recommendationid')}): {text}")
                 elif row.get('original_language') == 'english' and row.get('original_review_text'):
                     overall_texts_for_summary.append(f"Review (Lang: {row.get('original_language')}, ID: {row.get('recommendationid')}): {row.get('original_review_text')}")

            overall_summary_input_text = "\n---\n".join(overall_texts_for_summary[:300]) # Limit input size (maybe more than per-lang)
            overall_summary_data = {"error": "Overall LLM Summary generation failed (Unknown)."} # Default

            if not overall_summary_input_text.strip():
                logger.warning("No valid text found for overall LLM summary.")
                overall_summary_data = {"error": "No valid text input for overall summary."}
            else:
                try:
                    # Use same schema definition as per-language
                    json_schema_string = json.dumps(ReviewAnalysisResult.model_json_schema(mode='serialization'), indent=2)
                except Exception as schema_err:
                    logger.error(f"Failed to generate JSON schema for overall prompt: {schema_err}")
                    json_schema_string = "{\"error\": \"Schema generation failed\"}"

                # Define prompt for overall batch summary
                prompt = [
                    {
                        "role": "system",
                        "content": f"""You are an expert game analyst. Summarize the key points from the following batch of Steam reviews, originally written in various languages but translated to English.
Focus on overall sentiment, common positive/negative themes, feature requests, and bug reports identified across THE ENTIRE BATCH.
**IMPORTANT: Respond *only* with a valid JSON object adhering strictly to the following JSON schema...:**
```json
{json_schema_string}
```
If a category has no relevant information, provide an empty list `[]` or `null`."""
                    },
                    {
                        "role": "user",
                        "content": f"Summarize this batch of {len(overall_texts_for_summary)} translated Steam reviews (from various languages):\n\n{overall_summary_input_text}"
                    }
                ]

                try:
                    summary_response_text = call_openai_api(
                        prompt=prompt,
                        temperature=0.3, # Keep temp reasonable for summary
                        max_tokens=2000 # Allow decent size for overall summary
                    )
                    # Parse and validate
                    if summary_response_text and not summary_response_text.startswith("[REFUSAL"):
                        try:
                            json_start = summary_response_text.find('{')
                            json_end = summary_response_text.rfind('}')
                            if json_start != -1 and json_end != -1:
                                json_string = summary_response_text[json_start:json_end+1]
                                parsed_json = json.loads(json_string)
                                validated_data = ReviewAnalysisResult(**parsed_json)
                                overall_summary_data = validated_data.model_dump()
                                logger.info("Successfully generated and validated overall summary.")
                            else: raise ValueError("No JSON object found in overall summary response.")
                        except (json.JSONDecodeError, ValueError, ValidationError) as parse_err:
                            logger.error(f"Failed to parse/validate overall summary JSON: {parse_err}\nRaw: {summary_response_text[:500]}...")
                            overall_summary_data = {"error": "Failed to parse/validate overall summary JSON", "raw_response": summary_response_text}
                    elif summary_response_text and summary_response_text.startswith("[REFUSAL"):
                        overall_summary_data = {"error": "Overall summary request refused", "refusal_message": summary_response_text}
                    else:
                        overall_summary_data = {"error": "Overall LLM summary call failed (returned None/empty)."}
                except Exception as api_err:
                    logger.exception(f"Error calling LLM for overall summary: {api_err}")
                    overall_summary_data = {"error": "Exception during LLM call for overall summary."}
            # === End Step 2.8 ===

            # === Step 2.9: Excel Sheet Writing (Overall) ===
            logger.info("Writing Overall Summary sheet...")
            overall_summary_sheet_name = "Summary_Overall"
            current_row_overall = 0

            # Calculate overall stats
            overall_total = len(reviews_df)
            overall_pos = len(reviews_df[reviews_df['voted_up'] == True])
            overall_neg = overall_total - overall_pos
            overall_pos_pct = (overall_pos / overall_total) * 100 if overall_total > 0 else 0
            
            overall_stats_data = {
                'Metric': [
                    'Total Reviews Analyzed',
                    'Positive Reviews',
                    'Negative Reviews',
                    'Positive Percentage'
                ] + [f"{LANGUAGE_MAP.get(lang, lang)} Count" for lang in distinct_languages], # Add language counts
                'Value': [
                    overall_total,
                    overall_pos,
                    overall_neg,
                    f"{overall_pos_pct:.1f}%"
                ] + [len(reviews_df[reviews_df['original_language'] == lang]) for lang in distinct_languages] # Get counts per lang
            }
            overall_stats_df = pd.DataFrame(overall_stats_data)
            overall_stats_df.to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
            current_row_overall += len(overall_stats_df) + 2

            # Write overall structured analysis below stats
            if isinstance(overall_summary_data, dict):
                if 'error' in overall_summary_data:
                    pd.DataFrame([overall_summary_data.get('error')], columns=['Analysis Error']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
                    current_row_overall += 2
                    if 'raw_response' in overall_summary_data:
                         pd.DataFrame([overall_summary_data['raw_response']], columns=['Raw AI Response']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
                    elif 'refusal_message' in overall_summary_data:
                         pd.DataFrame([overall_summary_data['refusal_message']], columns=['Refusal Message']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
                else:
                    # Write parsed analysis data
                    for key, value in overall_summary_data.items():
                        section_title = key.replace('_', ' ').title()
                        pd.DataFrame([section_title], columns=['Analysis Section']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, header=False, startrow=current_row_overall)
                        current_row_overall += 1
                        if isinstance(value, list):
                            pd.DataFrame(value, columns=['Details']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, header=False, startrow=current_row_overall)
                            current_row_overall += len(value) if value else 1
                        elif value is not None:
                            pd.DataFrame([str(value)], columns=['Details']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, header=False, startrow=current_row_overall)
                            current_row_overall += 1
                        else:
                             current_row_overall += 1
                        current_row_overall += 1 # Blank row
            else:
                pd.DataFrame(["Overall analysis data invalid"], columns=['Status']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
            logger.info(f"Written sheet {overall_summary_sheet_name}.")
            # === End Step 2.9 ===

        logger.info("Report generation completed.")

    except Exception as e:
        logger.exception(f"Error during report generation: {e}")
        # Return an Excel file indicating error
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame([{"Error": str(e)}]).to_excel(writer, sheet_name="Error", index=False)
    finally:
        logger.info("Closing database session for report generation.")
        try:
            next(db_session_gen)
        except StopIteration:
            pass
        except Exception as e:
             logger.error(f"Error closing DB session: {e}")

    output.seek(0)
    return output.getvalue()

if __name__ == '__main__':
    # Example usage (for testing purposes)
    # Make sure DB is running and has data
    logging.basicConfig(level=logging.INFO)
    logger.info("Running excel_generator directly for testing...")
    TEST_APP_ID = 3228590 
    # Get timestamp for e.g., 30 days ago
    import datetime
    start_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    TEST_START_TIMESTAMP = int(start_date.timestamp())
    
    logger.info(f"Using App ID: {TEST_APP_ID}, Start Timestamp: {TEST_START_TIMESTAMP} ({start_date.date()})")
    
    try:
        report_bytes = generate_summary_report(TEST_APP_ID, TEST_START_TIMESTAMP)
        output_filename = f"test_report_{TEST_APP_ID}_{start_date.strftime('%Y%m%d')}.xlsx"
        with open(output_filename, 'wb') as f:
            f.write(report_bytes)
        logger.info(f"Test report saved to: {output_filename}")
    except Exception as e:
        logger.exception(f"Error generating test report: {e}") 