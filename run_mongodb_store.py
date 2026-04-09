from services.mongodb_service import store_chunks_in_mongodb
from services.embedding_service import generate_embedding

sample_text_1 = "This document explains artificial intelligence and machine learning concepts."
sample_text_2 = "Vector databases help store embeddings and retrieve similar chunks."

sample_chunks = [
    {
        "chunk_id": "real_test_1",
        "filename": "real_test.pdf",
        "page": 1,
        "chunk_index": 0,
        "text": sample_text_1,
        "embedding": generate_embedding(sample_text_1)
    },
    {
        "chunk_id": "real_test_2",
        "filename": "real_test.pdf",
        "page": 1,
        "chunk_index": 1,
        "text": sample_text_2,
        "embedding": generate_embedding(sample_text_2)
    }
]

store_chunks_in_mongodb(sample_chunks)
print("Inserted real test chunks.")