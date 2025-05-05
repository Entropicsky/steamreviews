#!/usr/bin/env python3
import os
import logging
import datetime
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

logger = logging.getLogger(__name__)

# --- R2 Configuration (Load from Environment Variables) ---
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "steam-reviews") # Default to your bucket name
R2_REGION = os.getenv("R2_REGION", "auto") # R2 typically uses 'auto'

# --- Check if configuration is present --- 
if not all([R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME]):
    logger.error("R2 configuration missing in environment variables (R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME)")
    # You might want to raise an exception here or handle it gracefully depending on usage context
    # For now, we'll let it fail later if boto3 is initialized without creds

# --- Boto3 S3 Client Initialization --- 
def get_r2_client():
    """Initializes and returns a boto3 S3 client configured for R2."""
    if not all([R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
         logger.error("Cannot initialize R2 client due to missing environment variables.")
         return None
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name=R2_REGION, # Often 'auto' for R2
            config=Config(signature_version='s3v4') # Ensure v4 signatures
        )
        logger.info(f"Successfully initialized boto3 S3 client for R2 endpoint: {R2_ENDPOINT_URL}")
        return s3_client
    except Exception as e:
        logger.exception(f"Failed to initialize R2 client: {e}")
        return None

# --- Upload and Pre-sign Function --- 
async def upload_to_r2_and_get_presigned_url(
    file_bytes: bytes,
    app_id: int,
    timespan: str,
    expiration_seconds: int = 3600 # Default: 1 hour
) -> str | None:
    """Uploads file bytes to R2 and generates a pre-signed URL for download.

    Args:
        file_bytes: The bytes content of the file to upload.
        app_id: The Steam App ID for naming.
        timespan: The report timespan ('weekly' or 'monthly') for naming.
        expiration_seconds: How long the pre-signed URL should be valid.

    Returns:
        The pre-signed URL string, or None if an error occurred.
    """
    s_client = get_r2_client()
    if not s_client:
        return None

    # Generate a unique object key (filename in the bucket)
    timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    object_key = f"reports/steam_report_{app_id}_{timespan}_{timestamp_str}.xlsx"

    logger.info(f"Attempting to upload report to R2 bucket '{R2_BUCKET_NAME}' with key '{object_key}'")

    try:
        # Upload the file bytes
        s_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=object_key,
            Body=file_bytes,
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        logger.info(f"Successfully uploaded {object_key} to R2 bucket '{R2_BUCKET_NAME}'.")

        # Generate the pre-signed URL for GET requests
        presigned_url = s_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': R2_BUCKET_NAME, 'Key': object_key},
            ExpiresIn=expiration_seconds
        )
        logger.info(f"Generated pre-signed URL (valid for {expiration_seconds}s): {presigned_url}")
        return presigned_url

    except ClientError as e:
        logger.error(f"Boto3 ClientError during R2 operation: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during R2 upload/pre-sign: {e}")
        return None

# --- Example Usage (for testing) --- 
if __name__ == '__main__':
    # Configure logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
    
    # Load .env for testing if present
    try:
        from dotenv import load_dotenv
        dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env') # Go up two levels for project root .env
        if os.path.exists(dotenv_path):
             load_dotenv(dotenv_path=dotenv_path)
             logger.info(f"Loaded environment variables from {dotenv_path} for testing.")
             # Re-fetch R2 variables after loading .env
             R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
             R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
             R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
             R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "steam-reviews")
             R2_REGION = os.getenv("R2_REGION", "auto")
        else:
             logger.warning("No .env file found at project root for testing R2 uploader.")

    except ImportError:
        logger.warning("python-dotenv not installed, cannot load .env for testing R2 uploader.")
        pass # Continue without dotenv if not installed

    async def test_upload():
        logger.info("--- Testing R2 Upload --- ")
        if not all([R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME]):
            logger.error("Skipping R2 upload test due to missing configuration.")
            return

        dummy_bytes = b"This is dummy excel data for testing R2 upload."
        test_app_id = 12345
        test_timespan = "test"
        
        url = await upload_to_r2_and_get_presigned_url(dummy_bytes, test_app_id, test_timespan, expiration_seconds=600)
        
        if url:
            logger.info(f"Test successful. Pre-signed URL: {url}")
            logger.info("You can try accessing this URL in your browser (valid for 10 minutes).")
        else:
            logger.error("Test failed. Check logs for errors.")
        logger.info("--- End R2 Upload Test --- ")

    # Run the async test function
    import asyncio
    asyncio.run(test_upload()) 