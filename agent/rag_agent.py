import re
import asyncio
from fastapi import WebSocket
from services.retrieval_service import retrieve_similar_chunks
from services.mongodb_retrieval_service import retrieve_similar_chunks_from_mongodb
from services.embedding_service import generate_embedding
from services.user_query_response_service import stream_query_response
from mcp_client import async_fetch_url
from core.utils import is_general_question
from services.cache_service import set_cached_answer
from services.chat_service import save_chat_message

async def run_rag_agent(
    message: str, 
    websocket: WebSocket, 
    user_id: str, 
    session_id: str, 
    chat_history: list,
    top_k: int = 5,
    db_choice: str = "mongodb"
) -> str:
    """
    RAG Agent:
    1. Retrieves similar chunks from the user's documents.
    2. Fetches web content if a URL is found in the message.
    3. Streams the answer token-by-token using the LLM via WebSocket.
    4. Caches the response and saves it to the database.
    """

    print(f"[RAG Agent] db_choice is: {db_choice}")
    if db_choice == "mongodb":
        query_embedding = generate_embedding(message)
        matches = retrieve_similar_chunks_from_mongodb(query_embedding, user_id, top_k)
    else:
        matches = retrieve_similar_chunks(question=message, user_id=user_id, top_k=top_k)
         

    # --- MCP WEB FETCHING (By URL) ---
    url_pattern = r'(https?://[^\s<>"]+|www\.[^\s<>"]+|[a-zA-Z0-9.-]+\.(?:com|org|net|edu|gov|io|co|in|ai)\b(?:/[^\s<>"]*)?)'
    urls = re.findall(url_pattern, message)
    if urls:
        matches.clear()
        for raw_url in urls:
            raw_url = raw_url.rstrip('.,;!?)("\'')
            fetch_url = raw_url if raw_url.startswith('http') else 'https://' + raw_url
            try:
                web_content = await async_fetch_url(fetch_url)
                matches.append({
                    "filename": raw_url,
                    "text": f"--- START OF WEBPAGE CONTENT ({raw_url}) ---\n{web_content}\n--- END OF WEBPAGE CONTENT ---"
                })
            except Exception as e:
                matches.append({
                    "filename": raw_url,
                    "text": f"The user asked you to summarize {raw_url}, but the system failed to fetch it. Tell the user: 'I could not fetch the website because of an error.'"
                })
    # ------------------------

    full_answer = ""
    try:
        async for chunk in stream_query_response(content={"question": message, "matches": matches}, chat_history=chat_history):
            full_answer += chunk
            # Break large chunks from Gemini into smaller pieces to force smooth UI streaming
        chunk_size = 5 
        for i in range(0, len(full_answer), chunk_size):
            piece = full_answer[i:i+chunk_size]
            await websocket.send_json({"type": "token", "content": piece})
            await asyncio.sleep(0.02)
        
        is_error = "⚠️" in full_answer or "Error" in full_answer
        is_fallback = "I don't know based on the provided document" in full_answer
        is_tagged_general = "[GENERAL]" in full_answer

        if is_tagged_general:
            full_answer = full_answer.replace("[GENERAL]", "").strip()

        if is_general_question(message) or is_error or is_fallback or is_tagged_general:
            sources = []
        else:
            unique_filenames = []
            for m in matches:
                if m["filename"] not in unique_filenames:
                    unique_filenames.append(m["filename"])
            sources = [{"filename": fn} for fn in unique_filenames]

        save_chat_message(user_id, session_id, "assistant", full_answer, sources)

        # Only cache real document answers, not errors or greetings
        if not is_error and not is_fallback and not is_tagged_general:
            set_cached_answer(user_id, message, full_answer, sources)

        await websocket.send_json({
            "type": "end",
            "sources": sources,
            "full_answer": full_answer
        })
        
        return full_answer

    except Exception as e:
        error_msg = f"⚠️ RAG agent error: {str(e)}"
        print(f"[RagAgent] EXCEPTION: {e}")
        await websocket.send_json({"type": "token", "content": error_msg})
        await websocket.send_json({"type": "end", "full_answer": error_msg, "sources": []})
        save_chat_message(user_id, session_id, "assistant", error_msg, [])
        return error_msg
