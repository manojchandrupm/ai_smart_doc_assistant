from fastapi import APIRouter, HTTPException, Depends
from models.schemas import QueryRequest, QueryResponse, RetrievedMatch, QueryReply
from services.retrieval_service import retrieve_similar_chunks
from services.mongodb_retrieval_service import retrieve_similar_chunks_from_mongodb
from services.embedding_service import generate_embedding
from services.user_query_response_service import generate_query_response, stream_query_response
from fastapi.responses import StreamingResponse
import asyncio
from core.dependencies import get_current_user

router = APIRouter(prefix="/query", tags=["Query"])


# ─────────────────────────────────────────────────────────
# Detect general/greeting questions
# ─────────────────────────────────────────────────────────
GENERAL_KEYWORDS = [
    "hi", "hello", "hey", "how are you", "who are you",
    "what are you", "good morning", "good evening", "good night",
    "thanks", "thank you", "bye", "goodbye", "what can you do",
    "what is your name"
]
def is_general_question(question: str) -> bool:
    q = question.lower().strip()
    return any(keyword in q for keyword in GENERAL_KEYWORDS)

def get_matches(question: str, top_k: int, db_choice: str, user_id: str):
    """
    Route retrieval to Qdrant or MongoDB based on db_choice.
    Both return the same list-of-dicts shape.
    """
    if db_choice == "mongodb":
        query_embedding = generate_embedding(question)
        return retrieve_similar_chunks_from_mongodb(query_embedding, user_id, top_k)
    else:
        return retrieve_similar_chunks(question=question, top_k=top_k, user_id=user_id)

# ─────────────────────────────────────────────────────────
# Non-streaming query endpoint
# ─────────────────────────────────────────────────────────

@router.post("/", response_model=QueryReply)
async def query_document(payload: QueryRequest, current_user: dict = Depends(get_current_user)):
    question = payload.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    user_id = str(current_user["_id"])

    try:
        matches = get_matches(question, payload.top_k, payload.db_choice, user_id)

        query_reply = QueryResponse(
            question=question,
            top_k=payload.top_k,
            matches=[RetrievedMatch(**match) for match in matches]
        )

        response = await generate_query_response(
            content=query_reply.model_dump(),
            chat_history=[msg.model_dump() for msg in payload.chat_history]
        )

        is_error = "⚠️" in response or "Error" in response

        # Only include sources for document questions and non-errors
        if is_general_question(question) or is_error:
            sources = ""  # No sources for "hi", "how are you", etc. or errors
        else:
            unique_files = list({m["filename"] for m in matches})
            sources = "\n".join(f"From document: {filename}" for filename in unique_files)

        return QueryReply(answer=response, sources=sources)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query pipeline failed: {str(e)}")


# ─────────────────────────────────────────────────────────
# Streaming query endpoint
# ─────────────────────────────────────────────────────────
@router.post("/stream")
async def query_document_stream(payload: QueryRequest, current_user: dict = Depends(get_current_user)):
    question = payload.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    user_id = str(current_user["_id"])

    try:
        matches = get_matches(question, payload.top_k, payload.db_choice, user_id)

        query_reply = QueryResponse(
            question=question,
            top_k=payload.top_k,
            matches=[RetrievedMatch(**match) for match in matches]
        )

        # Decide before streaming starts whether to show sources
        general = is_general_question(question)

        async def event_generator():
            full_response = ""
            # Stream the AI answer word by word
            async for chunk in stream_query_response(
                query_reply.model_dump(),
                [msg.model_dump() for msg in payload.chat_history[-6:]]
            ):
                # We do not want to stream the [GENERAL] tag
                clean_chunk = chunk.replace("[GENERAL]", "").lstrip() if "[GENERAL]" in chunk else chunk
                if not clean_chunk:
                    continue

                full_response += chunk
                words = clean_chunk.split(" ")
                for i, word in enumerate(words):
                    token = word if i == 0 else " " + word
                    yield token
                    await asyncio.sleep(0.03)

            is_error = "⚠️" in full_response or "Error" in full_response
            is_fallback = "I don't know based on the provided document" in full_response
            is_tagged_general = "[GENERAL]" in full_response
        
            # Only append sources if it's a document question and not an error
            if not general and not is_error and not is_fallback and not is_tagged_general:
                yield "\n\nSources:\n"
                seen = set()
                for m in matches:
                    if m["filename"] not in seen:
                        seen.add(m["filename"])
                        yield f"- {m['filename']}\n"
            # For general questions or errors: stream ends here with no sources
            
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Streaming query pipeline failed: {str(e)}"
        )