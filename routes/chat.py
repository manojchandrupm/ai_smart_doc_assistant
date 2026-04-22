from fastapi import APIRouter, Depends, HTTPException
from models.chat_models import ChatRequest
from core.dependencies import get_current_user
from services.chat_service import (
    create_chat_session,
    get_user_session,
    save_chat_message,
    list_user_sessions,
    list_session_messages
)
from services.retrieval_service import retrieve_similar_chunks
from services.user_query_response_service import generate_query_response

router = APIRouter(prefix="/chat", tags=["Chat"])

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

    save_chat_message(user_id, session_id, "user", payload.message)

    matches = retrieve_similar_chunks(
        question=payload.message,
        user_id=user_id,
        top_k=payload.top_k
    )

    answer = await generate_query_response(
        content={"question": payload.message, "matches": matches},
        chat_history=[]
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