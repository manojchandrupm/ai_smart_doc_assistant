from services.mongodb_retrieval_service import retrieve_similar_chunks_from_mongodb
from services.embedding_service import generate_embedding

query = "machine learning concepts"
query_embedding = generate_embedding(query)

results = retrieve_similar_chunks_from_mongodb(query_embedding, top_k=3)

print("Results:", results)
print("Number of results:", len(results))

for r in results:
    print("-----")
    print("Score:", r["score"])
    print("Text:", r["text"][:200])