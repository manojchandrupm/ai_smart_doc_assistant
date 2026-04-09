from services.mongodb_service import collection

def retrieve_similar_chunks_from_mongodb(query_embedding, top_k=5):
    pipeline = [
        {
            "$vectorSearch": {
                "index": "embedding_vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 100,
                "limit": top_k
            }
        },
        {
            "$project": {
                "_id": 0,
                "chunk_id": 1,
                "filename": 1,
                "page": 1,
                "chunk_index": 1,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]

    results = list(collection.aggregate(pipeline))
    return results