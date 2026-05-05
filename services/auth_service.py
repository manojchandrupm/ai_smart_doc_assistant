from datetime import datetime, timezone
from bson import ObjectId
from services.mongodb_service import users_collection
from core.security import hash_password, verify_password, create_access_token

def get_user_by_email(email: str):
    return users_collection.find_one({"email": email})

def create_user(email: str, password: str):
    user_doc = {
        "email": email,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc),
        "is_active": True
    }
    result = users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return user_doc

def authenticate_user(email: str, password: str):
    user = get_user_by_email(email)
    if not user:
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    return user

def generate_token_for_user(user: dict) -> str:
    return create_access_token(
        data={
            "sub": str(user["_id"]),
            "email": user["email"]
        }
    )

def user_to_response(user: dict):
    return {
        "id": str(user["_id"]),
        "email": user["email"]
    }

def get_user_by_id(user_id: str):
    return users_collection.find_one({"_id": ObjectId(user_id)})


def get_or_create_google_user(email: str, name: str, google_id: str) -> dict:
    """
    Find an existing user by email, or create one for Google OAuth users.
    Google users won't have a password_hash — they authenticate via Google.
    """
    user = get_user_by_email(email)
    if user:
        # If user registered normally before, just link google_id
        if not user.get("google_id"):
            users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"google_id": google_id}}
            )
        return user

    # Create a new Google-only user (no password)
    user_doc = {
        "email": email,
        "name": name,
        "google_id": google_id,
        "password_hash": None,       # No password for OAuth users
        "created_at": datetime.now(timezone.utc),
        "is_active": True,
        "auth_provider": "google"
    }
    result = users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return user_doc
