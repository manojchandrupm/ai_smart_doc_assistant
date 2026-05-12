import asyncio
import os
import sys
from config import env

NPX_CMD = "npx.cmd" if sys.platform == "win32" else "npx"

# pyrefly: ignore [missing-import]
from mcp import ClientSession, StdioServerParameters
# pyrefly: ignore [missing-import]
from mcp.client.stdio import stdio_client

async def async_fetch_url(url: str) -> str:
    """Connects to the external Fetch MCP server and grabs the webpage content."""
    
    print(f"--> Starting MCP Client to connect to fetch server for {url}...")
    
    # 1. Define the external server we want to connect to.
    # We are using 'npx' to automatically download and run the server-fetch tool.
    server_params = StdioServerParameters(
        command=NPX_CMD,
        args=["-y", "mcp-fetch-server"]
    )
    
    # 2. Connect to the external MCP server using standard input/output
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection handshake
            await session.initialize()
            
            try:
                # 3. Call the external "fetch" tool!
                print(f"--> Calling external 'fetch_markdown' tool...")
                result = await session.call_tool("fetch_markdown", {"url": url})
                
                # The result contains the markdown/text of the webpage
                text_content = result.content[0].text
                return text_content[:1000] # Returning first 1000 chars for brevity
                
            except Exception as e:
                return f"Error fetching {url}: {str(e)}"

async def async_tavily_search(query: str) -> str:
    """Connects to the external Tavily MCP server and searches the web."""
    print(f"--> Starting MCP Client to search Tavily for: {query}")
    
    tavily_key = env.TAVILY_API_KEY
    if not tavily_key:
        return "Error: TAVILY_API_KEY is missing from your .env file."

    server_params = StdioServerParameters(
        command=NPX_CMD,
        args=["-y", "@toolsdk.ai/tavily-mcp"],
        env={"TAVILY_API_KEY": tavily_key, **os.environ}
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            try:
                print(f"--> Calling external 'tavily-search' tool...")
                result = await session.call_tool("tavily-search", {"query": query})
                return result.content[0].text
            except Exception as e:
                return f"Error searching Tavily: {str(e)}"

def fetch_web_page(url: str) -> str:
    """
    Reads the text content of any website URL.
    Use this when the user asks you to read a link or summarize a webpage.
    """
    return asyncio.run(async_fetch_url(url))

# Quick test if you run this file directly
if __name__ == "__main__":
    print("Testing the MCP Client...")
    
    # Test 1: Web Fetching
    # website_text = fetch_web_page("https://example.com")
    # print("\n--- Result from Fetch Server ---")
    # print(website_text)
    
    # Test 2: Tavily Search
    search_result = asyncio.run(async_tavily_search("Who won the Super Bowl in 2024?"))
    print("\n--- Result from Tavily Search Server ---")
    print(search_result)
