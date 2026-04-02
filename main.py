from fastapi import FastAPI
from config import env
from models.schemas import HealthResponse
from routes.upload_router import router as upload_router
from routes.query_router import router as query_router
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title=env.APP_NAME,
    version=env.APP_VERSION
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(upload_router)
app.include_router(query_router)

@app.get("/")
async def serve_home():
    return FileResponse("static/index.html")

#
# @app.get("/", response_model=HealthResponse)
# async def root():
#     return HealthResponse(
#         status="ok",
#         app_name=env.APP_NAME,
#         version=env.APP_VERSION
#     )
