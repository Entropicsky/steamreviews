#!/usr/bin/env python3
import os
import logging
import asyncio
import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables (especially for R2 and DB)
# Make sure .env is in the project root or vars are set in the deployment environment
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env') # Assumes api_server.py is in root
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    logger.info(f"Loaded environment variables from {dotenv_path}")
else:
    logger.info("No .env file found in root, relying on system environment variables.")

# --- Import project modules ---
from src.reporting.excel_generator import generate_summary_report
from src.utils.r2_uploader import upload_to_r2_and_get_presigned_url

# --- Configuration ---
# PRIMARY_APP_ID is removed - will be passed as query parameter
# logger.info(f"Using APP ID for reports: {PRIMARY_APP_ID}")

# --- FastAPI App --- 
app = FastAPI(
    title="Steam Review Report Generator API",
    description="Generates Steam review summary reports and provides a download link.",
    version="1.0.0"
)

@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}

@app.get("/generate_report")
async def trigger_generate_report(
    timespan: str = Query(..., description="Time span for the report ('weekly' or 'monthly')"),
    app_id: int = Query(..., description="Steam App ID for the report (e.g., 3228590)")
):
    """Triggers the generation of the Excel report, uploads it, and returns a pre-signed URL."""
    logger.info(f"---> ENTERING /generate_report endpoint for App ID: {app_id}, Timespan: {timespan}")
    
    # --- Temporarily simplify for debugging --- 
    logger.info("--- DEBUG: Skipping actual report generation and upload ---")
    return JSONResponse(content={
        "message": "DEBUG: Skipped report generation.",
        "app_id_received": app_id,
        "timespan_received": timespan,
        "report_url": "debug-skipped"
    })
    # --- End simplification ---
    
    # --- Original Code (Commented out) ---
    # logger.info(f"Received GET request to generate report for App ID: {app_id}, Timespan: {timespan}")
    # # 1. Calculate start_timestamp
    # now_utc = datetime.datetime.now(datetime.timezone.utc)
    # if timespan == 'weekly':
    #     start_of_this_week = now_utc - datetime.timedelta(days=now_utc.weekday())
    #     start_of_last_week = start_of_this_week - datetime.timedelta(weeks=1)
    #     start_datetime_utc = start_of_last_week.replace(hour=0, minute=0, second=0, microsecond=0)
    #     start_timestamp = int(start_datetime_utc.timestamp())
    #     logger.info(f"Calculated weekly start timestamp: {start_timestamp} ({start_datetime_utc})")
    # elif timespan == 'monthly':
    #     first_day_this_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    #     last_day_last_month = first_day_this_month - datetime.timedelta(days=1)
    #     start_datetime_utc = last_day_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    #     start_timestamp = int(start_datetime_utc.timestamp())
    #     logger.info(f"Calculated monthly start timestamp: {start_timestamp} ({start_datetime_utc})")
    # else:
    #     logger.error(f"Invalid timespan provided: {timespan}")
    #     raise HTTPException(status_code=400, detail="Invalid timespan. Use 'weekly' or 'monthly'.")
    # 
    # try:
    #     logger.info(f"Starting report generation for App ID: {app_id}, Timestamp: {start_timestamp}")
    #     # 2. Call the actual report generator using the passed app_id
    #     report_bytes = await generate_summary_report(app_id, start_timestamp)
    #     
    #     if not report_bytes:
    #          logger.error(f"Report generation returned empty bytes for App ID: {app_id}.")
    #          raise HTTPException(status_code=500, detail=f"Report generation failed for App ID {app_id} (empty result).")
    #     logger.info(f"Report generation successful for App ID: {app_id}. Size: {len(report_bytes)} bytes.")
    # 
    #     # 3. Upload to R2 and get pre-signed URL using the passed app_id
    #     report_url = await upload_to_r2_and_get_presigned_url(
    #         file_bytes=report_bytes,
    #         app_id=app_id,
    #         timespan=timespan
    #     )
    #     
    #     if not report_url:
    #         logger.error(f"Failed to upload report to R2 for App ID: {app_id}.")
    #         raise HTTPException(status_code=500, detail=f"Failed to store report for App ID {app_id} after generation.")
    #     logger.info(f"Report for App ID: {app_id} uploaded to R2. Pre-signed URL generated.")
    # 
    #     # 4. Return the URL
    #     return JSONResponse(content={
    #         "message": "Report generated and uploaded successfully.",
    #         "report_url": report_url
    #     })
    # 
    # except HTTPException as http_exc: # Re-raise HTTP exceptions
    #     raise http_exc
    # except Exception as e:
    #     logger.exception(f"Failed to generate or upload report for App ID: {app_id}, Timespan: {timespan}: {e}")
    #     raise HTTPException(status_code=500, detail=f"Internal server error during report process for App ID {app_id}: {str(e)}")
    # --- End Original Code ---

# --- Main entry point --- 
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting Uvicorn server on port {port}")
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False) 