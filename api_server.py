#!/usr/bin/env python3
import os
import logging
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import uvicorn

# Configure logging (still useful for startup)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
logger = logging.getLogger(__name__)

# --- FastAPI App --- 
app = FastAPI(
    title="Steam Review Report Generator API - DEBUG MINIMAL",
    version="0.1.0"
)

@app.get("/health")
def health_check():
    return {"status": "ok - minimal"}

@app.get("/generate_report") 
async def trigger_generate_report_minimal(
    # Keep params for URL structure consistency, but don't use them
    timespan: str = Query(..., description="Time span for the report ('weekly' or 'monthly')"),
    app_id: int = Query(..., description="Steam App ID for the report (e.g., 3228590)") 
):
    """Minimal endpoint for debugging routing/server startup."""
    logger.info(f"---> MINIMAL /generate_report endpoint hit. ts={timespan}, app={app_id}")
    return JSONResponse(content={"message": "Minimal endpoint reached successfully!"})

# --- Main entry point --- 
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting MINIMAL Uvicorn server on port {port}")
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False) 