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
        analyzed_feedback_data = crud.get_analyzed_feedback_for_game(db_session, game_id, start_date, end_date)

        if not analyzed_feedback_data:
            logger.warning(f"No analyzed YouTube feedback found for game {game_id} in the specified date range.")
            # Create a simple Excel file indicating no data
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                 pd.DataFrame([{"Status": f"No analyzed YouTube feedback found for Game ID {game_id} between {start_date.date()} and {end_date.date()}"}]).to_excel(writer, sheet_name="Status", index=False)
            output.seek(0)
            return output.getvalue()
        
        logger.info(f"Fetched {len(analyzed_feedback_data)} analyzed feedback records.")
        feedback_df = pd.DataFrame(analyzed_feedback_data)

        # --- Step 2: Prepare Data --- 
        influencers = feedback_df['influencer_name'].unique()
        logger.info(f"Found feedback from {len(influencers)} influencers: {list(influencers)}")

        # Add Video URL column for hyperlinks
        feedback_df['video_url'] = feedback_df['video_id'].apply(lambda x: f"https://www.youtube.com/watch?v={x}")
        
        # Convert list columns to newline-separated strings globally first
        list_cols = ['positive_themes', 'negative_themes', 'bug_reports', 'feature_requests', 'balance_feedback', 'gameplay_loop_feedback', 'monetization_feedback']
        for col in list_cols:
             if col in feedback_df.columns:
                  feedback_df[col] = feedback_df[col].apply(lambda x: '\n'.join(map(str, x)) if isinstance(x, list) and x else '-')
        
        # Convert datetimes to timezone-naive globally first
        datetime_cols = ['video_upload_date', 'llm_analysis_timestamp']
        for dt_col in datetime_cols:
            if dt_col in feedback_df.columns and pd.api.types.is_datetime64_any_dtype(feedback_df[dt_col]):
                try:
                    if feedback_df[dt_col].dt.tz is not None:
                        feedback_df[dt_col] = feedback_df[dt_col].dt.tz_localize(None)
                except Exception as tz_err:
                    logger.warning(f"Could not make column {dt_col} timezone-naive: {tz_err}.")
                    feedback_df[dt_col] = feedback_df[dt_col].astype(str) # Fallback to string

        # --- Step 3: Write Excel File --- 
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            # --- Define Formats --- 
            fmt_sheet_title = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left', 'valign': 'top'})
            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1, 'align': 'center', 'valign': 'top', 'text_wrap': True})
            fmt_text_wrap_top = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1, 'align': 'left'})
            fmt_date_top = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm', 'valign': 'top', 'border': 1, 'align': 'left'})
            fmt_text_top_border = workbook.add_format({'valign': 'top', 'border': 1, 'align': 'left'})
            fmt_link_wrap_top = workbook.add_format({'font_color': 'blue', 'underline': 1, 'text_wrap': True, 'valign': 'top', 'border': 1, 'align': 'left'})
            fmt_link_top_border = workbook.add_format({'font_color': 'blue', 'underline': 1, 'valign': 'top', 'border': 1, 'align': 'left'})

            # --- Step 3.1: Write NEW Summary Sheet (List View) ---
            summary_sheet_name = "Video Summary List"
            logger.info(f"Writing sheet: {summary_sheet_name}")
            worksheet_summary = workbook.add_worksheet(summary_sheet_name)
            worksheet_summary.write('A1', f"YouTube Feedback Video List for Game ID {game_id}", fmt_sheet_title)
            worksheet_summary.write('A2', f"Period: {start_date.date()} to {end_date.date()}", fmt_text_top_border) # Use fmt_text_top_border
            current_row_summary = 4 # Start below title and period

            # Define columns for the new summary view
            summary_cols_to_include = [
                 'influencer_name', 'video_upload_date', 'video_title', 
                 'analyzed_sentiment', 'positive_themes', 'negative_themes', 
                 'bug_reports', 'feature_requests', 'balance_feedback', 
                 'gameplay_loop_feedback', 'monetization_feedback',
                 'video_url' # Include URL for the link
            ]
            # Old sort: summary_df = feedback_df[summary_cols_to_include].sort_values(by=['influencer_name', 'video_upload_date'], ascending=[True, False])
            # New sort: primarily by newest video globally, then by influencer name as a secondary sort for tie-breaking (though unlikely with timestamps)
            summary_df = feedback_df[summary_cols_to_include].sort_values(by=['video_upload_date', 'influencer_name'], ascending=[False, True])

            # Write Headers
            for c_idx, col_name in enumerate(summary_df.columns):
                 # Don't write the actual URL column header, title will be the link
                 if col_name != 'video_url':
                     worksheet_summary.write(current_row_summary, c_idx, col_name, fmt_header)
            current_row_summary += 1
            
            # Write Data Rows
            title_col_idx = summary_df.columns.get_loc('video_title')
            url_col_idx = summary_df.columns.get_loc('video_url')
            date_col_idx = summary_df.columns.get_loc('video_upload_date')
            list_data_cols = [col for col in list_cols if col in summary_df.columns] # Find which list cols are present
            
            for row_idx in range(len(summary_df)):
                 excel_row = current_row_summary + row_idx
                 for col_idx, col_name in enumerate(summary_df.columns):
                     if col_name == 'video_url': continue # Skip writing the URL column itself
                     
                     value = summary_df.iloc[row_idx, col_idx]
                     url = summary_df.iloc[row_idx, url_col_idx]

                     # Choose format
                     if col_idx == title_col_idx: # Video Title Column
                         fmt = fmt_link_wrap_top
                         worksheet_summary.write_url(excel_row, col_idx, url, fmt, string=str(value) if pd.notna(value) else '-')
                     elif col_name in list_data_cols:
                         fmt = fmt_text_wrap_top
                         worksheet_summary.write_string(excel_row, col_idx, str(value) if pd.notna(value) else '-', fmt)
                     elif col_name == 'video_upload_date':
                          fmt = fmt_date_top
                          if isinstance(value, (datetime, pd.Timestamp)):
                              worksheet_summary.write_datetime(excel_row, col_idx, value, fmt)
                          else:
                              worksheet_summary.write_string(excel_row, col_idx, str(value) if pd.notna(value) else '-', fmt)
                     else:
                         fmt = fmt_text_top_border
                         worksheet_summary.write_string(excel_row, col_idx, str(value) if pd.notna(value) else '-', fmt)
            
            # Adjust column widths
            worksheet_summary.set_column(url_col_idx, url_col_idx, None, None, {'hidden': True}) # Hide the URL column
            adjust_column_widths(summary_df.drop(columns=['video_url']), worksheet_summary, min_width=15, max_width=50)
            worksheet_summary.freeze_panes(5, 2) # Freeze header rows and influencer name/date
            logger.info(f"Finished writing sheet: {summary_sheet_name}")


            # --- Step 3.2: Write Per-Influencer Sheets --- 
            for influencer_name in sorted(influencers):
                logger.info(f"Writing sheet for influencer: {influencer_name}")
                # Get the pre-processed data for this influencer
                influencer_df_full = feedback_df[feedback_df['influencer_name'] == influencer_name].copy()
                
                safe_sheet_name = influencer_name.replace('[', '(').replace(']', ')').replace(':', '-').replace('*', '-').replace('?', '-').replace('/', '-').replace('\\', '-')
                safe_sheet_name = safe_sheet_name[:31]
                
                # Define columns for these sheets (include summary here, exclude URL col)
                cols_to_include = [
                    'video_upload_date', 'video_title', 'analyzed_sentiment',
                    'summary', # Detailed markdown summary
                    'positive_themes', 'negative_themes', 'bug_reports',
                    'feature_requests', 'balance_feedback',
                    'gameplay_loop_feedback', 'monetization_feedback',
                    'channel_handle', 'video_id', 'llm_analysis_timestamp'
                    # 'video_url' is implicitly used for link but not displayed as a column
                ]
                cols_to_select = [col for col in cols_to_include if col in influencer_df_full.columns]
                sheet_df = influencer_df_full[cols_to_select + ['video_url']].sort_values(by='video_upload_date', ascending=False) # Include URL for link
                
                # Write DataFrame to sheet - without URL column explicitly
                sheet_df_display = sheet_df.drop(columns=['video_url'])
                sheet_df_display.to_excel(writer, sheet_name=safe_sheet_name, index=False, startrow=1)
                worksheet = writer.sheets[safe_sheet_name]
                worksheet.write('A1', f"Feedback from {influencer_name}", fmt_sheet_title)
                
                # Apply formatting (headers)
                for c_idx, value in enumerate(sheet_df_display.columns.values):
                    worksheet.write(1, c_idx, value, fmt_header)
                
                # Define columns needing specific formats
                wrap_cols = ['video_title', 'summary', 'positive_themes', 'negative_themes', 'bug_reports', 'feature_requests', 'balance_feedback', 'gameplay_loop_feedback', 'monetization_feedback']
                date_cols = ['video_upload_date', 'llm_analysis_timestamp']
                title_col_name = 'video_title' # Column to make hyperlink
                
                # Apply formats row by row
                start_data_row = 2 
                for row_idx in range(len(sheet_df)):
                    excel_row = start_data_row + row_idx
                    for col_idx, col_name in enumerate(sheet_df_display.columns):
                        value = sheet_df_display.iloc[row_idx, col_idx]
                        
                        # Get corresponding URL for title link
                        url = sheet_df.iloc[row_idx]['video_url']
                        
                        # Choose format based on column type
                        if col_name == title_col_name:
                             fmt = fmt_link_wrap_top # Use link format
                             worksheet.write_url(excel_row, col_idx, url, fmt, string=str(value) if pd.notna(value) else '-')
                        elif col_name in wrap_cols:
                            fmt = fmt_text_wrap_top
                            worksheet.write_string(excel_row, col_idx, str(value) if pd.notna(value) else '-', fmt)
                        elif col_name in date_cols:
                            if isinstance(value, (datetime, pd.Timestamp)):
                                fmt = fmt_date_top
                                worksheet.write_datetime(excel_row, col_idx, value, fmt) 
                            else:
                                fmt = fmt_text_top_border 
                                worksheet.write_string(excel_row, col_idx, str(value) if pd.notna(value) else '-', fmt)
                        else:
                            fmt = fmt_text_top_border
                            worksheet.write_string(excel_row, col_idx, str(value) if pd.notna(value) else '-', fmt)

                # Adjust column widths
                adjust_column_widths(sheet_df_display, worksheet, min_width=15, max_width=80)
                worksheet.freeze_panes(2, 1)

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