import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_URL = os.getenv("QDRANT_URL")
    COLLECTION_NAME = os.getenv("COLLECTION_NAME")
    UPLOAD_DIR = os.getenv("UPLOAD_DIR")
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP"))
    APP_NAME = os.getenv("APP_NAME", "AI Smart Document Assistant")
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
    MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME")

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")

env = Settings()

