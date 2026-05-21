from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
import json
import asyncio
import re
from models.chat_models import ChatRequest
from core.dependencies import get_current_user
from core.security import decode_access_token
from core.utils import is_general_question
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
from services.user_query_response_service import generate_query_response
from mcp_client import async_fetch_url
from agent.web_search_agent import run_web_search_agent
from services.router_service import route_query
from routes.browser_agent import run_browser_agent
from agent.rag_agent import run_rag_agent
from agent.flight_search_agent import run_flight_search_agent
from agent.ecommerce_research_agent import run_ecommerce_research_agent
from agent.hotel_comparison_agent import run_hotel_comparison_agent

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
            db_choice = payload.get("db_choice")
            
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

            # # Check cache BEFORE doing any work
            # cached = get_cached_answer(user_id, message)
            # if cached:
            #     save_chat_message(user_id, session_id, "assistant", cached["answer"], cached["sources"])
            #     words = cached["answer"].split(" ")
            #     for i in range(0, len(words), 2):
            #         chunk = " ".join(words[i:i+2]) + " "
            #         await websocket.send_json({"type": "token", "content": chunk})
            #         await asyncio.sleep(0.05)
            #     await websocket.send_json({
            #         "type": "end",
            #         "full_answer": cached["answer"],
            #         "sources": cached["sources"],
            #         "from_cache": True
            #     })
            #     continue

            # ─────────────────────────────────────────────────────────
            # Step 2: AI Router — decide which agent handles this query
            # ─────────────────────────────────────────────────────────
            route = await route_query(message, chat_history=chat_history)
            print(f"[AI Router] Query routed to: {route}")

            # ══════════════════════════════════════════════════════════
            # Agent Selection 
            # ══════════════════════════════════════════════════════════
            save_fn = lambda ans, src: save_chat_message(user_id, session_id, "assistant", ans, src)

            if route == "browser_agent":
                await run_browser_agent(message, websocket, save_fn, chat_history=chat_history)
                continue  

            elif route == "web_search_agent":
                await run_web_search_agent(message, websocket, save_fn)
                continue  
            
            elif route == "rag_agent":
                await run_rag_agent(
                    message=message,
                    websocket=websocket,
                    user_id=user_id,
                    session_id=session_id,
                    chat_history=chat_history,
                    top_k=top_k,
                    db_choice=db_choice
                )
            elif route == "flight_search_agent":
                await run_flight_search_agent(message, websocket, save_fn, chat_history)
                continue 

            elif route == "ecommerce_research_agent":
                await run_ecommerce_research_agent(message, websocket, save_fn, chat_history)   
                continue

            elif route == "hotel_comparison_agent":
                await run_hotel_comparison_agent(message, websocket, save_fn, chat_history)
                continue


    except WebSocketDisconnect:
        print("WebSocket client disconnected")

# @router.post("/")
# async def chat(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
#     user_id = str(current_user["_id"])

#     if payload.session_id:
#         session = get_user_session(payload.session_id, user_id)
#         if not session:
#             raise HTTPException(status_code=404, detail="Session not found")
#         session_id = payload.session_id
#     else:
#         session = create_chat_session(user_id=user_id, title=payload.message[:30])
#         session_id = str(session["_id"])

#     past_messages = list_session_messages(user_id, session_id) if payload.session_id else []
#     chat_history = [{"role": msg["role"], "content": msg["message"]} for msg in past_messages][-10:] # get last 10 messages for context

#     save_chat_message(user_id, session_id, "user", payload.message)

#     matches = retrieve_similar_chunks(
#         question=payload.message,
#         user_id=user_id,
#         top_k=payload.top_k
#     )

#     # --- MCP WEB FETCHING (By URL) ---
#     url_pattern = r'(https?://[^\s<>"]+|www\.[^\s<>"]+|[a-zA-Z0-9.-]+\.(?:com|org|net|edu|gov|io|co|in|ai)\b(?:/[^\s<>"]*)?)'
#     urls = re.findall(url_pattern, payload.message)
#     if urls:
#         matches.clear()
#         for raw_url in urls:
#             raw_url = raw_url.rstrip('.,;!?)("\'')
#             fetch_url = raw_url if raw_url.startswith('http') else 'https://' + raw_url
#             try:
#                 web_content = await async_fetch_url(fetch_url)
#                 matches.append({
#                     "filename": raw_url,
#                     "text": f"--- START OF WEBPAGE CONTENT ({raw_url}) ---\n{web_content}\n--- END OF WEBPAGE CONTENT ---"
#                 })
#             except Exception as e:
#                 matches.append({
#                     "filename": raw_url,
#                     "text": f"The user asked you to summarize {raw_url}, but the system failed to fetch it. Tell the user: 'I could not fetch the website because of an error.'"
#                 })
#     # ------------------------

#     # ------------------------

#     answer = await generate_query_response(
#         content={"question": payload.message, "matches": matches},
#         chat_history=chat_history
#     )

#     is_error = "⚠️" in answer or "Error" in answer
#     is_fallback = "I don't know based on the provided document" in answer
#     is_tagged_general = "[GENERAL]" in answer

#     if is_tagged_general:
#         answer = answer.replace("[GENERAL]", "").strip()

#     if is_general_question(payload.message) or is_error or is_fallback or is_tagged_general:
#         sources = []
#     else:
#         unique_filenames = []
#         for m in matches:
#             if m["filename"] not in unique_filenames:
#                 unique_filenames.append(m["filename"])
        
#         sources = [{"filename": fn} for fn in unique_filenames]

#     save_chat_message(user_id, session_id, "assistant", answer, sources)

#     return {
#         "session_id": session_id,
#         "answer": answer,
#         "sources": sources
#     }

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