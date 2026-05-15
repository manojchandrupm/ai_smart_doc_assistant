from google import genai
import os
import logging

logger = logging.getLogger(__name__)

# Create a client using the new google.genai SDK
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def rule_based_route(user_query: str) -> str | None:
    query = user_query.lower()

    browser_keywords = [
        "book", "fill form", "login", "sign in", "compare price",
        "add to cart", "buy", "checkout", "open website",
        "navigate", "click", "submit"
    ]

    web_keywords = [
        "latest", "current", "today", "yesterday", "news",
        "live", "real-time", "weather", "stock price",
        "search web", "internet", "recent", "now",
        "who is the current", "2025", "2026"
    ]

    document_keywords = [
        "document", "pdf", "uploaded file", "according to the document",
        "from this file", "from the pdf", "summarize this document",
        "based on the document", "page", "chunk"
    ]

    if any(word in query for word in browser_keywords):
        return "browser_agent"

    if any(word in query for word in web_keywords):
        return "web_search_agent"

    if any(word in query for word in document_keywords):
        return "rag_agent"

    return None

# async def route_query(user_query: str) -> str:
#     """
#     Returns the routing decision: 'browser_agent', 'rag_agent', 'web_search_agent'.
#     Falls back to 'rag_agent' on any Gemini API error (e.g. empty response,
#     quota exceeded, or model unavailable).
#     """
#     prompt = f"""
#     You are an intelligent router. Analyze the user query and decide which agent should handle it.
    
#     Agents available:
#     - browser_agent: For booking tickets, filling forms, interacting with UI, comparing products on live sites, logging into websites, extracting UI data.
#     - web_search_agent: ONLY use this if the user EXPLICITLY asks to "search the web", "look up on the internet", or asks about real-time live events/news.
#     - rag_agent: DEFAULT choice. Use for all questions about documents, uploaded PDFs, general questions, and anything that isn't explicitly a web search or browser automation task.

#     Query: "{user_query}"

#     Respond with ONLY ONE of the agent names above. Do not include any other text.
#     """
    
#     try:
#         response = await client.aio.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=prompt
#         )
#         decision = (response.text or "").strip().lower()

#         if decision in ["browser_agent", "rag_agent", "web_search_agent"]:
#             return decision

#         # Gemini returned something unexpected — fallback
#         logger.warning(f"[Router] Unexpected decision '{decision}', falling back to rag_agent")
#         return "rag_agent"

#     except Exception as e:
#         # Catches: empty response, quota errors, model unavailable, etc.
#         logger.warning(f"[Router] Gemini routing failed ({e}), falling back to rag_agent")
#         return "rag_agent"

async def route_query(user_query: str) -> str:
    """
    Returns: browser_agent, rag_agent, or web_search_agent
    """

    # 1. First use rule-based routing
    rule_decision = rule_based_route(user_query)
    if rule_decision:
        logger.info(f"[Router] Rule-based decision: {rule_decision}")
        return rule_decision

    # 2. Then use Gemini only for unclear cases
    prompt = f"""
You are an AI router. Choose the best agent for the user query.

Available agents:

1. rag_agent
Use when the query is about:
- uploaded documents
- PDFs
- document summary
- asking content from stored files
- previous document-based knowledge

2. web_search_agent
Use when the query needs:
- latest information
- current events
- real-time data
- news
- current prices
- weather
- live information
- information not available in uploaded documents

3. browser_agent
Use when the user wants actions on websites:
- booking tickets
- filling forms
- logging into websites
- clicking buttons
- comparing products on websites
- interacting with UI

Important:
- Do NOT always choose rag_agent.
- If the query needs current/latest/live data, choose web_search_agent.
- If the query requires website interaction, choose browser_agent.
- If the query is clearly about uploaded documents, choose rag_agent.

User query:
"{user_query}"

Respond with only one word:
rag_agent
web_search_agent
browser_agent
"""

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        ) 

        decision = (response.text or "").strip().lower()

        if decision in ["browser_agent", "rag_agent", "web_search_agent"]:
            logger.info(f"[Router] Gemini decision: {decision}")
            return decision

        logger.warning(f"[Router] Unexpected decision '{decision}', fallback to rag_agent")
        return "rag_agent"

    except Exception as e:
        logger.warning(f"[Router] Gemini routing failed: {e}")
        return "rag_agent"