from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
import json
import asyncio
from models.chat_models import ChatRequest
from core.dependencies import get_current_user
from core.security import decode_access_token
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
from services.user_query_response_service import generate_query_response, stream_query_response

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket, token: str):
    await websocket.accept()
    
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=1008)
            return
        user = get_user_by_id(user_id)
        if not user:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
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

            matches = retrieve_similar_chunks(question=message, user_id=user_id, top_k=top_k)

            full_answer = ""
            async for chunk in stream_query_response(content={"question": message, "matches": matches}, chat_history=chat_history):
                full_answer += chunk
                await websocket.send_json({"type": "token", "content": chunk})
                await asyncio.sleep(0.01)  # Small yield so browser can paint each chunk
            
            from routes.query_router import is_general_question
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

    answer = await generate_query_response(
        content={"question": payload.message, "matches": matches},
        chat_history=chat_history
    )

    from routes.query_router import is_general_question
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