from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from config import env
from models.schemas import HealthResponse
from routes.upload_router import router as upload_router
from routes.query_router import router as query_router
from routes.auth_router import router as auth_router
from routes.chat import router as chat_router
from routes.documents import router as documents_router
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from services.Qdrant_service import qdrant_client
from services.mongodb_service import (
    chat_messages_collection,
    chat_sessions_collection,
    users_collection
)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.rate_limiter import limiter


# ─────────────────────────────────────────────────────────
# On startup: ensure the "filename" payload index exists.
# This is needed so Qdrant can filter/delete by filename.
# Safe to run every time — does nothing if index already exists.
# ─────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─────────────────────────────────────────────────────────
    # Qdrant: ensure payload indexes exist for filtering
    # ─────────────────────────────────────────────────────────
    collections = qdrant_client.get_collections().collections
    collection_names = [c.name for c in collections]
    if env.COLLECTION_NAME in collection_names:
        # index for filename
        qdrant_client.create_payload_index(
            collection_name=env.COLLECTION_NAME,
            field_name="filename",
            field_schema="keyword"
        )
        # index for user_id
        qdrant_client.create_payload_index(
            collection_name=env.COLLECTION_NAME,
            field_name="user_id",
            field_schema="keyword"
        )
        # index for document_id
        qdrant_client.create_payload_index(
            collection_name=env.COLLECTION_NAME,
            field_name="document_id",
            field_schema="keyword"
        )
    # ─────────────────────────────────────────────────────────
    # MongoDB: ensure compound indexes exist
    # Safe to call every startup — MongoDB ignores duplicates
    # ─────────────────────────────────────────────────────────
    import pymongo
    chat_messages_collection.create_index([("user_id", pymongo.ASCENDING), ("session_id", pymongo.ASCENDING)])
    chat_sessions_collection.create_index([("user_id", pymongo.ASCENDING), ("updated_at", pymongo.DESCENDING)])
    users_collection.create_index("email", unique=True)
    
    yield  # App runs here
app = FastAPI(
    title=env.APP_NAME,
    version=env.APP_VERSION,
    lifespan=lifespan
)

# Attach limiter to app state and register 429 handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(upload_router)
app.include_router(query_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)

@app.get("/")
async def serve_home():
    return FileResponse("static/index.html")



# @app.get("/", response_model=HealthResponse)
# async def root():
#     return HealthResponse(
#         status="ok",
#         app_name=env.APP_NAME,
#         version=env.APP_VERSION
#     )