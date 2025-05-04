import os
from dotenv import load_dotenv
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Explicitly define the path to the .env file in the current directory
# (assuming this script is run from the root)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')

logging.info(f"Looking for .env file at: {os.path.abspath(dotenv_path)}")

# Load the .env file
if os.path.exists(dotenv_path):
    loaded = load_dotenv(dotenv_path=dotenv_path, override=True) # Override ensures .env takes precedence
    if loaded:
        logging.info(".env file loaded successfully.")
    else:
        logging.warning(".env file found but load_dotenv returned False.")
else:
    logging.warning(".env file not found at the specified path.")

# Get the environment variable
api_key = os.getenv("OPENAI_API_KEY")

# Print the result
if api_key:
    # Mask the key for security, showing only first 5 and last 4 chars
    masked_key = f"{api_key[:5]}...{api_key[-4:] if len(api_key) > 9 else ''}"
    logging.info(f"Found OPENAI_API_KEY: {masked_key}")
    if "your_ope" in api_key:
        logging.error("The loaded key appears to be the placeholder string!")
else:
    logging.error("OPENAI_API_KEY not found in environment after loading .env.")

print("\nTest complete.") 