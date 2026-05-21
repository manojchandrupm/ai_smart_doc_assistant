import os
import sys
import asyncio
from google import genai
from google.genai import errors as genai_errors
from fastapi import WebSocket
from mcp_client import async_tavily_search
from config import env

# ─────────────────────────────────────────────────────────
# MCP / Tavily imports
# ─────────────────────────────────────────────────────────
NPX_CMD = "npx.cmd" if sys.platform == "win32" else "npx"

# pyrefly: ignore [missing-import]
from mcp import ClientSession, StdioServerParameters
# pyrefly: ignore [missing-import]
from mcp.client.stdio import stdio_client

# Gemini client
_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

MAX_RETRIES = 3
BASE_BACKOFF = 2  # seconds


# ─────────────────────────────────────────────────────────
# Web Search Agent prompt builder
# ─────────────────────────────────────────────────────────
def _build_web_search_prompt(question: str, search_results: str) -> str:
    return f"""
You are a helpful AI assistant with access to live web search results.

Answer the user's question using ONLY the search results below.
Be concise, accurate, and well-structured.
Use bullet points when listing multiple items.
If the search results do not contain a clear answer, say so honestly.

User Question:
{question}

--- TAVILY WEB SEARCH RESULTS ---
{search_results}
---------------------------------

Answer:
"""

# ─────────────────────────────────────────────────────────
# The main agent — called from chat.py WebSocket handler
# ─────────────────────────────────────────────────────────
async def run_web_search_agent(message: str, websocket: WebSocket, save_fn) -> str:
    """
    Full web search agent:
      1. Calls Tavily MCP for live results
      2. Sends results to Gemini for a structured answer
      3. Streams the answer token-by-token via the WebSocket
      4. Saves the final answer via save_fn

    Mirrors the run_browser_agent() pattern from browser_endpoint.py.
    """
    try:
        # Step 1: Fetch web search results
        print(f"[WebSearchAgent] Searching web for: {message}")
        search_results = await async_tavily_search(message)
 
        if search_results.startswith("Error"):
            error_msg = f"⚠️ Web search failed: {search_results}"
            await websocket.send_json({"type": "token", "content": error_msg})
            await websocket.send_json({"type": "end", "full_answer": "", "sources": []})
            save_fn(error_msg, [])
            return error_msg

        # Step 2: Build prompt + stream Gemini response
        prompt = _build_web_search_prompt(message, search_results)

        full_answer = ""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await _client.aio.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                async for chunk in response: 
                    piece = getattr(chunk, "text", "") or ""
                    if piece:
                        full_answer += piece
                        # Stream in small chunks for smooth UI
                        chunk_size = 5
                        for i in range(0, len(piece), chunk_size):
                            await websocket.send_json({
                                "type": "token",
                                "content": piece[i:i + chunk_size]
                            })
                            await asyncio.sleep(0.02)
                break  # Streaming completed — exit retry loop

            except (genai_errors.ClientError, genai_errors.ServerError) as e:
                is_retryable = (
                    "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e).upper() or
                    "503" in str(e) or "UNAVAILABLE" in str(e).upper()
                )
                if is_retryable and attempt < MAX_RETRIES:
                    wait = BASE_BACKOFF ** attempt
                    print(f"[WebSearchAgent] Gemini error, retrying in {wait}s (attempt {attempt})...")
                    await asyncio.sleep(wait)
                    continue
                full_answer = f"⚠️ Error generating answer: {str(e)}"
                await websocket.send_json({"type": "token", "content": full_answer})
                break

            except Exception as e:
                full_answer = f"⚠️ Error generating answer: {str(e)}"
                await websocket.send_json({"type": "token", "content": full_answer})
                break

        if not full_answer:
            full_answer = "⚠️ The search completed but no answer was generated."
            await websocket.send_json({"type": "token", "content": full_answer})

        # Step 3: Save + signal end
        save_fn(full_answer, [{"filename": "Tavily Web Search"}])
        await websocket.send_json({
            "type": "end",
            "sources": [{"filename": "Tavily Web Search"}],
            "full_answer": full_answer
        }) 
        return full_answer

    except Exception as e:
        error_msg = f"⚠️ Web search agent error: {str(e)}"
        print(f"[WebSearchAgent] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({"type": "token", "content": error_msg})
        await websocket.send_json({"type": "end", "full_answer": "", "sources": []})
        save_fn(error_msg, [])
        return error_msg
