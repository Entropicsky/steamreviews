import os
import sys
import logging
import asyncio # Added for async
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

# Initialize OpenAI Clients at module level
client: Optional[openai.OpenAI] = None
async_client: Optional[openai.AsyncOpenAI] = None # Added async client
try:
    if OPENAI_API_KEY:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        async_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY) # Initialize async client
        logger.info("[OpenAI Client] Initialized sync and async clients explicitly with API key.")
    else:
        logger.error("[OpenAI Client] Cannot initialize clients: API key is missing.")
except Exception as e:
    logger.error(f"[OpenAI Client] Failed to initialize OpenAI clients: {e}")
    client = None
    async_client = None

# Define which OpenAI exceptions should be retried
# These generally apply to both sync and async clients
RETRYABLE_EXCEPTIONS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    # Retry on server errors (5xx). Specific client errors (4xx) might need case-by-case handling.
    lambda e: isinstance(e, openai.APIStatusError) and e.status_code >= 500
)

# --- Sync API Call Function ---

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
    """Calls the OpenAI Responses API synchronously with retry logic."""
    if not client:
        logger.error("[OpenAI Client][Sync] OpenAI client is not initialized. Cannot make API call.")
        return None

    try:
        # Ensure model is not None or empty
        actual_model = model if model else OPENAI_MODEL
        if not actual_model: # Final fallback if OPENAI_MODEL was also empty
            actual_model = "gpt-4.1"
            logger.warning(f"[OpenAI Client][Sync] Model resolved to empty, falling back to {actual_model}")

        logger.info(f"[OpenAI Client][Sync] Calling Responses API with model: {actual_model}")

        # Prepare input for Responses API
        if isinstance(prompt, str):
            api_input = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            api_input = prompt
        else:
            logger.error(f"[OpenAI Client][Sync] Invalid prompt type: {type(prompt)}. Expected str or list.")
            return None

        # Prepare API call arguments
        api_args = {
            "model": actual_model,
            "input": api_input,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }

        # Make the API call
        response = client.responses.create(**api_args)

        # Extract output text (handle potential variations)
        output_text = ""
        if response.output:
            # Prefer output_text if available (newer structure?)
            if hasattr(response, 'output_text') and response.output_text:
                output_text = response.output_text
            else: # Fallback to iterating output list
                for item in response.output:
                    if hasattr(item, 'type') and item.type == 'output_text' and hasattr(item, 'text'):
                        output_text += item.text + "\n"
            output_text = output_text.strip()

        if output_text:
            logger.info(f"[OpenAI Client][Sync] API call successful. Output length: {len(output_text)}")
            return output_text
        else:
            # Check for refusal if no text output found
            if response.output:
                 first_output = response.output[0]
                 if hasattr(first_output, 'type') and first_output.type == 'refusal' and hasattr(first_output, 'refusal'):
                      refusal_text = first_output.refusal
                      logger.warning(f"[OpenAI Client][Sync] Model refused request: {refusal_text}")
                      return f"[REFUSAL: {refusal_text}]" # Specific refusal string
            logger.warning(f"[OpenAI Client][Sync] API call returned response but no output text found.")
            return None

    except openai.APIStatusError as e:
        logger.error(f"[OpenAI Client][Sync] APIStatusError: Status={e.status_code}, Response={e.response}")
        try:
            message = e.response.json().get('error', {}).get('message', 'N/A')
            logger.error(f"[OpenAI Client][Sync] Error Message: {message}")
        except Exception:
            logger.error("[OpenAI Client][Sync] Could not parse error message from response.")
        return None
    except Exception as e:
        logger.exception(f"[OpenAI Client][Sync] Unexpected error calling OpenAI API: {e}")
        return None

# --- Async API Call Function --- NEW --- 

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS)
)
async def acall_openai_api(
    prompt: Any,
    model: str = OPENAI_MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    **kwargs
) -> Optional[str]:
    """Calls the OpenAI Responses API asynchronously with retry logic."""
    if not async_client:
        logger.error("[OpenAI Client][Async] Async OpenAI client is not initialized. Cannot make API call.")
        return None

    try:
        # Ensure model is not None or empty
        actual_model = model if model else OPENAI_MODEL
        if not actual_model:
            actual_model = "gpt-4.1"
            logger.warning(f"[OpenAI Client][Async] Model resolved to empty, falling back to {actual_model}")

        logger.info(f"[OpenAI Client][Async] Calling Responses API with model: {actual_model}")

        # Prepare input for Responses API
        if isinstance(prompt, str):
            api_input = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            api_input = prompt
        else:
            logger.error(f"[OpenAI Client][Async] Invalid prompt type: {type(prompt)}. Expected str or list.")
            return None

        # Prepare API call arguments
        api_args = {
            "model": actual_model,
            "input": api_input,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }

        # Make the API call asynchronously
        response = await async_client.responses.create(**api_args)

        # Extract output text (same logic as sync version)
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
            logger.info(f"[OpenAI Client][Async] API call successful. Output length: {len(output_text)}")
            return output_text
        else:
            # Check for refusal if no text output found
            if response.output:
                 first_output = response.output[0]
                 if hasattr(first_output, 'type') and first_output.type == 'refusal' and hasattr(first_output, 'refusal'):
                      refusal_text = first_output.refusal
                      logger.warning(f"[OpenAI Client][Async] Model refused request: {refusal_text}")
                      return f"[REFUSAL: {refusal_text}]"
            logger.warning(f"[OpenAI Client][Async] API call returned response but no output text found.")
            return None

    except openai.APIStatusError as e:
        logger.error(f"[OpenAI Client][Async] APIStatusError: Status={e.status_code}, Response={e.response}")
        try:
            message = e.response.json().get('error', {}).get('message', 'N/A')
            logger.error(f"[OpenAI Client][Async] Error Message: {message}")
        except Exception:
            logger.error("[OpenAI Client][Async] Could not parse error message from response.")
        return None
    except Exception as e:
        logger.exception(f"[OpenAI Client][Async] Unexpected error calling OpenAI API: {e}")
        return None 