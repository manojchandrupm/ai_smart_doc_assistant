from typing import List, Dict
from qdrant_client import QdrantClient
from config import env
from services.embedding_service import generate_embedding


qdrant_client = QdrantClient(
    url=env.QDRANT_URL,
    api_key=env.QDRANT_API_KEY,
)

def retrieve_similar_chunks(question, top_k = 3) -> List[Dict]:
    """
    Convert the user question into an embedding,
    search Qdrant, and return top-k matching chunks.
    """
    query_vector = generate_embedding(question)

    search_results = qdrant_client.query_points(
        collection_name=env.COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True
    )

    matches = []

    for result in search_results.points:
        payload = result.payload or {}

        matches.append({
            "chunk_id": payload.get("chunk_id", ""),
            "filename": payload.get("filename", ""),
            "page": payload.get("page", 0),
            "chunk_index": payload.get("chunk_index", 0),
            "score": float(result.score),
            "text": payload.get("text", "")
        })

    return matches

