import os
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Query
from config import env
from models.schemas import MultiUploadResponse, FileUploadResult, FileUploadError
from services.pdf_service import extract_text_from_pdf
from services.chunking_service import create_document_chunks
from services.embedding_service import generate_embedding
from services.Qdrant_service import store_chunks_in_qdrant, delete_document_from_qdrant
from services.mongodb_service import store_chunks_in_mongodb, delete_document_from_mongodb

router = APIRouter(prefix="/upload", tags=["Upload"])

def _is_quota_error_msg(msg: str) -> bool:
    """Check if an error message indicates an API quota exceeded error."""
    return 'quota exceeded' in msg.lower() or '429' in msg or 'resource_exhausted' in msg.upper()


@router.post("/", response_model=MultiUploadResponse)
async def upload_pdfs(files: List[UploadFile] = File(...), db_choice: str = Form("qdrant")):
    
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    if db_choice not in ("qdrant", "mongodb"):
        raise HTTPException(status_code=400, detail="db_choice must be 'qdrant' or 'mongodb'.")

    os.makedirs(env.UPLOAD_DIR, exist_ok=True)

    uploaded: List[FileUploadResult] = []
    errors: List[FileUploadError] = []

    for file in files:
        filename = file.filename or "unknown.pdf"

        if not filename.lower().endswith(".pdf"):
            errors.append(FileUploadError(filename=filename, error="Only PDF files are allowed."))
            continue

        file_path = os.path.join(env.UPLOAD_DIR, filename)

        try:
            content = await file.read()

            with open(file_path, "wb") as f:
                f.write(content)

            pages = extract_text_from_pdf(file_path)

            if not pages:
                errors.append(FileUploadError(filename=filename, error="No extractable text found in PDF."))
                continue

            chunks = create_document_chunks(
                filename=filename,
                pages=pages,
                chunk_size=env.CHUNK_SIZE,
                overlap=env.CHUNK_OVERLAP
            )

            enriched_chunks = []
            for chunk in chunks:
                embedding = generate_embedding(chunk["text"])
                chunk["embedding"] = embedding
                enriched_chunks.append(chunk)

            if db_choice == "mongodb":
                store_chunks_in_mongodb(enriched_chunks)
            else:
                store_chunks_in_qdrant(enriched_chunks)

            uploaded.append(FileUploadResult(filename=filename, 
            total_chunks=len(enriched_chunks),
            db_choice=db_choice
            ))

        except RuntimeError as e:
            error_msg = str(e)
            if _is_quota_error_msg(error_msg):
                # Abort the whole upload immediately with 429 so the client knows to back off
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"API quota exceeded while processing '{filename}': "
                        "The Gemini API rate limit has been reached. "
                        "Please wait a moment and try again, or check your API quota in Google AI Studio."
                    )
                )
            errors.append(FileUploadError(filename=filename, error=error_msg))

        except Exception as e:
            errors.append(FileUploadError(filename=filename, error=str(e)))

    total = len(uploaded)
    failed = len(errors)
    message = f"{total} file(s) uploaded successfully."
    if failed:
        message += f" {failed} file(s) failed."

    return MultiUploadResponse(message=message, uploaded=uploaded, errors=errors)


# ─────────────────────────────────────────────────────────
# List all uploaded documents
# ─────────────────────────────────────────────────────────
@router.get("/documents")
def list_documents():
    os.makedirs(env.UPLOAD_DIR, exist_ok=True)
    files = [f for f in os.listdir(env.UPLOAD_DIR) if f.lower().endswith(".pdf")]
    return {"documents": files}


# ─────────────────────────────────────────────────────────
# Delete a document (disk + Qdrant vectors + MongoDB vectors)
# ─────────────────────────────────────────────────────────
@router.delete("/documents/{filename}")
def delete_document(filename: str):
    file_path = os.path.join(env.UPLOAD_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    # Step 1: Remove from BOTH vector stores to guarantee cleanup
    delete_document_from_mongodb(filename)
    delete_document_from_qdrant(filename)

    # Step 2: Remove from disk
    os.remove(file_path)

    return {"message": f"'{filename}' deleted successfully."}
