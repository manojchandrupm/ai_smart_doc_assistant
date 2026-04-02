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


env = Settings()

