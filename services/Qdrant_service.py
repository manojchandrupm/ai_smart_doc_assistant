from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from config import env


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

def store_chunks_in_qdrant(chunks: list):
    if not chunks:
        return

    points = []
    vector_size = len(chunks[0]["embedding"])
    ensure_collection_exists(vector_size)

    for idx, chunk in enumerate(chunks):
        points.append(
            PointStruct(
                id=idx + 1,
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