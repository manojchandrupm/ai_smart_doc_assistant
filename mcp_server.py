# pyrefly: ignore [missing-import]
from mcp.server.fastmcp import FastMCP

from routes.query_router import get_matches
from services.document_service import list_user_documents
from services.chat_service import list_session_messages

# 1. Initialize the FastMCP server
mcp = FastMCP("SmartDocAssistant")

# 2. Define a tool using the @mcp.tool() decorator
# Everything in the docstring and type hints becomes instructions for the AI client!
@mcp.tool()
def search_documents(question: str, user_id: str, db_choice: str = "qdrant", top_k: int = 3) -> str:
    """
    Search a user's uploaded documents for information matching the question.
    
    Args:
        question: The question or keyword to search for.
        user_id: The unique ID of the user (from MongoDB).
        db_choice: The database to search in. Use "qdrant" or "mongodb".
        top_k: Number of document chunks to retrieve (default 3).
    """
    try:
        # Call your existing codebase!
        matches = get_matches(question, top_k, db_choice, user_id)
        
        if not matches:
            return f"No documents found for user '{user_id}' matching the question."
            
        # Format the retrieved chunks into a readable string for the AI client
        result = f"Found {len(matches)} matching document chunks:\n\n"
        
        for i, match in enumerate(matches):
            filename = match.get("filename", "Unknown file")
            text = match.get("text", "No text content")
            result += f"--- Match {i+1} (From {filename}) ---\n{text}\n\n"
            
        return result
        
    except Exception as e:
        return f"Error searching documents: {str(e)}"

@mcp.tool()
def get_user_uploaded_files(user_id: str) -> str:
    """
    Get a list of all documents/files that the user has uploaded to the system.
    
    Args:
        user_id: The unique ID of the user.
    """
    try:
        # Call your existing service
        docs = list_user_documents(user_id)
        
        if not docs:
            return f"User '{user_id}' has not uploaded any documents."
            
        result = f"User '{user_id}' has uploaded {len(docs)} documents:\n"
        for doc in docs:
            filename = doc.get("filename", "Unknown")
            backend = doc.get("vector_backend", "qdrant")
            result += f"- {filename} (Stored in {backend})\n"
            
        return result
    except Exception as e:
        return f"Error fetching documents: {str(e)}"


@mcp.tool()
def get_chat_summary(session_id: str, user_id: str) -> str:
    """
    Fetch the chat history for a specific session to provide conversation context.
    
    Args:
        session_id: The unique ID of the chat session.
        user_id: The unique ID of the user who owns the chat.
    """
    try:
        # Fetch messages using your existing service
        messages = list_session_messages(user_id, session_id)
        
        if not messages:
            return f"No chat history found for session '{session_id}'."
            
        # Format the chat history into a readable script format
        result = f"Chat History for Session {session_id}:\n\n"
        
        for msg in messages:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("message", "")
            result += f"{role}: {content}\n\n"
            
        return result.strip()
    except Exception as e:
        return f"Error fetching chat summary: {str(e)}"

# 3. Run the server using Stdio transport (standard input/output)
if __name__ == "__main__":
    # This makes the server listen for MCP clients via standard input/output
    mcp.run()
