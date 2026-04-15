"""
Temporary debug endpoint - REMOVE AFTER DEBUGGING
"""
from fastapi import APIRouter
from config import env

router = APIRouter(prefix="/debug", tags=["Debug"])

@router.get("/env-check")
def check_env():
    """Check if critical env vars are set (does NOT expose values)."""
    jwt_key = env.JWT_SECRET_KEY
    return {
        "JWT_SECRET_KEY_set": bool(jwt_key and jwt_key.strip()),
        "JWT_SECRET_KEY_length": len(jwt_key.strip()) if jwt_key and jwt_key.strip() else 0,
        "JWT_ALGORITHM": env.JWT_ALGORITHM,
        "ACCESS_TOKEN_EXPIRE_MINUTES": env.ACCESS_TOKEN_EXPIRE_MINUTES,
        "MONGO_URI_set": bool(env.MONGO_URI),
        "UPLOAD_DIR": env.UPLOAD_DIR,
    }
