from datetime import datetime, timezone
from bson import ObjectId
from services.mongodb_service import chat_sessions_collection, chat_messages_collection

def create_chat_session(user_id: str, title: str = "New Chat"):
    session = {
        "user_id": user_id,
        "title": title,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    result = chat_sessions_collection.insert_one(session)
    session["_id"] = result.inserted_id
    return session

def get_user_session(session_id: str, user_id: str):
    return chat_sessions_collection.find_one({
        "_id": ObjectId(session_id),
        "user_id": user_id
    })

def save_chat_message(user_id: str, session_id: str, role: str, message: str, sources=None):
    chat_messages_collection.insert_one({
        "user_id": user_id,
        "session_id": session_id,
        "role": role,
        "message": message,
        "sources": sources or [],
        "created_at": datetime.now(timezone.utc)
    })

def list_user_sessions(user_id: str):
    return list(chat_sessions_collection.find({"user_id": user_id}).sort("updated_at", -1))

def list_session_messages(user_id: str, session_id: str):
    return list(chat_messages_collection.find({
        "user_id": user_id,
        "session_id": session_id
    }).sort("created_at", 1))