from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue
)
from config import env
import uuid

qdrant_client = QdrantClient(
    url=env.QDRANT_URL,
    api_key=env.QDRANT_API_KEY,
)

def ensure_collection_exists(vector_size: int):
    collections = qdrant_client.get_collections().collections
    collection_names = [collection.name for collection in collections]
    if env.COLLECTION_NAME not in collection_names:
        qdrant_client.create_collection(
            collection_name=env.COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
        )

    # Create a keyword index on "filename" so we can filter and delete by it.
    # Qdrant requires an index before allowing payload-based filters on delete.
    # This call is safe to run every time — it does nothing if the index already exists.
    qdrant_client.create_payload_index(
        collection_name=env.COLLECTION_NAME,
        field_name="filename",
        field_schema="keyword"
    )
def store_chunks_in_qdrant(chunks: list):
    if not chunks:
        return

    points = []
    vector_size = len(chunks[0]["embedding"])
    ensure_collection_exists(vector_size)

    for chunk in chunks:
        # Generate a unique UUID from the chunk_id string.
        # This ensures each chunk always gets the same unique ID,
        # and uploading a new document never overwrites another document's chunks.
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"]))
        points.append(
            PointStruct(

                id=point_id,
                vector=chunk["embedding"],
                payload={
                    "chunk_id": chunk["chunk_id"],
                    "filename": chunk["filename"],
                    "page": chunk["page"],
                    "chunk_index": chunk["chunk_index"],
                    "text": chunk["text"]
                }
            )
        )

    qdrant_client.upsert(
        collection_name=env.COLLECTION_NAME,
        points=points
    )
# ─────────────────────────────────────────────────────────
# CHANGE 3 — Delete all vector points for a specific document
# ─────────────────────────────────────────────────────────
def delete_document_from_qdrant(filename: str):
    """
    Deletes every vector point in Qdrant that belongs to the given filename.
    After deletion, the AI will no longer use that document to answer questions.
    How it works:
    - Each stored point has a payload with "filename"
    - We use Qdrant's filter to find all points where filename matches
    - Then we delete all those matching points at once
    """
    qdrant_client.delete(
        collection_name=env.COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="filename",
                    match=MatchValue(value=filename)
                )
            ]
        )
    )