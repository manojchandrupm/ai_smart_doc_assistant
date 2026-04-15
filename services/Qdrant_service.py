from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue,PayloadSchemaType
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

    qdrant_client.create_payload_index(
        collection_name=env.COLLECTION_NAME,
        field_name="filename",
        field_schema=PayloadSchemaType.KEYWORD
    )

    qdrant_client.create_payload_index(
        collection_name=env.COLLECTION_NAME,
        field_name="user_id",
        field_schema=PayloadSchemaType.KEYWORD
    )

    qdrant_client.create_payload_index(
        collection_name=env.COLLECTION_NAME,
        field_name="document_id",
        field_schema=PayloadSchemaType.KEYWORD
    )    
    
def store_chunks_in_qdrant(chunks: list):
    if not chunks:
        return

    points = []
    vector_size = len(chunks[0]["embedding"])
    ensure_collection_exists(vector_size)

    for chunk in chunks:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"]))

        points.append(
            PointStruct(
                id=point_id,
                vector=chunk["embedding"],
                payload={
                    "chunk_id": chunk["chunk_id"],
                    "user_id": chunk["user_id"],               
                    "document_id": chunk["document_id"],       
                    "filename": chunk["original_filename"],   
                    "stored_filename": chunk["stored_filename"],  
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
# Delete all vector points for a specific document
# ─────────────────────────────────────────────────────────
def delete_document_from_qdrant(filename: str,user_id: str):

    qdrant_client.delete(
        collection_name=env.COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="filename",
                    match=MatchValue(value=filename)
                ),
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            ]
        )
    )