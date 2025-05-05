import logging
import io
import asyncio # Added
from typing import List, Dict, Any, Optional
import json

import pandas as pd
from sqlalchemy.orm import Session
from pydantic import ValidationError # Added for explicit handling

# Adjust path for imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database import crud, models
from database.connection import get_db
from processing.analyzer import ReviewAnalysisResult # For LLM summary structure
from openai_client import acall_openai_api, OPENAI_MODEL # Changed to async call
from constants import LANGUAGE_MAP # Import from constants

logger = logging.getLogger(__name__)

# --- Helper Async Function for Single Summary --- 
async def _generate_single_summary(
    input_text: str,
    context_description: str, # e.g., "language English", "overall"
    num_reviews: int,
    schema_string: str,
    model: str = OPENAI_MODEL,
    max_tokens: int = 1500
) -> Dict[str, Any]:
    """Helper async function to generate one summary using the LLM."""
    logger.info(f"Starting LLM summary generation for {context_description} ({num_reviews} reviews)...")
    summary_data = {"error": f"LLM Summary generation failed for {context_description} (Unknown reason)."}

    if not input_text.strip():
        logger.warning(f"No valid text input for LLM summary for {context_description}.")
        return {"error": f"No valid text input for summary ({context_description})."}

    # Define prompt (using passed schema string)
    prompt = [
        {
            "role": "system",
            "content": f"""You are an expert game analyst. Summarize the key points from the following batch of Steam reviews, derived from {context_description}.
Focus on overall sentiment, common positive/negative themes, feature requests, and bug reports identified within THIS BATCH of reviews.
**IMPORTANT: Respond *only* with a valid JSON object adhering strictly to the following JSON schema. Do not include any text outside the JSON object:**
```json
{schema_string}
```
If a category has no relevant information in this batch, provide an empty list `[]` or `null`."""
        },
        {
            "role": "user",
            "content": f"Summarize this batch of {num_reviews} translated Steam reviews ({context_description}):\n\n{input_text}"
        }
    ]

    try:
        summary_response_text = await acall_openai_api(
            prompt=prompt,
            model=model,
            temperature=0.3,
            max_tokens=max_tokens
        )

        if summary_response_text and not summary_response_text.startswith("[REFUSAL"):
            try:
                json_start = summary_response_text.find('{')
                json_end = summary_response_text.rfind('}')
                if json_start != -1 and json_end != -1:
                    json_string = summary_response_text[json_start:json_end+1]
                    parsed_json = json.loads(json_string)
                    validated_data = ReviewAnalysisResult(**parsed_json)
                    summary_data = validated_data.model_dump()
                    logger.info(f"Successfully generated and validated summary for {context_description}.")
                else:
                    raise ValueError("No JSON object found in summary response.")
            except (json.JSONDecodeError, ValueError, ValidationError) as parse_err:
                logger.error(f"Failed to parse/validate summary JSON for {context_description}: {parse_err}\nRaw: {summary_response_text[:500]}...")
                summary_data = {"error": f"Failed to parse/validate summary JSON ({context_description})", "raw_response": summary_response_text}
        elif summary_response_text and summary_response_text.startswith("[REFUSAL"):
            logger.warning(f"Summary request refused for {context_description}: {summary_response_text}")
            summary_data = {"error": f"Summary request refused ({context_description})", "refusal_message": summary_response_text}
        else:
            logger.warning(f"LLM summary call failed for {context_description} (returned None/empty)." )
            summary_data = {"error": f"LLM summary call failed ({context_description}) (returned None/empty)."}

    except Exception as api_err:
        # Catching exceptions from acall_openai_api (already logged there)
        # Or potential issues within this helper itself
        logger.exception(f"Error during LLM call task for {context_description}: {api_err}")
        summary_data = {"error": f"Exception during LLM call task for {context_description}."}

    return summary_data

# --- Main Report Generation Function (Now Async) ---
async def generate_summary_report(app_id: int, start_timestamp: int) -> bytes:
    """Generates the Excel summary report asynchronously."""
    logger.info(f"[Async] Generating summary report for app {app_id} since timestamp {start_timestamp}")
    output = io.BytesIO()
    db_session_gen = get_db()
    db = next(db_session_gen)

    try:
        # --- Step 1: Fetch and Prepare Data (Sync) ---
        logger.info(f"[Async] Fetching reviews for app {app_id} since {start_timestamp}...")
        reviews = crud.get_reviews_for_app_since(db, app_id, start_timestamp)

        if not reviews:
            logger.warning(f"[Async] No reviews found for app {app_id} since {start_timestamp}. Returning empty report.")
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame([{"Status": f"No reviews found for App ID {app_id} since timestamp {start_timestamp}"}]).to_excel(writer, sheet_name="Status", index=False)
            output.seek(0)
            return output.getvalue()

        logger.info(f"[Async] Fetched {len(reviews)} reviews for report generation.")
        distinct_languages = crud.get_distinct_languages_for_app_since(db, app_id, start_timestamp)
        logger.info(f"[Async] Found distinct languages in results: {distinct_languages}")

        reviews_df = pd.DataFrame([r.to_dict() for r in reviews])
        if 'author' in reviews_df.columns:
            try:
                 author_df = pd.json_normalize(reviews_df['author'])
                 author_df.columns = [f"author_{col}" for col in author_df.columns]
                 reviews_df = pd.concat([reviews_df.drop(columns=['author']), author_df], axis=1)
            except Exception as e:
                 logger.error(f"[Async] Error flattening author data in DataFrame: {e}")

        # Timestamp conversion (remains synchronous)
        timestamp_cols = ['timestamp_created', 'timestamp_updated', 'timestamp_dev_responded', 'author_last_played']
        for col in timestamp_cols:
            if col in reviews_df.columns:
                reviews_df[col] = pd.to_datetime(reviews_df[col], unit='s', errors='coerce', origin='unix')
                try:
                    if reviews_df[col].dt.tz is None:
                        reviews_df[col] = reviews_df[col].dt.tz_localize('UTC')
                    else:
                        reviews_df[col] = reviews_df[col].dt.tz_convert('UTC')
                    reviews_df[col] = reviews_df[col].dt.strftime('%Y-%m-%d %H:%M:%S %Z')
                except Exception as fmt_err:
                    logger.warning(f"[Async] Could not format datetime column {col} to string: {fmt_err}. Leaving as objects.")
        logger.info("[Async] Converted and formatted timestamp columns to strings.")

        # --- Step 2: Prepare and Run LLM Tasks Concurrently (Async) ---
        tasks = []
        language_data_map = {} # Store DFs and inputs temporarily

        # Prepare JSON schema once
        try:
            json_schema_string = json.dumps(ReviewAnalysisResult.model_json_schema(mode='serialization'), indent=2)
        except Exception as schema_err:
            logger.error(f"[Async] Failed to generate JSON schema for prompt: {schema_err}")
            # Cannot proceed without schema
            raise ValueError(f"Failed to generate JSON schema for prompts: {schema_err}") from schema_err

        # Prepare tasks for each language
        logger.info("[Async] Preparing per-language summary tasks...")
        for lang_code in distinct_languages:
            lang_name = LANGUAGE_MAP.get(lang_code, lang_code)
            lang_df = reviews_df[reviews_df['original_language'] == lang_code].copy()
            if lang_df.empty:
                logger.warning(f"[Async] Skipping language {lang_code}, no reviews found after filtering.")
                language_data_map[lang_code] = {'df': lang_df, 'summary_result': {"error": "No reviews for this language."}}
                continue

            texts_for_summary = []
            for _, row in lang_df.iterrows():
                text = row.get('english_translation')
                if text and isinstance(text, str) and not text.startswith('[Translation') and not text.startswith('[REFUSAL'):
                    texts_for_summary.append(f"Review (ID: {row.get('recommendationid')}): {text}")
                elif row.get('original_language') == 'english' and row.get('original_review_text'):
                    texts_for_summary.append(f"Review (ID: {row.get('recommendationid')}): {row.get('original_review_text')}")

            lang_summary_input_text = "\n---\n".join(texts_for_summary[:200])
            language_data_map[lang_code] = {'df': lang_df} # Store df for later writing

            if lang_summary_input_text.strip():
                task = _generate_single_summary(
                    input_text=lang_summary_input_text,
                    context_description=f"language {lang_name} ({lang_code})",
                    num_reviews=len(texts_for_summary),
                    schema_string=json_schema_string,
                    max_tokens=1500
                )
                tasks.append(task)
                language_data_map[lang_code]['task_index'] = len(tasks) - 1 # Map lang to its task index
            else:
                 logger.warning(f"[Async] No text for {lang_name} summary task.")
                 language_data_map[lang_code]['summary_result'] = {"error": f"No valid text input for summary ({lang_name})."}

        # Prepare task for overall summary
        logger.info("[Async] Preparing overall summary task...")
        overall_texts_for_summary = []
        for _, row in reviews_df.iterrows():
            text = row.get('english_translation')
            if text and isinstance(text, str) and not text.startswith('[Translation') and not text.startswith('[REFUSAL'):
                overall_texts_for_summary.append(f"Review (Lang: {row.get('original_language')}, ID: {row.get('recommendationid')}): {text}")
            elif row.get('original_language') == 'english' and row.get('original_review_text'):
                overall_texts_for_summary.append(f"Review (Lang: {row.get('original_language')}, ID: {row.get('recommendationid')}): {row.get('original_review_text')}")

        overall_summary_input_text = "\n---\n".join(overall_texts_for_summary[:300])
        overall_task_index = -1 # Keep track of the overall task

        if overall_summary_input_text.strip():
            overall_task = _generate_single_summary(
                input_text=overall_summary_input_text,
                context_description="overall",
                num_reviews=len(overall_texts_for_summary),
                schema_string=json_schema_string,
                max_tokens=2000
            )
            tasks.append(overall_task)
            overall_task_index = len(tasks) - 1
            overall_summary_result = None # Will be populated after gather
        else:
            logger.warning("[Async] No text for overall summary task.")
            overall_summary_result = {"error": "No valid text input for overall summary."}

        # Execute all tasks concurrently
        if tasks:
            logger.info(f"[Async] Executing {len(tasks)} summary tasks concurrently using asyncio.gather...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"[Async] asyncio.gather finished. Processing {len(results)} results...")

            # --- Step 3: Process Results (Sync) ---
            # Populate results back into language_data_map and overall_summary_result
            for lang_code, data in language_data_map.items():
                if 'task_index' in data:
                    task_index = data['task_index']
                    result = results[task_index]
                    if isinstance(result, Exception):
                         logger.error(f"[Async] Task for language {lang_code} failed with exception: {result}")
                         language_data_map[lang_code]['summary_result'] = {"error": f"Task execution failed: {result}"}
                    else:
                         language_data_map[lang_code]['summary_result'] = result
                # If no task_index, it means summary_result was already set (e.g., no input text)
            
            if overall_task_index != -1:
                 overall_result = results[overall_task_index]
                 if isinstance(overall_result, Exception):
                     logger.error(f"[Async] Overall summary task failed with exception: {overall_result}")
                     overall_summary_result = {"error": f"Overall task execution failed: {overall_result}"}
                 else:
                     overall_summary_result = overall_result
            # If overall_task_index is -1, overall_summary_result was set earlier (no input text)

        else:
             logger.warning("[Async] No summary tasks were created to run.")
             # Ensure overall_summary_result is initialized if it wasn't set due to no input
             if overall_task_index == -1 and overall_summary_result is None:
                 overall_summary_result = {"error": "No summary tasks run."}

        # --- Step 4: Write Excel File (Sync) ---
        logger.info("[Async] Writing results to Excel...")
        with pd.ExcelWriter(output, engine='openpyxl') as writer:

            # --- Step 4.1: Write Overall Summary Sheet FIRST ---
            logger.info("[Async] Writing Overall Summary sheet...")
            overall_summary_sheet_name = "Summary_Overall"
            current_row_overall = 0

            overall_total = len(reviews_df)
            overall_pos = len(reviews_df[reviews_df['voted_up'] == True]) if overall_total > 0 else 0
            overall_neg = overall_total - overall_pos
            overall_pos_pct = (overall_pos / overall_total) * 100 if overall_total > 0 else 0

            # Calculate language counts *before* defining the overall_stats_data
            lang_counts = {
                lang: len(data.get('df', pd.DataFrame()))
                for lang, data in language_data_map.items()
            }

            overall_stats_data = {
                'Metric': [
                    'Total Reviews Analyzed',
                    'Positive Reviews',
                    'Negative Reviews',
                    'Positive Percentage'
                # Get language names based on original distinct_languages order for the stats table
                ] + [f"{LANGUAGE_MAP.get(lang, lang)} Count" for lang in distinct_languages],
                'Value': [
                    overall_total,
                    overall_pos,
                    overall_neg,
                    f"{overall_pos_pct:.1f}%"
                # Use the calculated counts based on original distinct_languages order
                ] + [lang_counts.get(lang, 0) for lang in distinct_languages]
            }
            overall_stats_df = pd.DataFrame(overall_stats_data)
            overall_stats_df.to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
            current_row_overall += len(overall_stats_df) + 2

            # Write the AI analysis part for Overall Summary
            if isinstance(overall_summary_result, dict):
                if 'error' in overall_summary_result:
                    pd.DataFrame([overall_summary_result.get('error')], columns=['Analysis Error']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
                    current_row_overall += 2
                    if 'raw_response' in overall_summary_result:
                         pd.DataFrame([overall_summary_result['raw_response']], columns=['Raw AI Response']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
                    elif 'refusal_message' in overall_summary_result:
                         pd.DataFrame([overall_summary_result['refusal_message']], columns=['Refusal Message']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
                else:
                    for key, value in overall_summary_result.items():
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
                        current_row_overall += 1
            else:
                pd.DataFrame(["Overall analysis data invalid or task failed"], columns=['Status']).to_excel(writer, sheet_name=overall_summary_sheet_name, index=False, startrow=current_row_overall)
            logger.info(f"[Async] Written sheet {overall_summary_sheet_name}.")


            # --- Step 4.2: Sort Languages by Review Count ---
            # Use the lang_counts calculated earlier
            sorted_lang_codes = sorted(lang_counts.keys(), key=lambda lang: lang_counts[lang], reverse=True)
            logger.info(f"[Async] Languages sorted by review count (desc): {sorted_lang_codes}")

            # --- Step 4.3: Write Per-Language Sheets (Sorted) ---
            for lang_code in sorted_lang_codes: # Iterate through sorted list
                # Retrieve the data for this language
                data = language_data_map.get(lang_code)
                if not data:
                    logger.warning(f"[Async] Could not find data for language {lang_code} during sorted writing, skipping.")
                    continue # Should not happen if lang_counts was populated correctly

                lang_name = LANGUAGE_MAP.get(lang_code, lang_code)
                lang_df = data.get('df')
                lang_summary_data = data.get('summary_result', {"error": f"Summary data missing for {lang_name}."})

                # Check if df is None or empty (handle potential edge case where df wasn't stored)
                if lang_df is None or lang_df.empty:
                    logger.info(f"[Async] Skipping sheet writing for {lang_name} as DataFrame is empty or missing.")
                    continue # Don't write sheets if no reviews existed or df is missing

                logger.info(f"[Async] Writing Excel sheets for {lang_name} ({lang_code})...")
                summary_sheet_name = f"Summary_{lang_code}"
                reviews_sheet_name = f"Reviews_{lang_code}"

                # --- Write Summary Sheet (Copied/adapted from original, uses lang_summary_data) ---
                current_row = 0
                # Use the pre-calculated count for stats
                lang_total = lang_counts.get(lang_code, 0)
                # Calculate pos/neg directly from the lang_df if it exists
                lang_pos = len(lang_df[lang_df['voted_up'] == True]) if not lang_df.empty else 0
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
                        if 'raw_response' in lang_summary_data:
                             pd.DataFrame([lang_summary_data['raw_response']], columns=['Raw AI Response']).to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)
                        elif 'refusal_message' in lang_summary_data:
                             pd.DataFrame([lang_summary_data['refusal_message']], columns=['Refusal Message']).to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)
                    else:
                        for key, value in lang_summary_data.items():
                            section_title = key.replace('_', ' ').title()
                            pd.DataFrame([section_title], columns=['Analysis Section']).to_excel(writer, sheet_name=summary_sheet_name, index=False, header=False, startrow=current_row)
                            current_row += 1
                            if isinstance(value, list):
                                pd.DataFrame(value, columns=['Details']).to_excel(writer, sheet_name=summary_sheet_name, index=False, header=False, startrow=current_row)
                                current_row += len(value) if value else 1
                            elif value is not None:
                                pd.DataFrame([str(value)], columns=['Details']).to_excel(writer, sheet_name=summary_sheet_name, index=False, header=False, startrow=current_row)
                                current_row += 1
                            else:
                                current_row += 1
                            current_row += 1
                else:
                    pd.DataFrame(["Analysis data invalid"], columns=['Status']).to_excel(writer, sheet_name=summary_sheet_name, index=False, startrow=current_row)

                # --- Write Reviews Sheet (Copied/adapted from original) ---
                # No change needed here, still uses lang_df
                review_cols_order = [
                    'recommendationid', 'voted_up', 'sentiment',
                    'original_review_text', 'english_translation',
                    'timestamp_created', 'timestamp_updated',
                    'votes_up', 'votes_funny', 'weighted_vote_score', 'comment_count',
                    'author_steamid', 'author_playtime_forever', 'author_playtime_at_review',
                    'steam_purchase', 'received_for_free', 'written_during_early_access',
                    'developer_response'
                ]
                lang_df['sentiment'] = lang_df['voted_up'].apply(lambda x: 'Positive' if x else 'Negative')
                lang_df_cols = [col for col in review_cols_order if col in lang_df.columns]
                lang_df_ordered = lang_df[lang_df_cols]
                lang_df_ordered.to_excel(writer, sheet_name=reviews_sheet_name, index=False)
                logger.info(f"[Async] Written sheets {summary_sheet_name} and {reviews_sheet_name}.")

            # Overall summary sheet writing is moved BEFORE this loop

        logger.info("[Async] Excel writing finished. Report generation completed.")

    except Exception as e:
        logger.exception(f"[Async] Error during async report generation: {e}")
        # Rewrite the Excel file to indicate the error
        output.seek(0)
        output.truncate()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame([{"Error": f"Report Generation Failed: {str(e)}"}]).to_excel(writer, sheet_name="Error", index=False)
    finally:
        logger.info("[Async] Closing database session for report generation.")
        try:
            next(db_session_gen)
        except StopIteration:
            pass
        except Exception as e:
             logger.error(f"[Async] Error closing DB session: {e}")

    output.seek(0)
    return output.getvalue()

if __name__ == '__main__':
    # Example usage (for testing purposes)
    # Make sure DB is running and has data
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    logger.info("Running excel_generator directly for testing (ASYNC version)...")
    TEST_APP_ID = 3228590
    import datetime
    start_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    TEST_START_TIMESTAMP = int(start_date.timestamp())

    logger.info(f"Using App ID: {TEST_APP_ID}, Start Timestamp: {TEST_START_TIMESTAMP} ({start_date.date()})")

    async def main_test():
        try:
            start_time = asyncio.get_event_loop().time()
            logger.info("Calling async generate_summary_report...")
            report_bytes = await generate_summary_report(TEST_APP_ID, TEST_START_TIMESTAMP)
            end_time = asyncio.get_event_loop().time()
            logger.info(f"Async report generation took {end_time - start_time:.2f} seconds.")
            output_filename = f"test_report_async_{TEST_APP_ID}_{start_date.strftime('%Y%m%d')}.xlsx"
            with open(output_filename, 'wb') as f:
                f.write(report_bytes)
            logger.info(f"Test report saved to: {output_filename}")
        except Exception as e:
            logger.exception(f"Error generating async test report: {e}")

    # Run the async main function
    asyncio.run(main_test()) 