import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from config import env
from models.schemas import UploadResponse
from services.pdf_service import extract_text_from_pdf
from services.chunking_service import create_document_chunks
from services.embedding_service import generate_embedding
from services.Qdrant_service import store_chunks_in_qdrant

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("/", response_model=UploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    os.makedirs(env.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(env.UPLOAD_DIR, file.filename)

    try:
        content = await file.read()

        with open(file_path, "wb") as f:
            f.write(content)

        pages = extract_text_from_pdf(file_path)

        if not pages:
            raise HTTPException(status_code=400, detail="No extractable text found in PDF")

        chunks = create_document_chunks(
            filename=file.filename,
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

        return UploadResponse(
            message="PDF processed and stored in Qdrant successfully",
            filename=file.filename,
            total_chunks=len(enriched_chunks)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload pipeline failed: {str(e)}")