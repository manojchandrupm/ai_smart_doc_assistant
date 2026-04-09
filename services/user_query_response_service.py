from google import genai
from google.genai import errors as genai_errors
import os
import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MAX_RETRIES = 3
BASE_BACKOFF = 2  # seconds

QUOTA_ERROR_MESSAGE = (
    "⚠️ API quota exceeded: The Gemini API rate limit has been reached. "
    "Please wait a moment and try again, or check your API quota in Google AI Studio."
)

UNAVAILABLE_ERROR_MESSAGE = (
    "⚠️ The Gemini model is currently experiencing high demand and is temporarily unavailable. "
    "Please try again in a few moments."
)

def _is_quota_error(e: Exception) -> bool:
    """Returns True if the exception is a Gemini quota/rate-limit error (429)."""
    status = getattr(e, 'status', None) or getattr(e, 'code', None)
    return (
        '429' in str(e) or
        'RESOURCE_EXHAUSTED' in str(e).upper() or
        (status is not None and str(status) in ('429', 'RESOURCE_EXHAUSTED'))
    )

def _is_unavailable_error(e: Exception) -> bool:
    """Returns True if the exception is a Gemini 503 model-unavailable/overload error."""
    status = getattr(e, 'status', None) or getattr(e, 'code', None)
    return (
        '503' in str(e) or
        'UNAVAILABLE' in str(e).upper() or
        (status is not None and str(status) in ('503', 'UNAVAILABLE'))
    )

def _is_retryable_error(e: Exception) -> bool:
    """Returns True if the error should trigger a retry (quota or model unavailable)."""
    return _is_quota_error(e) or _is_unavailable_error(e)

def _friendly_error_message(e: Exception) -> str:
    """Returns a user-friendly message for known transient Gemini API errors."""
    if _is_quota_error(e):
        return QUOTA_ERROR_MESSAGE
    if _is_unavailable_error(e):
        return UNAVAILABLE_ERROR_MESSAGE
    return f"Error generating answer: {str(e)}"

async def generate_query_response(content, chat_history):

    context = "\n\n".join([match["text"] for match in content['matches']])

    history_text = ""
    if chat_history:
        history_text = "\n".join(
            [f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history]
        )

    prompt = f"""
            You are a highly accurate document question-answering assistant.

You will be given:
1. A user question
2. Retrieved context chunks from a document

Your job:
- Answer the question ONLY using the provided context.
- Do NOT use any external knowledge.
- Do NOT guess or assume anything.
- If the answer is not present in the context, reply exactly:
  "I don't know based on the provided document."
- if the question is related to the past question from the chathistory refer it and provide the correct answer.

Instructions:
- Present the answer in a clean and structured format.
- Use bullet points when listing multiple items.
- Keep sentences short and easy to understand.
- Combine information only if it is clearly available in the context.
- Do NOT include explanations like "based on the context".
- Do NOT add notes or extra commentary.

Formatting rules:
- Start with a short 1-line summary (if applicable).
- Then present details as bullet points.
- Use simple and readable English.

---
Previous conversation:
{history_text}


Current User Question:
{content['question']}

---

Retrieved document context:
{context}

---

Answer:
            """

    answer = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            answer = response.text
            break

        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            if _is_retryable_error(e) and attempt < MAX_RETRIES:
                wait = BASE_BACKOFF ** attempt
                error_type = "quota exceeded" if _is_quota_error(e) else "model unavailable (503)"
                print(f"[QueryResponse] {error_type} — retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                await asyncio.sleep(wait)
                continue
            # Retries exhausted or non-retryable error
            answer = _friendly_error_message(e)
            break

        except Exception as e:
            answer = f"Error generating answer: {str(e)}"
            break

    if answer is None:
        answer = UNAVAILABLE_ERROR_MESSAGE

    return answer


async def stream_query_response(content, chat_history):
    context = "\n\n".join([match["text"] for match in content["matches"]])

    history_text = ""
    if chat_history:
        history_text = "\n".join(
            [f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history]
        )

    prompt = f"""
You are a smart AI assistant.

You can handle two types of queries:
1. General conversation (greetings, casual talk)
2. Document-based questions

---

Rules:

🔹 If the user asks a GENERAL question (like "hi", "how are you", "who are you"):
- Respond naturally like a friendly assistant.
- Keep it short.
- Mention that you are a bot designed to answer questions from uploaded documents.

---

If the user asks a DOCUMENT-RELATED question:
- Answer ONLY using the provided context.
- Do NOT use any external knowledge.
- Do NOT guess or assume anything.
- If the answer is not present in the context, reply exactly:
  "I don't know based on the provided document."

---

Instructions for document answers:
- Present the answer in a clean and structured format.
- Use bullet points when listing multiple items.
- Keep sentences short and easy to understand.
- Combine information only if clearly available in the context.
- Do NOT include explanations like "based on the context".
- Do NOT add extra commentary.

Formatting rules:
- Start with a short 1-line summary (if applicable).
- Then present details as bullet points.

---

Previous conversation:
{history_text}

---

Current User Question:
{content['question']}

---

Retrieved document context:
{context}

---

Answer:
"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            stream = await client.aio.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=prompt
            )

            async for chunk in stream:
                piece = getattr(chunk, "text", "")
                if piece:
                    yield piece
            return  # Streaming completed successfully

        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            if _is_retryable_error(e) and attempt < MAX_RETRIES:
                wait = BASE_BACKOFF ** attempt
                error_type = "quota exceeded" if _is_quota_error(e) else "model unavailable (503)"
                print(f"[StreamResponse] {error_type} — retrying in {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                await asyncio.sleep(wait)
                continue
            # Retries exhausted or non-retryable error
            yield f"\n{_friendly_error_message(e)}"
            return

        except Exception as e:
            yield f"\nError generating answer: {str(e)}"
            return

    yield f"\n{UNAVAILABLE_ERROR_MESSAGE}"