import os
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException
from config import env
from models.schemas import MultiUploadResponse, FileUploadResult, FileUploadError
from services.pdf_service import extract_text_from_pdf
from services.chunking_service import create_document_chunks
from services.embedding_service import generate_embedding
from services.Qdrant_service import store_chunks_in_qdrant, delete_document_from_qdrant

router = APIRouter(prefix="/upload", tags=["Upload"])


# ─────────────────────────────────────────────────────────
# Upload one or more PDF files at once
# Frontend sends all files under the key "files"
# Returns per-file results so the UI can show which
# files succeeded and which failed independently.
# ─────────────────────────────────────────────────────────
@router.post("/", response_model=MultiUploadResponse)
async def upload_pdfs(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

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

            store_chunks_in_qdrant(enriched_chunks)

            uploaded.append(FileUploadResult(filename=filename, total_chunks=len(enriched_chunks)))

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
# Returns every PDF filename saved in UPLOAD_DIR.
# The frontend uses this to render the Documents tab list.
# ─────────────────────────────────────────────────────────
@router.get("/documents")
def list_documents():
    os.makedirs(env.UPLOAD_DIR, exist_ok=True)
    files = [f for f in os.listdir(env.UPLOAD_DIR) if f.lower().endswith(".pdf")]
    return {"documents": files}


# ─────────────────────────────────────────────────────────
# Delete a document (disk + Qdrant vectors)
# Step 1 — Remove vectors from Qdrant (AI stops answering from it)
# Step 2 — Delete the actual PDF file from disk
# The order matters: Qdrant first so even if disk deletion fails,
# the AI will no longer use the document.
# ─────────────────────────────────────────────────────────
@router.delete("/documents/{filename}")
def delete_document(filename: str):
    file_path = os.path.join(env.UPLOAD_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    # Step 1: Remove from Qdrant
    delete_document_from_qdrant(filename)

    # Step 2: Remove from disk
    os.remove(file_path)

    return {"message": f"'{filename}' deleted successfully."}
