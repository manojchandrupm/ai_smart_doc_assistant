from services.mongodb_service import collection

def retrieve_similar_chunks_from_mongodb(query_embedding, user_id, top_k=5):
    pipeline = [
        {
            "$vectorSearch": {
                "index": "embedding_vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 100,
                "limit": top_k,
                "filter": {
                    "user_id": user_id
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "chunk_id": 1,
                "user_id": 1,
                "document_id": 1,
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