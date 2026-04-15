from fastapi import FastAPI
from contextlib import asynccontextmanager
from config import env
from models.schemas import HealthResponse
from routes.upload_router import router as upload_router
from routes.query_router import router as query_router
from routes.auth_router import router as auth_router
from routes.chat import router as chat_router
from routes.documents import router as documents_router
from routes.debug_router import router as debug_router
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from services.Qdrant_service import qdrant_client


# ─────────────────────────────────────────────────────────
# On startup: ensure the "filename" payload index exists.
# This is needed so Qdrant can filter/delete by filename.
# Safe to run every time — does nothing if index already exists.
# ─────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    yield  # App runs here


app = FastAPI(
    title=env.APP_NAME,
    version=env.APP_VERSION,
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(upload_router)
app.include_router(query_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(debug_router)  # TODO: remove after debugging

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