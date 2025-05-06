# src/reporting/youtube_report_generator.py
import logging
import io
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

# Adjust path for imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database import crud_youtube as crud
from database.connection import get_db # If needed for direct testing

logger = logging.getLogger(__name__)

# Helper function to adjust column widths (similar to Steam report generator)
def adjust_column_widths(df, worksheet, offset=0, min_width=10, max_width=60):
    for idx, col in enumerate(df.columns):
        series = df[col]
        # Header length
        header_len = len(str(series.name))
        # Max content length (handle potential NAs and multi-line strings)
        try:
            content_len = series.astype(str).map(lambda x: max(len(line) for line in x.split('\n')) if pd.notna(x) else 0).max()
        except:
            content_len = 10 # Fallback
        
        max_len = max(header_len, int(content_len)) + 2 # Add padding
        # Clamp width
        width = max(min_width, min(max_len, max_width))
        worksheet.set_column(idx + offset, idx + offset, width)

async def generate_youtube_summary_report(db_session: Session, game_id: int, start_date: datetime, end_date: datetime) -> Optional[bytes]:
    """Generates an Excel summary report for YouTube feedback for a specific game and date range."""
    logger.info(f"Generating YouTube summary report for game {game_id} from {start_date} to {end_date}")
    output = io.BytesIO()

    try:
        # --- Step 1: Fetch Analyzed Feedback Data --- 
        logger.info(f"Fetching analyzed feedback data for game {game_id}...")
        # Using the existing CRUD function which joins necessary tables
        analyzed_feedback_data = crud.get_analyzed_feedback_for_game(db_session, game_id, start_date, end_date)

        if not analyzed_feedback_data:
            logger.warning(f"No analyzed YouTube feedback found for game {game_id} in the specified date range.")
            # Create a simple Excel file indicating no data
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                 pd.DataFrame([{"Status": f"No analyzed YouTube feedback found for Game ID {game_id} between {start_date.date()} and {end_date.date()}"}]).to_excel(writer, sheet_name="Status", index=False)
            output.seek(0)
            return output.getvalue()
        
        logger.info(f"Fetched {len(analyzed_feedback_data)} analyzed feedback records.")
        
        # Convert list of dicts to DataFrame
        feedback_df = pd.DataFrame(analyzed_feedback_data)

        # --- Step 2: Prepare Data & Group by Influencer --- 
        # (Potentially normalize influencer/channel names if needed)
        influencers = feedback_df['influencer_name'].unique()
        logger.info(f"Found feedback from {len(influencers)} influencers: {list(influencers)}")

        # --- Step 3: Write Excel File (using xlsxwriter) --- 
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            # --- Define Formats --- 
            fmt_sheet_title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left', 'valign': 'top'})
            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1, 'align': 'center', 'valign': 'top', 'text_wrap': True})
            fmt_text_wrap_top = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1, 'align': 'left'})
            fmt_date_top = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm', 'valign': 'top', 'border': 1, 'align': 'left'})
            fmt_text_top_border = workbook.add_format({'valign': 'top', 'border': 1, 'align': 'left'})
            fmt_number_top_border = workbook.add_format({'num_format': '#,##0', 'valign': 'top', 'border': 1, 'align': 'right'})
            fmt_bold_top = workbook.add_format({'bold': True, 'valign': 'top', 'border': 1})
            fmt_default_top_border = workbook.add_format({'valign': 'top', 'border': 1}) # Default align is left

            # --- Step 3.1: Write Summary Sheet ---
            summary_sheet_name = "Summary"
            logger.info(f"Writing sheet: {summary_sheet_name}")
            worksheet_summary = workbook.add_worksheet(summary_sheet_name)
            worksheet_summary.write('A1', f"YouTube Feedback Summary for Game ID {game_id}", fmt_sheet_title)
            worksheet_summary.write('A2', f"Period: {start_date.date()} to {end_date.date()}", fmt_default_top_border)
            current_row_summary = 4 # Start below title and period

            # Aggregate data for summary
            summary_stats = []
            for influencer_name in sorted(influencers):
                infl_df = feedback_df[feedback_df['influencer_name'] == influencer_name]
                total_videos = len(infl_df)
                # Count sentiments (case-insensitive check)
                sentiments = infl_df['analyzed_sentiment'].str.lower().value_counts()
                pos_count = sentiments.get('positive', 0)
                neg_count = sentiments.get('negative', 0)
                mix_count = sentiments.get('mixed', 0)
                neu_count = sentiments.get('neutral', 0)
                summary_stats.append({
                    'Influencer': influencer_name,
                    'Total Videos Analyzed': total_videos,
                    'Positive Sentiment': pos_count,
                    'Negative Sentiment': neg_count,
                    'Mixed Sentiment': mix_count,
                    'Neutral Sentiment': neu_count
                })
            
            summary_df = pd.DataFrame(summary_stats)
            summary_columns = summary_df.columns.tolist()

            # Write Headers
            for c_idx, col_name in enumerate(summary_columns):
                worksheet_summary.write(current_row_summary, c_idx, col_name, fmt_header)
            current_row_summary += 1
            
            # Write Data Rows
            for _, row_data in summary_df.iterrows():
                 for c_idx, col_name in enumerate(summary_columns):
                    value = row_data[col_name]
                    fmt = fmt_number_top_border if col_name != 'Influencer' else fmt_text_top_border
                    if isinstance(value, str):
                        worksheet_summary.write_string(current_row_summary, c_idx, value, fmt)
                    else:
                        worksheet_summary.write_number(current_row_summary, c_idx, value, fmt)
                 current_row_summary += 1

            # Adjust column widths for Summary sheet
            adjust_column_widths(summary_df, worksheet_summary, min_width=15, max_width=40)
            worksheet_summary.freeze_panes(5, 1) # Freeze header row and influencer column
            logger.info(f"Finished writing sheet: {summary_sheet_name}")


            # --- Step 3.2: Write Per-Influencer Sheets --- (existing logic modified for formatting)
            for influencer_name in sorted(influencers):
                logger.info(f"Writing sheet for influencer: {influencer_name}")
                influencer_df = feedback_df[feedback_df['influencer_name'] == influencer_name].copy()
                
                # Sanitize sheet name (max 31 chars, no invalid chars)
                safe_sheet_name = influencer_name.replace('[', '(').replace(']', ')').replace(':', '-').replace('*', '-').replace('?', '-').replace('/', '-').replace('\\', '-')
                safe_sheet_name = safe_sheet_name[:31]
                
                # Define columns to include and their order
                cols_to_include = [
                    'video_upload_date', 'video_title', 'analyzed_sentiment',
                    'summary', # This contains the detailed markdown summary
                    'positive_themes', 'negative_themes', 'bug_reports',
                    'feature_requests', 'balance_feedback',
                    'gameplay_loop_feedback', 'monetization_feedback',
                    'channel_handle', 'video_id', 'llm_analysis_timestamp' 
                ]
                # Ensure only existing columns are selected
                cols_to_select = [col for col in cols_to_include if col in influencer_df.columns]
                sheet_df = influencer_df[cols_to_select].sort_values(by='video_upload_date', ascending=False)
                
                # Convert list columns to newline-separated strings for Excel
                list_cols = ['positive_themes', 'negative_themes', 'bug_reports', 'feature_requests', 'balance_feedback', 'gameplay_loop_feedback', 'monetization_feedback']
                for col in list_cols:
                     if col in sheet_df.columns:
                          sheet_df[col] = sheet_df[col].apply(lambda x: '\n'.join(map(str, x)) if isinstance(x, list) and x else '-')
                
                # Convert datetimes to timezone-naive for xlsxwriter
                datetime_cols = ['video_upload_date', 'llm_analysis_timestamp']
                for dt_col in datetime_cols:
                    if dt_col in sheet_df.columns and pd.api.types.is_datetime64_any_dtype(sheet_df[dt_col]):
                        try:
                            if sheet_df[dt_col].dt.tz is not None:
                                sheet_df[dt_col] = sheet_df[dt_col].dt.tz_localize(None)
                        except Exception as tz_err:
                            logger.warning(f"Could not make column {dt_col} timezone-naive for sheet {safe_sheet_name}: {tz_err}.")
                            sheet_df[dt_col] = sheet_df[dt_col].astype(str) # Fallback to string
                
                # Write DataFrame to sheet
                sheet_df.to_excel(writer, sheet_name=safe_sheet_name, index=False, startrow=1) # Start row 1 to leave space for title
                worksheet = writer.sheets[safe_sheet_name]
                worksheet.write('A1', f"Feedback from {influencer_name}", fmt_sheet_title)
                
                # Apply formatting (headers, text wrap, column widths)
                # Write Headers with specific format
                for c_idx, value in enumerate(sheet_df.columns.values):
                    worksheet.write(1, c_idx, value, fmt_header) # Write headers on row 1 (0-indexed)
                
                # Define columns needing specific formats
                wrap_cols = ['video_title', 'summary', 'positive_themes', 'negative_themes', 'bug_reports', 'feature_requests', 'balance_feedback', 'gameplay_loop_feedback', 'monetization_feedback']
                date_cols = ['video_upload_date', 'llm_analysis_timestamp']
                
                # Apply formats to data cells row by row (overwrite default pandas formatting)
                start_data_row = 2 # Excel row index where data starts (1-based, after title[0] and header[1])
                for row_idx in range(len(sheet_df)):
                    excel_row = start_data_row + row_idx
                    for col_idx, col_name in enumerate(sheet_df.columns):
                        value = sheet_df.iloc[row_idx, col_idx]
                        
                        # Choose format based on column type
                        if col_name in wrap_cols:
                            fmt = fmt_text_wrap_top
                        elif col_name in date_cols:
                            # Check if it's actually a datetime object before applying date format
                            if isinstance(value, (datetime, pd.Timestamp)):
                                fmt = fmt_date_top
                            else: # If it was converted to string due to errors
                                fmt = fmt_text_top_border 
                        else:
                            fmt = fmt_text_top_border # Default: top-aligned, left-aligned, bordered text
                        
                        # Write cell with appropriate type and format
                        if pd.isna(value):
                            worksheet.write_blank(excel_row, col_idx, None, fmt)
                        elif isinstance(value, (int, float)):
                            # Use number format only if it wasn't explicitly defined otherwise (like dates)
                            num_fmt = fmt_number_top_border if col_name not in date_cols+wrap_cols else fmt
                            worksheet.write_number(excel_row, col_idx, value, num_fmt) 
                        elif isinstance(value, (datetime, pd.Timestamp)):
                             # write_datetime handles naive datetimes directly
                            worksheet.write_datetime(excel_row, col_idx, value, fmt) 
                        else:
                            worksheet.write_string(excel_row, col_idx, str(value), fmt)

                # Adjust column widths automatically after writing data and formats
                adjust_column_widths(sheet_df, worksheet, min_width=15, max_width=80) # Max width 80 for summary
                worksheet.freeze_panes(2, 1) # Freeze header row and first column (date)

            logger.info("Finished writing per-influencer sheets.")
            
        logger.info("Excel file generated successfully in memory.")

    except Exception as e:
        logger.exception(f"Error generating YouTube summary report: {e}")
        # Optional: Write an error sheet to the Excel buffer
        try:
            output.seek(0)
            output.truncate()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                 pd.DataFrame([{"Error": f"Report generation failed: {e}"}]).to_excel(writer, sheet_name="Error", index=False)
        except Exception as write_err:
            logger.error(f"Additionally failed to write error sheet to Excel: {write_err}")
        output.seek(0)
        return None # Indicate failure

    output.seek(0)
    return output.getvalue()

# Example usage for direct testing
if __name__ == '__main__':
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    
    logging.basicConfig(level=logging.INFO)
    logger.info("Running youtube_report_generator directly for testing...")
    
    TEST_GAME_ID = 1 # Assuming SMITE 2 is game ID 1 from seeding
    TEST_END_DATE = datetime.now(timezone.utc)
    TEST_START_DATE = TEST_END_DATE - timedelta(days=7)
    
    async def main_test():
        db_gen = get_db()
        db = next(db_gen)
        try:
            report_bytes = await generate_youtube_summary_report(db, TEST_GAME_ID, TEST_START_DATE, TEST_END_DATE)
            if report_bytes:
                output_filename = f"youtube_test_report_game_{TEST_GAME_ID}_{TEST_START_DATE.strftime('%Y%m%d')}-{TEST_END_DATE.strftime('%Y%m%d')}.xlsx"
                with open(output_filename, 'wb') as f:
                    f.write(report_bytes)
                logger.info(f"Test report saved to: {output_filename}")
            else:
                logger.error("Report generation failed.")
        finally:
            try:
                next(db_gen) # Attempt to close session if context manager isn't used
            except StopIteration:
                pass
            except Exception as e:
                logger.error(f"Error closing DB session: {e}")

    asyncio.run(main_test()) 