from fastapi import APIRouter, Depends, HTTPException
from core.dependencies import get_current_user
from services.document_service import get_user_document, delete_user_document, list_user_documents
from services.Qdrant_service import delete_document_from_qdrant
from services.mongodb_service import delete_document_from_mongodb
import os

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.get("/")
def get_documents(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    docs = list_user_documents(user_id)

    return [
        {
            "id": str(doc["_id"]),
            "filename": doc["filename"],
            "vector_backend": doc.get("vector_backend", "qdrant"),
            "status": doc.get("status", "processed")
        }
        for doc in docs
    ]


@router.delete("/{document_id}")
def delete_document(document_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])

    document = get_user_document(document_id, user_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    filename = document["filename"]
    file_path = document.get("storage_path")
    vector_backend = document.get("vector_backend", "qdrant")

    # Delete from the correct vector store based on what was used at upload time
    if vector_backend == "mongodb":
        delete_document_from_mongodb(filename=filename, user_id=user_id)
    else:
        delete_document_from_qdrant(filename=filename, user_id=user_id)

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    delete_user_document(document_id, user_id)

    return {"message": "Document deleted successfully"}
