import os
import sys
import logging
from typing import Any, Optional, Type, Union
import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# --- OpenAI Configuration ---

# Load environment variables at module level
# Use absolute path loading logic consistent with prototype.py
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(ROOT_DIR, '.env')
logger.info(f"[OpenAI Client] Attempting to load .env from: {dotenv_path}")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)
    logger.info(f"[OpenAI Client] Loaded .env from: {dotenv_path}")
else:
    logger.warning(f"[OpenAI Client] .env file not found at {dotenv_path}. Relying on system env.")
    load_dotenv(override=True) # Fallback to default search

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("[OpenAI Client] Missing OPENAI_API_KEY environment variable.")
    # Decide if this should be a fatal error for the module
    # For now, let it proceed, but client initialization will likely fail
    # sys.exit(1) # Or raise an exception

# Use OPENAI_MODEL from environment or default
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")

# Initialize OpenAI Client at module level
client: Optional[openai.OpenAI] = None
try:
    if OPENAI_API_KEY:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        logger.info("[OpenAI Client] Initialized explicitly with API key.")
    else:
        logger.error("[OpenAI Client] Cannot initialize client: API key is missing.")
except Exception as e:
    logger.error(f"[OpenAI Client] Failed to initialize OpenAI client: {e}")
    client = None # Ensure client is None if init fails

# Define which OpenAI exceptions should be retried
RETRYABLE_EXCEPTIONS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    lambda e: isinstance(e, openai.APIStatusError) and e.status_code >= 500
)

# --- API Call Function ---

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS)
)
def call_openai_api(
    prompt: Any,
    model: str = OPENAI_MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    **kwargs
) -> Optional[str]:
    """Calls the OpenAI Responses API with retry logic."""
    if not client:
        logger.error("[OpenAI Client] OpenAI client is not initialized. Cannot make API call.")
        return None

    try:
        # Ensure model is not None or empty
        actual_model = model if model else OPENAI_MODEL
        if not actual_model: # Final fallback if OPENAI_MODEL was also empty
            actual_model = "gpt-4.1"
            logger.warning(f"[OpenAI Client] Model resolved to empty, falling back to {actual_model}")

        logger.info(f"[OpenAI Client] Calling Responses API with model: {actual_model}")

        # Prepare input for Responses API
        if isinstance(prompt, str):
            api_input = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            api_input = prompt
        else:
            logger.error(f"[OpenAI Client] Invalid prompt type: {type(prompt)}. Expected str or list.")
            return None

        # Prepare API call arguments (no text_format)
        api_args = {
            "model": actual_model,
            "input": api_input,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }

        # Make the API call
        response = client.responses.create(**api_args)

        # Revert to original text extraction logic
        output_text = ""
        if response.output:
            if hasattr(response, 'output_text') and response.output_text:
                output_text = response.output_text
            else:
                for item in response.output:
                    if hasattr(item, 'type') and item.type == 'output_text' and hasattr(item, 'text'):
                        output_text += item.text + "\n"
            output_text = output_text.strip()

        if output_text:
            logger.info(f"[OpenAI Client] API call successful. Output length: {len(output_text)}")
            return output_text
        else:
            # Check for refusal if no text output found
            if response.output:
                 first_output = response.output[0]
                 if hasattr(first_output, 'type') and first_output.type == 'refusal' and hasattr(first_output, 'refusal'):
                      refusal_text = first_output.refusal
                      logger.warning(f"[OpenAI Client] Model refused request: {refusal_text}")
                      # Decide how to signal refusal - maybe specific string?
                      return f"[REFUSAL: {refusal_text}]"
            logger.warning(f"[OpenAI Client] API call returned response but no output text found.")
            return None # Return None for standard text failure

    except openai.APIStatusError as e:
        logger.error(f"[OpenAI Client] APIStatusError: Status={e.status_code}, Response={e.response}")
        try:
            message = e.response.json().get('error', {}).get('message', 'N/A')
            logger.error(f"[OpenAI Client] Error Message: {message}")
        except Exception:
            logger.error("[OpenAI Client] Could not parse error message from response.")
        return None # Return None on API Status Error
    except Exception as e:
        logger.exception(f"[OpenAI Client] Unexpected error calling OpenAI API: {e}")
        return None # Return None on other exceptions 