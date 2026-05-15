import asyncio
from services.mongodb_service import users_collection, collection
from services.embedding_service import generate_embedding

def test_pipeline():
    user = users_collection.find_one({})
    if not user:
        return
    user_id = str(user['_id'])
    
    question = 'test'
    query_embedding = generate_embedding(question)
    
    pipeline2 = [
        {
            '$vectorSearch': {
                'index': 'embedding_vector_index',
                'path': 'embedding',
                'queryVector': query_embedding,
                'numCandidates': 200,
                'limit': 100
            }
        }
    ]
    try:
        results2 = list(collection.aggregate(pipeline2))
        print(f'Pipeline without match returned {len(results2)} matches.')
        
        pipeline = pipeline2 + [
            {
                '$match': {
                    'user_id': user_id
                }
            }
        ]
        results = list(collection.aggregate(pipeline))
        print(f'Pipeline with match returned {len(results)} matches.')
    except Exception as e:
        print(f'Error: {e}')

test_pipeline()
