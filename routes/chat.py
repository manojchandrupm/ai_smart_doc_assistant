from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
import json
import asyncio
import re
from models.chat_models import ChatRequest
from core.dependencies import get_current_user
from core.security import decode_access_token
from core.utils import is_general_question  # ✅ from shared util, not query_router
from services.auth_service import get_user_by_id
from services.chat_service import (
    create_chat_session,
    get_user_session,
    save_chat_message,
    list_user_sessions,
    list_session_messages,
    delete_chat_session
)
from services.retrieval_service import retrieve_similar_chunks
from services.user_query_response_service import generate_query_response, stream_query_response, needs_web_search
from services.cache_service import get_cached_answer, set_cached_answer
from mcp_client import async_fetch_url, async_tavily_search

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()

    # ─────────────────────────────────────────────────────────
    # Step 1: Expect the FIRST message to be a JSON auth handshake
    # This keeps the token out of the URL (no server logs / browser history)
    # Expected format: { "type": "auth", "token": "<jwt>" }
    # ─────────────────────────────────────────────────────────
    try:
        raw = await websocket.receive_text()
        auth_msg = json.loads(raw)
        if auth_msg.get("type") != "auth" or not auth_msg.get("token"):
            await websocket.close(code=1008, reason="First message must be auth handshake")
            return
        token = auth_msg["token"]
        auth_payload = decode_access_token(token)
        user_id = auth_payload.get("sub")
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token: missing user id")
            return
        user = get_user_by_id(user_id)
        if not user:
            await websocket.close(code=1008, reason="User not found")
            return
    except Exception:
        await websocket.close(code=1008, reason="Authentication failed")
        return

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            message = payload.get("message")

            session_id = payload.get("session_id")
            top_k = payload.get("top_k", 3)

            if session_id:
                session = get_user_session(session_id, user_id)
                if not session:
                    await websocket.send_json({"error": "Session not found"})
                    continue
            else:
                session = create_chat_session(user_id=user_id, title=message[:30])
                session_id = str(session["_id"])

            await websocket.send_json({"type": "session_meta", "session_id": session_id})
            
            past_messages = list_session_messages(user_id, session_id) if session_id else []
            chat_history = [{"role": msg["role"], "content": msg["message"]} for msg in past_messages][-10:]

            save_chat_message(user_id, session_id, "user", message)

            # ─────────────────────────────────────────────────────────
            # Step 2: Check cache BEFORE doing any work
            # ─────────────────────────────────────────────────────────
            cached = get_cached_answer(user_id, message)
            if cached:
                # Send only the `end` frame — avoids a requestAnimationFrame
                # race where streamingText is reset to "" by `end` before the
                # scheduled animation frame (triggered by `token`) can paint.
                save_chat_message(user_id, session_id, "assistant", cached["answer"], cached["sources"])
                await websocket.send_json({
                    "type": "end",
                    "full_answer": cached["answer"],
                    "sources": cached["sources"],
                    "from_cache": True
                })
                continue

            matches = retrieve_similar_chunks(question=message, user_id=user_id, top_k=top_k)

            # --- MCP WEB FETCHING (By URL) ---
            urls = re.findall(r'(https?://[^\s]+)', message)
            for url in urls:
                try:
                    matches.clear()
                    web_content = await async_fetch_url(url)
                    matches.append({
                        "filename": url,
                        "text": f"--- START OF WEBPAGE CONTENT ({url}) ---\n{web_content}\n--- END OF WEBPAGE CONTENT ---"
                    })
                except Exception as e:
                    matches.append({
                        "filename": url,
                        "text": f"The user asked you to summarize {url}, but the system failed to fetch it. Tell the user: 'I could not fetch the website because of an error.'"
                    })
            # ------------------------

            # --- MCP TAVILY SEARCH (By AI Intent) ---
            if await needs_web_search(message):
                try:
                    print(f"--> AI decided to use Tavily for: {message}")
                    matches.clear() # Clear document chunks so it focuses entirely on the web
                    search_results = await async_tavily_search(message)
                    matches.append({
                        "filename": "Tavily Internet Search",
                        "text": f"--- TAVILY WEB SEARCH RESULTS ---\n{search_results}\n---------------------------------"
                    })
                except Exception as e:
                    print(f"Tavily fetch error: {e}")
            # ------------------------

            full_answer = ""
            async for chunk in stream_query_response(content={"question": message, "matches": matches}, chat_history=chat_history):
                full_answer += chunk
                await websocket.send_json({"type": "token", "content": chunk})
                await asyncio.sleep(0.01)  # Small yield so browser can paint each chunk
            
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

            #    Only cache real document answers, not errors or greetings
            if not is_error and not is_fallback and not is_tagged_general:
                set_cached_answer(user_id, message, full_answer, sources)

            await websocket.send_json({
                "type": "end",
                "sources": sources,
                "full_answer": full_answer
            })

    except WebSocketDisconnect:
        print("WebSocket client disconnected")

@router.post("/")
async def chat(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])

    if payload.session_id:
        session = get_user_session(payload.session_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = payload.session_id
    else:
        session = create_chat_session(user_id=user_id, title=payload.message[:30])
        session_id = str(session["_id"])

    past_messages = list_session_messages(user_id, session_id) if payload.session_id else []
    chat_history = [{"role": msg["role"], "content": msg["message"]} for msg in past_messages][-10:] # get last 10 messages for context

    save_chat_message(user_id, session_id, "user", payload.message)

    matches = retrieve_similar_chunks(
        question=payload.message,
        user_id=user_id,
        top_k=payload.top_k
    )

    # --- MCP WEB FETCHING (By URL) ---
    urls = re.findall(r'(https?://[^\s]+)', payload.message)
    for url in urls:
        try:
            matches.clear()
            web_content = await async_fetch_url(url)
            matches.append({
                "filename": url,
                "text": f"--- START OF WEBPAGE CONTENT ({url}) ---\n{web_content}\n--- END OF WEBPAGE CONTENT ---"
            })
        except Exception as e:
            matches.append({
                "filename": url,
                "text": f"The user asked you to summarize {url}, but the system failed to fetch it. Tell the user: 'I could not fetch the website because of an error.'"
            })
    # ------------------------

    # --- MCP TAVILY SEARCH (By AI Intent) ---
    if await needs_web_search(payload.message):
        try:
            print(f"--> AI decided to use Tavily for: {payload.message}")
            matches.clear() # Clear document chunks
            search_results = await async_tavily_search(payload.message)
            matches.append({
                "filename": "Tavily Internet Search",
                "text": f"--- TAVILY WEB SEARCH RESULTS ---\n{search_results}\n---------------------------------"
            })
        except Exception as e:
            print(f"Tavily fetch error: {e}")
    # ------------------------

    answer = await generate_query_response(
        content={"question": payload.message, "matches": matches},
        chat_history=chat_history
    )

    is_error = "⚠️" in answer or "Error" in answer
    is_fallback = "I don't know based on the provided document" in answer
    is_tagged_general = "[GENERAL]" in answer

    if is_tagged_general:
        answer = answer.replace("[GENERAL]", "").strip()

    if is_general_question(payload.message) or is_error or is_fallback or is_tagged_general:
        sources = []
    else:
        unique_filenames = []
        for m in matches:
            if m["filename"] not in unique_filenames:
                unique_filenames.append(m["filename"])
        
        sources = [{"filename": fn} for fn in unique_filenames]

    save_chat_message(user_id, session_id, "assistant", answer, sources)

    return {
        "session_id": session_id,
        "answer": answer,
        "sources": sources
    }

@router.get("/sessions")
def get_sessions(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    sessions = list_user_sessions(user_id)
    return [
        {"session_id": str(session["_id"]), "title": session["title"]}
        for session in sessions
    ]

@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    messages = list_session_messages(user_id, session_id)
    return [
        {
            "role": msg["role"],
            "message": msg["message"],
            "sources": msg.get("sources", [])
        }
        for msg in messages
    ]

@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    delete_chat_session(user_id, session_id)
    return {"message": "Session deleted successfully"}