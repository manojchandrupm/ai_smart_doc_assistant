from fastapi import APIRouter, HTTPException
from models.schemas import QueryRequest, QueryResponse, RetrievedMatch,QueryReply
from services.retrieval_service import retrieve_similar_chunks
from services.user_query_response_service import generate_query_response,stream_query_response
from fastapi.responses import StreamingResponse
import asyncio

router = APIRouter(prefix="/query", tags=["Query"])

@router.post("/", response_model=QueryReply)
async def query_document(payload: QueryRequest):
    question = payload.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        matches = retrieve_similar_chunks(question=question, top_k=payload.top_k)


        query_reply = QueryResponse(
            question=question,
            top_k=payload.top_k,
            matches=[RetrievedMatch(**match) for match in matches]
        )

        response = await generate_query_response(
            content=query_reply.model_dump(),
            chat_history=[msg.model_dump() for msg in payload.chat_history]
        )

        unique_files = list({m["filename"] for m in matches})

        sources = "\n".join(
            f"From document: {filename}"
            for filename in unique_files
        )

        return QueryReply(
            answer=response,
            sources=sources
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query pipeline failed: {str(e)}")


@router.post("/stream")
async def query_document_stream(payload: QueryRequest):
    question = payload.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        matches = retrieve_similar_chunks(
            question=question,
            top_k=payload.top_k
        )

        query_reply = QueryResponse(
            question=question,
            top_k=payload.top_k,
            matches=[RetrievedMatch(**match) for match in matches]
        )

        async def event_generator():
            async for chunk in stream_query_response(
                query_reply.model_dump(),
                [msg.model_dump() for msg in payload.chat_history[-6:]]
            ):
                words = chunk.split(" ")
                for i, word in enumerate(words):
                    token = word if i == 0 else " " + word
                    yield token
                    await asyncio.sleep(0.03)

            yield "\n\nSources:\n"

            seen = set()
            for m in matches:
                source_key = (m["filename"])
                if source_key not in seen:
                    seen.add(source_key)
                    yield f"- {m['filename']}\n"

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