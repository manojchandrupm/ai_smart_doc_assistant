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

    sources = [
        {
            "filename": m["filename"],
            "page": m["page"],
            "chunk_index": m["chunk_index"]
        }
        for m in matches
    ]

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