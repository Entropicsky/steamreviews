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
    max_tokens: int, # Removed default, will be passed in call
    model: str = OPENAI_MODEL
) -> Dict[str, Any]:
    """Helper async function to generate one summary using the LLM."""
    logger.info(f"Starting LLM summary generation for {context_description} ({num_reviews} reviews) with max_tokens={max_tokens}...")
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
**IMPORTANT: Respond *only* with a valid JSON object adhering strictly to the following JSON schema. Do not include any text outside the JSON object.**
**IMPORTANT: All textual summaries within the JSON response (like themes, requests, sentiment descriptions) MUST be in English, regardless of the input review language.**
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
            max_tokens=max_tokens # Use passed value
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
    """Generates the Excel summary report asynchronously with consolidated summary and styling."""
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
            # Use xlsxwriter even for the empty report for consistency
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
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

        # --- Timestamp processing (Handle potential errors) ---
        timestamp_cols = ['timestamp_created', 'timestamp_updated', 'timestamp_dev_responded', 'author_last_played']
        for col in timestamp_cols:
            if col in reviews_df.columns:
                converted_timestamps = []
                for timestamp in reviews_df[col]:
                    try:
                        # Attempt conversion for each timestamp individually
                        if pd.isna(timestamp):
                             converted_timestamps.append(pd.NaT) # Handle existing NaNs
                             continue
                        # Convert valid numbers
                        dt_obj = pd.to_datetime(timestamp, unit='s', errors='raise', origin='unix')
                        # Attempt to localize to UTC
                        if dt_obj.tz is None:
                            dt_obj = dt_obj.tz_localize('UTC')
                        else:
                            dt_obj = dt_obj.tz_convert('UTC')
                        converted_timestamps.append(dt_obj)
                    except (OverflowError, ValueError, FloatingPointError) as e:
                        # Catch specific numerical/conversion errors
                        logger.warning(f"[Timestamp Conversion] Error converting timestamp '{timestamp}' in column '{col}': {e}. Setting to NaT.")
                        converted_timestamps.append(pd.NaT) # Set to Not a Time on error
                    except Exception as e:
                        # Catch any other unexpected errors during conversion/localization
                        logger.error(f"[Timestamp Conversion] Unexpected error converting timestamp '{timestamp}' in column '{col}': {e}. Setting to NaT.")
                        converted_timestamps.append(pd.NaT)
                
                # Assign the list of converted timestamps back to the DataFrame column
                reviews_df[col] = pd.Series(converted_timestamps, index=reviews_df.index, dtype='datetime64[ns, UTC]')
                logger.info(f"[Async] Processed timestamp column '{col}' with individual error handling.")
            # else: Column not present, skip
        
        # Add Language Name column to main DataFrame for the All Reviews sheet
        reviews_df['Language Name'] = reviews_df['original_language'].map(lambda x: LANGUAGE_MAP.get(x, x))

        # --- Step 2: Prepare and Run LLM Tasks Concurrently (Async) ---
        tasks = []
        language_data_map = {} # Store DFs AND results temporarily

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
            language_data_map[lang_code] = {'df': lang_df}
            
            if lang_df.empty:
                logger.warning(f"[Async] Skipping language {lang_code}, no reviews found after filtering.")
                language_data_map[lang_code]['summary_result'] = {"error": "No reviews for this language."}
                continue

            texts_for_summary = []
            for _, row in lang_df.iterrows():
                # Try English translation first
                text_to_use = row.get('english_translation')
                is_translation_valid = text_to_use and isinstance(text_to_use, str) and not text_to_use.startswith('[Translation') and not text_to_use.startswith('[REFUSAL')
                
                if is_translation_valid:
                    texts_for_summary.append(f"Review (ID: {row.get('recommendationid')}): {text_to_use}")
                else:
                    # Fallback to original text if translation invalid or missing
                    original_text = row.get('original_review_text')
                    if original_text and isinstance(original_text, str):
                        texts_for_summary.append(f"Review (ID: {row.get('recommendationid')}): {original_text}")
                    # else: log warning maybe? Review has no usable text.

            lang_summary_input_text = "\n---\n".join(texts_for_summary)
            language_data_map[lang_code]['task_index'] = len(tasks) - 1 # Map lang to its task index

            if lang_summary_input_text.strip():
                task = _generate_single_summary(
                    input_text=lang_summary_input_text,
                    context_description=f"language {lang_name} ({lang_code})",
                    num_reviews=len(texts_for_summary),
                    schema_string=json_schema_string,
                    max_tokens=3000 # Increased max_tokens for per-language
                )
                tasks.append(task)
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

        overall_summary_input_text = "\n---\n".join(overall_texts_for_summary)
        overall_task_index = -1 # Keep track of the overall task

        if overall_summary_input_text.strip():
            overall_task = _generate_single_summary(
                input_text=overall_summary_input_text,
                context_description="overall",
                num_reviews=len(overall_texts_for_summary),
                schema_string=json_schema_string,
                max_tokens=4000 # Increased max_tokens for overall
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

        # --- Step 4: Write Excel File (Sync using xlsxwriter) ---
        logger.info("[Async] Writing results to Excel with new consolidated structure...")
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book

            # --- Define Formats (Adding valign: top where needed) ---
            fmt_sheet_title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left', 'valign': 'top'})
            fmt_section_title = workbook.add_format({'bold': True, 'font_size': 12, 'bottom': 1, 'valign': 'top'})
            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1, 'align': 'center', 'valign': 'top', 'text_wrap': True})
            fmt_header_left = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1, 'align': 'left', 'valign': 'top'})
            fmt_percent = workbook.add_format({'num_format': '0.0%', 'border': 1, 'align': 'right', 'valign': 'top'})
            fmt_number = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'right', 'valign': 'top'})
            fmt_text_wrap = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1})
            fmt_text_left_border = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'top'})
            fmt_date = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss', 'align': 'left', 'valign': 'top'})
            fmt_error = workbook.add_format({'font_color': 'red', 'valign': 'top'})
            fmt_bold = workbook.add_format({'bold': True, 'valign': 'top'})
            fmt_default_border = workbook.add_format({'border': 1, 'valign': 'top'})

            # Helper function to adjust column widths
            def adjust_column_widths(df, worksheet, offset=0):
                for idx, col in enumerate(df.columns):
                    series = df[col]
                    # Header length
                    header_len = len(str(series.name))
                    # Max content length (handle potential NAs)
                    content_len = series.astype(str).map(len).max()
                    if pd.isna(content_len):
                        content_len = 0
                    
                    max_len = max(header_len, int(content_len)) + 1
                    # Clamp max width
                    max_len = min(max_len, 60)
                    worksheet.set_column(idx + offset, idx + offset, max_len)
            
            # Helper function to write AI analysis data (lists or strings)
            def write_analysis_cell(worksheet, row, col, data, cell_format):
                 if isinstance(data, list) and data:
                     # Join list items with newline for multiline cell
                     worksheet.write_string(row, col, '\n'.join(map(str, data)), cell_format)
                 elif data and not isinstance(data, list):
                     worksheet.write_string(row, col, str(data), cell_format)
                 else:
                     worksheet.write_string(row, col, '-', cell_format) # Placeholder for empty/null

            # --- Step 4.1: Prepare Data for Consolidated Summary Sheet ---
            summary_data_list = []
            lang_counts = {} # Recalculate counts for sorting
            lang_pos_counts = {}
            lang_neg_counts = {}

            # Process individual languages first
            for lang_code, data in language_data_map.items():
                df = data.get('df')
                count = len(df) if df is not None else 0
                lang_counts[lang_code] = count
                pos = 0
                neg = 0
                if count > 0 and df is not None:
                    pos = len(df[df['voted_up'] == True])
                    neg = count - pos
                lang_pos_counts[lang_code] = pos
                lang_neg_counts[lang_code] = neg
                # Explicitly cast to float before division/multiplication
                pct = (float(pos) / float(count)) * 100.0 if count > 0 else 0.0
                
                ai_summary = data.get('summary_result', {})
                if not isinstance(ai_summary, dict):
                     ai_summary = {"error": "Invalid AI summary format received."}

                lang_name = LANGUAGE_MAP.get(lang_code, lang_code)
                summary_data_list.append({
                    'Language': lang_name,
                    'Negative Reviews': neg,
                    'Positive Reviews': pos,
                    'Total Reviews': count,
                    '% Positive': pct / 100.0, # Store as float
                    'Analyzed Sentiment': ai_summary.get('analyzed_sentiment'),
                    'Positive Themes': ai_summary.get('positive_themes'),
                    'Negative Themes': ai_summary.get('negative_themes'),
                    'Feature Requests': ai_summary.get('feature_requests'),
                    'Bug Reports': ai_summary.get('bug_reports'),
                    '_sort_key': count # Add temporary key for sorting
                })

            # Sort languages by review count (descending)
            sorted_summary_data = sorted(summary_data_list, key=lambda x: x['_sort_key'], reverse=True)

            # Prepare "Total / All" row data
            overall_total = sum(lang_counts.values())
            overall_pos = sum(lang_pos_counts.values())
            overall_neg = sum(lang_neg_counts.values())
            # Explicitly cast to float before division/multiplication
            overall_pct = (float(overall_pos) / float(overall_total)) * 100.0 if overall_total > 0 else 0.0
            ai_summary_overall = overall_summary_result if isinstance(overall_summary_result, dict) else {"error": "Invalid AI summary format."}

            total_row_data = {
                'Language': 'Total / All',
                'Negative Reviews': overall_neg,
                'Positive Reviews': overall_pos,
                'Total Reviews': overall_total,
                '% Positive': overall_pct / 100.0,
                'Analyzed Sentiment': ai_summary_overall.get('analyzed_sentiment'),
                'Positive Themes': ai_summary_overall.get('positive_themes'),
                'Negative Themes': ai_summary_overall.get('negative_themes'),
                'Feature Requests': ai_summary_overall.get('feature_requests'),
                'Bug Reports': ai_summary_overall.get('bug_reports'),
                 # No sort key needed here
            }

            # Define column order for the summary sheet
            summary_columns = ['Language', 'Negative Reviews', 'Positive Reviews', 'Total Reviews', '% Positive',
                               'Analyzed Sentiment', 'Positive Themes', 'Negative Themes', 'Feature Requests', 'Bug Reports']

            # --- Step 4.2: Write Consolidated Summary Sheet --- 
            summary_sheet_name = "Summary"
            logger.info(f"[Async] Writing sheet: {summary_sheet_name}")
            worksheet_summary = workbook.add_worksheet(summary_sheet_name)
            worksheet_summary.write('A1', summary_sheet_name, fmt_sheet_title)
            current_row_summary = 2 # Start below title

            # Write Headers
            for c_idx, col_name in enumerate(summary_columns):
                worksheet_summary.write(current_row_summary, c_idx, col_name, fmt_header)
            current_row_summary += 1

            # Write Total Row
            for c_idx, col_name in enumerate(summary_columns):
                value = total_row_data.get(col_name)
                fmt = fmt_default_border # Default format
                if col_name == 'Language':
                    fmt = fmt_header_left # Header style for the row label
                    worksheet_summary.write_string(current_row_summary, c_idx, str(value) if value is not None else '-', fmt)
                elif col_name == '% Positive':
                    fmt = fmt_percent
                    worksheet_summary.write_number(current_row_summary, c_idx, value if value is not None else 0, fmt)
                elif col_name in ['Negative Reviews', 'Positive Reviews', 'Total Reviews']:
                    fmt = fmt_number
                    worksheet_summary.write_number(current_row_summary, c_idx, value if value is not None else 0, fmt)
                else: # AI analysis columns
                    fmt = fmt_text_wrap
                    write_analysis_cell(worksheet_summary, current_row_summary, c_idx, value, fmt)
            current_row_summary += 1

            # Write Blank Separator Row (optional, for visual spacing)
            worksheet_summary.set_row(current_row_summary, 10) # Make it a bit shorter
            current_row_summary += 1 

            # Write Individual Language Rows
            for lang_data in sorted_summary_data:
                 for c_idx, col_name in enumerate(summary_columns):
                     value = lang_data.get(col_name)
                     fmt = fmt_default_border # Default format
                     if col_name == 'Language':
                         fmt = fmt_bold # Just bold for language name
                         worksheet_summary.write_string(current_row_summary, c_idx, str(value) if value is not None else '-', fmt)
                     elif col_name == '% Positive':
                         fmt = fmt_percent
                         worksheet_summary.write_number(current_row_summary, c_idx, value if value is not None else 0, fmt)
                     elif col_name in ['Negative Reviews', 'Positive Reviews', 'Total Reviews']:
                         fmt = fmt_number
                         worksheet_summary.write_number(current_row_summary, c_idx, value if value is not None else 0, fmt)
                     else: # AI analysis columns
                         fmt = fmt_text_wrap
                         write_analysis_cell(worksheet_summary, current_row_summary, c_idx, value, fmt)
                 current_row_summary += 1
                 # Optional: Add blank row between languages
                 # worksheet_summary.set_row(current_row_summary, 10)
                 # current_row_summary += 1 

            # Adjust column widths for Summary sheet
            worksheet_summary.set_column('A:A', 25) # Language
            worksheet_summary.set_column('B:D', 15) # Counts
            worksheet_summary.set_column('E:E', 12) # Percent
            worksheet_summary.set_column('F:J', 45) # AI Analysis columns - wider and wrapped
            worksheet_summary.freeze_panes(3, 1) # Freeze header row and language column
            logger.info(f"[Async] Finished writing sheet: {summary_sheet_name}")

            # --- Step 4.3: Write "Reviews_All" Sheet ---
            reviews_all_sheet_name = "Reviews_All"
            logger.info(f"[Async] Writing sheet: {reviews_all_sheet_name}")
            worksheet_reviews_all = workbook.add_worksheet(reviews_all_sheet_name)
            worksheet_reviews_all.write('A1', reviews_all_sheet_name, fmt_sheet_title)
            current_row_reviews_all = 2

            # Define column order, bringing Language Name near the start
            # Add LLM analysis columns
            all_reviews_cols_order = [
                'recommendationid', 'Language Name', 'voted_up', 'sentiment',
                'original_review_text', 'english_translation',
                'timestamp_created', 'timestamp_updated',
                'votes_up', 'votes_funny', 'weighted_vote_score', 'comment_count',
                # LLM Analysis Fields
                'analysis_status', 'analyzed_sentiment',
                'positive_themes', 'negative_themes', 'feature_requests', 'bug_reports',
                'llm_analysis_model', 'llm_analysis_timestamp',
                # Author Fields
                'author_steamid', 'author_playtime_forever', 'author_playtime_at_review',
                # Other Review Fields
                'steam_purchase', 'received_for_free', 'written_during_early_access',
                'developer_response', 'original_language'
            ]
            reviews_df['sentiment'] = reviews_df['voted_up'].apply(lambda x: 'Positive' if x else 'Negative')
            reviews_df_cols = [col for col in all_reviews_cols_order if col in reviews_df.columns]
            all_reviews_df_ordered = reviews_df[reviews_df_cols].copy()

            # Make datetime columns timezone-naive for xlsxwriter
            # Include llm_analysis_timestamp here
            datetime_cols_to_convert = ['timestamp_created', 'timestamp_updated', 'llm_analysis_timestamp']
            for dt_col in datetime_cols_to_convert:
                 if dt_col in all_reviews_df_ordered.columns and pd.api.types.is_datetime64_any_dtype(all_reviews_df_ordered[dt_col]):
                     try:
                         if all_reviews_df_ordered[dt_col].dt.tz is not None:
                              all_reviews_df_ordered[dt_col] = all_reviews_df_ordered[dt_col].dt.tz_localize(None)
                     except Exception as tz_err:
                         logger.warning(f"Could not make column {dt_col} timezone-naive for All Reviews: {tz_err}. Exporting as string.")
                         all_reviews_df_ordered[dt_col] = all_reviews_df_ordered[dt_col].astype(str)

            # Write DataFrame to Excel
            all_reviews_df_ordered.to_excel(writer, sheet_name=reviews_all_sheet_name, index=False, startrow=current_row_reviews_all)

            # Apply formatting to All Reviews sheet headers
            for c_idx, value in enumerate(all_reviews_df_ordered.columns.values):
                worksheet_reviews_all.write(current_row_reviews_all, c_idx, value, fmt_header)
            
            # Apply specific formats (dates, text wrap)
            # Include llm_analysis_timestamp for date formatting
            date_format_cols = ['timestamp_created', 'timestamp_updated', 'llm_analysis_timestamp']
            for dt_col_name in date_format_cols:
                if dt_col_name in all_reviews_df_ordered.columns:
                     dt_col_idx = all_reviews_df_ordered.columns.get_loc(dt_col_name)
                     if pd.api.types.is_datetime64_any_dtype(all_reviews_df_ordered[dt_col_name]):
                         worksheet_reviews_all.set_column(dt_col_idx, dt_col_idx, 20, fmt_date)
                     else:
                         worksheet_reviews_all.set_column(dt_col_idx, dt_col_idx, 20)
            text_wrap_cols = ['original_review_text', 'english_translation', 'developer_response', 
                              'positive_themes', 'negative_themes', 'feature_requests', 'bug_reports']
            for txt_col_name in text_wrap_cols:
                if txt_col_name in all_reviews_df_ordered.columns:
                    txt_col_idx = all_reviews_df_ordered.columns.get_loc(txt_col_name)
                    worksheet_reviews_all.set_column(txt_col_idx, txt_col_idx, 50, fmt_text_wrap)

            adjust_column_widths(all_reviews_df_ordered, worksheet_reviews_all)
            worksheet_reviews_all.freeze_panes(3, 0) # Freeze header row
            logger.info(f"[Async] Finished writing sheet: {reviews_all_sheet_name}")

            # --- Step 4.4: Write Individual Language Review Sheets (Sorted) ---
            # Use the same sorted list as the summary sheet for consistent ordering
            sorted_sheet_lang_codes = [d['Language'] for d in sorted_summary_data] # Get sorted language names
            logger.info(f"[Async] Languages sorted for individual review sheets: {sorted_sheet_lang_codes}")
            
            for lang_name in sorted_sheet_lang_codes:
                # Find the original lang_code and data using lang_name
                lang_code = next((lc for lc, name in LANGUAGE_MAP.items() if name == lang_name), lang_name) # Fallback if not in map
                data = language_data_map.get(lang_code)
                
                if not data:
                    logger.warning(f"[Async] Could not find data for language {lang_name} ({lang_code}) for individual review sheet, skipping.")
                    continue

                lang_df = data.get('df')
                if lang_df is None or lang_df.empty:
                    logger.info(f"[Async] Skipping individual review sheet for {lang_name} as DataFrame is empty or missing.")
                    continue

                # --- Create Sheet ---
                reviews_sheet_name = f"Reviews_{lang_code}"
                logger.info(f"[Async] Writing sheet: {reviews_sheet_name}...")
                worksheet_reviews = workbook.add_worksheet(reviews_sheet_name)
                worksheet_reviews.write('A1', reviews_sheet_name, fmt_sheet_title)
                current_row_reviews = 2

                # --- Prepare and Write DataFrame ---
                # Add LLM analysis columns to the order for individual sheets
                review_cols_order = [
                    'recommendationid', 'voted_up', 'sentiment',
                    'original_review_text', 'english_translation',
                    'timestamp_created', 'timestamp_updated',
                    'votes_up', 'votes_funny', 'weighted_vote_score', 'comment_count',
                    # LLM Analysis Fields
                    'analysis_status', 'analyzed_sentiment',
                    'positive_themes', 'negative_themes', 'feature_requests', 'bug_reports',
                    'llm_analysis_model', 'llm_analysis_timestamp',
                    # Author Fields
                    'author_steamid', 'author_playtime_forever', 'author_playtime_at_review',
                     # Other Review Fields
                    'steam_purchase', 'received_for_free', 'written_during_early_access',
                    'developer_response'
                    # 'original_language' is implicitly known for these sheets
                ]
                lang_df['sentiment'] = lang_df['voted_up'].apply(lambda x: 'Positive' if x else 'Negative')
                lang_df_cols = [col for col in review_cols_order if col in lang_df.columns]
                lang_df_ordered = lang_df[lang_df_cols].copy()

                # Convert datetime columns timezone-naive
                # Include llm_analysis_timestamp here
                datetime_cols_to_convert = ['timestamp_created', 'timestamp_updated', 'llm_analysis_timestamp']
                for dt_col in datetime_cols_to_convert:
                    if dt_col in lang_df_ordered.columns and pd.api.types.is_datetime64_any_dtype(lang_df_ordered[dt_col]):
                        try:
                            if lang_df_ordered[dt_col].dt.tz is not None:
                                lang_df_ordered[dt_col] = lang_df_ordered[dt_col].dt.tz_localize(None)
                        except Exception as tz_err:
                            logger.warning(f"Could not make column {dt_col} timezone-naive for {reviews_sheet_name}: {tz_err}. Exporting as string.")
                            lang_df_ordered[dt_col] = lang_df_ordered[dt_col].astype(str)

                lang_df_ordered.to_excel(writer, sheet_name=reviews_sheet_name, index=False, startrow=current_row_reviews)

                # --- Apply Formatting ---
                for c_idx, value in enumerate(lang_df_ordered.columns.values):
                    worksheet_reviews.write(current_row_reviews, c_idx, value, fmt_header)
                
                # Apply date formatting (include llm_analysis_timestamp)
                date_format_cols = ['timestamp_created', 'timestamp_updated', 'llm_analysis_timestamp']
                for dt_col_name in date_format_cols:
                    if dt_col_name in lang_df_ordered.columns:
                         dt_col_idx = lang_df_ordered.columns.get_loc(dt_col_name)
                         if pd.api.types.is_datetime64_any_dtype(lang_df_ordered[dt_col_name]):
                             worksheet_reviews.set_column(dt_col_idx, dt_col_idx, 20, fmt_date)
                         else:
                             worksheet_reviews.set_column(dt_col_idx, dt_col_idx, 20)
                
                # Apply text wrap (include LLM list columns)
                text_wrap_cols = ['original_review_text', 'english_translation', 'developer_response', 
                                  'positive_themes', 'negative_themes', 'feature_requests', 'bug_reports']
                for txt_col_name in text_wrap_cols:
                    if txt_col_name in lang_df_ordered.columns:
                        txt_col_idx = lang_df_ordered.columns.get_loc(txt_col_name)
                        worksheet_reviews.set_column(txt_col_idx, txt_col_idx, 50, fmt_text_wrap)
                adjust_column_widths(lang_df_ordered, worksheet_reviews)
                worksheet_reviews.freeze_panes(3, 0) # Freeze header row
                logger.info(f"[Async] Finished writing sheet {reviews_sheet_name}.")

        logger.info("[Async] Excel writing finished. Report generation completed.")

    except Exception as e:
        logger.exception(f"[Async] Error during async report generation: {e}")
        # Rewrite the Excel file to indicate the error (using xlsxwriter)
        output.seek(0)
        output.truncate()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            worksheet = workbook.add_worksheet("Error")
            fmt_error = workbook.add_format({'bold': True, 'font_color': 'red', 'align': 'center'})
            worksheet.merge_range('A1:D1', f"Report Generation Failed: {str(e)}", fmt_error)
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
            output_filename = f"test_report_consolidated_{TEST_APP_ID}_{start_date.strftime('%Y%m%d')}.xlsx"
            with open(output_filename, 'wb') as f:
                f.write(report_bytes)
            logger.info(f"Test report saved to: {output_filename}")
        except Exception as e:
            logger.exception(f"Error generating async test report: {e}")

    # Run the async main function
    asyncio.run(main_test()) 