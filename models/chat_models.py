from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    top_k: int = 5