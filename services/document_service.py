# app/services/document_service.py
from datetime import datetime, timezone
from bson import ObjectId
from services.mongodb_service import documents_collection

def create_document_record(user_id: str, filename: str, storage_path: str, vector_backend: str = "qdrant"):
    doc = {
        "user_id": user_id,
        "filename": filename,
        "upload_time": datetime.now(timezone.utc),
        "storage_path": storage_path,
        "vector_backend": vector_backend,
        "status": "processed"
    }
    result = documents_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc

def list_user_documents(user_id: str):
    return list(documents_collection.find({"user_id": user_id}))

def get_user_document(document_id: str, user_id: str):
    return documents_collection.find_one({
        "_id": ObjectId(document_id),
        "user_id": user_id
    })

def delete_user_document(document_id: str, user_id: str):
    return documents_collection.delete_one({
        "_id": ObjectId(document_id),
        "user_id": user_id
    })