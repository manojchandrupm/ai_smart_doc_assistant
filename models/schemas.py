from pydantic import BaseModel
from typing import List

class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str

class UploadResponse(BaseModel):
    message: str
    filename: str
    total_chunks: int

class FileUploadResult(BaseModel):
    filename: str
    total_chunks: int

class FileUploadError(BaseModel):
    filename: str
    error: str

class MultiUploadResponse(BaseModel):
    message: str
    uploaded: List[FileUploadResult] = []
    errors: List[FileUploadError] = []

class ChatMessage(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    question: str
    top_k: int = 3
    chat_history: List[ChatMessage] = []

class RetrievedMatch(BaseModel):
    chunk_id: str
    filename: str
    page: int
    chunk_index: int
    score: float
    text: str

class QueryResponse(BaseModel):
    question: str
    top_k: int
    matches: List[RetrievedMatch]

class QueryReply(BaseModel):
    answer : str
    sources : str