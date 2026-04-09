# import requests
#
# def generate_embedding(text):
#     """
#     Generate embedding using Ollama embeddings API.
#     """
#     response = requests.post(
#         "http://localhost:11434/api/embed",
#         json={
#             "model": "nomic-embed-text",
#             "input": text
#         },
#         timeout=60
#     )
#
#     response.raise_for_status()
#     data = response.json()
#
#     return data["embeddings"][0]

from google import genai
from google.genai import errors as genai_errors
import os
import time

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MAX_RETRIES = 3
BASE_BACKOFF = 2  # seconds

def _is_quota_error(e: Exception) -> bool:
    status = getattr(e, 'status', None) or getattr(e, 'code', None)
    return (
        '429' in str(e) or
        'RESOURCE_EXHAUSTED' in str(e).upper() or
        (status is not None and str(status) in ('429', 'RESOURCE_EXHAUSTED'))
    )

def _is_unavailable_error(e: Exception) -> bool:
    status = getattr(e, 'status', None) or getattr(e, 'code', None)
    return (
        '503' in str(e) or
        'UNAVAILABLE' in str(e).upper() or
        (status is not None and str(status) in ('503', 'UNAVAILABLE'))
    )

def _is_retryable_error(e: Exception) -> bool:
    return _is_quota_error(e) or _is_unavailable_error(e)

def generate_embedding(text: str):
    """
    Generate embedding using Gemini API (cloud-based).
    Retries automatically on quota (429) and model-unavailable (503) errors.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=text
            )
            return response.embeddings[0].values

        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            if _is_retryable_error(e) and attempt < MAX_RETRIES:
                wait = BASE_BACKOFF ** attempt
                error_type = "API quota exceeded" if _is_quota_error(e) else "model unavailable (503)"
                print(f"[Embedding] {error_type}. Retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue
            # Retries exhausted or non-retryable error — raise friendly message
            if _is_quota_error(e):
                raise RuntimeError(
                    "API quota exceeded: The Gemini embedding API rate limit has been reached. "
                    "Please wait a moment and try again, or check your API quota in Google AI Studio."
                ) from e
            if _is_unavailable_error(e):
                raise RuntimeError(
                    "The Gemini embedding model is currently experiencing high demand (503). "
                    "Please try again in a few moments."
                ) from e
            raise RuntimeError(f"Embedding generation failed: {str(e)}") from e

        except Exception as e:
            raise RuntimeError(f"Embedding generation failed: {str(e)}") from e

    raise RuntimeError(
        "Embedding generation failed after multiple retries. Please try again later."
    )