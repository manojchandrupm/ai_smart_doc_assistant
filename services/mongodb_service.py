from datetime import datetime
from pymongo import MongoClient
from config import env

client = MongoClient(env.MONGO_URI)
db = client[env.MONGO_DB_NAME]
collection = db[env.MONGO_COLLECTION_NAME]
users_collection = db["users"]
documents_collection = db["documents"]
chat_sessions_collection = db["chat_sessions"]
chat_messages_collection = db["chat_messages"]

def store_chunks_in_mongodb(chunks):
    docs = []

    for chunk in chunks:
        docs.append({
            "chunk_id": chunk["chunk_id"],
            "filename": chunk["filename"],
            "page": chunk["page"],
            "chunk_index": chunk["chunk_index"],
            "text": chunk["text"],
            "embedding": chunk["embedding"],
            "uploaded_at": datetime.utcnow()
        })

    if docs:
        collection.insert_many(docs)


def get_chunks_by_filename(filename: str):
    return list(collection.find({"filename": filename}, {"_id": 0}))


def delete_document_from_mongodb(filename: str):
    result = collection.delete_many({"filename": filename})
    return result.deleted_count