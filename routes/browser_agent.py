from pydantic import BaseModel
from fastapi import WebSocket
from services.router_service import route_query
from services.browser_service import BrowserAgent
from google import genai
from google.genai import types
import asyncio
import os

# Create a single shared client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def _extract_text(response) -> str:
    """
    Safely extract plain text from a Gemini response.

    Gemini 2.5 Flash (thinking model) sometimes sets response.text = None
    even when the model has finished — the actual text is buried inside
    response.candidates[0].content.parts as a Part with a non-empty .text.
    This helper walks those parts directly so we never miss the final answer.
    """
    # Fast path: .text property works
    try:
        if response.text:
            return response.text
    except Exception:
        pass

    # Slow path: walk candidates → content → parts
    try:
        for candidate in (response.candidates or []):
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in (getattr(content, "parts", None) or []):
                text = getattr(part, "text", None)
                if text and text.strip():
                    return text.strip()
    except Exception:
        pass

    return ""

class QueryRequest(BaseModel):
    query: str

SYSTEM_PROMPT = """
You are a safe Browser Booking Agent.

Your job:
1. Understand the user's booking request.
2. If source, destination, date, passenger count, or required details are missing, ask the user directly.
3. If details are available, open the booking website.
4. Use get_page_text and get_interactive_elements before clicking or filling.
5. Fill only normal booking details like source, destination, date, name, age, gender, mobile, and email if provided by the user.
6. Never bypass CAPTCHA, OTP, login security, or payment authentication.
7. Never complete payment.
8. Stop when you reach the review/payment page (if applicable).
9. Return a summary of what you found or accomplished (e.g., ticket details, prices, or search results).
10. ONLY IF the user is booking something or buying a product, append this exact message: "Please click the Source URL below to complete your payment/booking." (Do not mention payment for general information searches like Wikipedia).
11. DO NOT manually print the raw current page URL in your text response, as the chat interface will automatically attach it to the bottom of your message.

Important:
- Do not guess selectors blindly.
- First inspect the page using get_interactive_elements.
- Use click_element, fill_input, and press_key step by step.
- If CAPTCHA, OTP, login, or payment appears, stop and ask the user to complete it manually.
- If a tool returns an error for the same website, do not repeat the same action more than once. Try an alternative URL or explain the issue to the user.
"""
 

async def run_browser_agent(message: str, websocket: WebSocket, save_fn, chat_history: list = None) -> str:
    browser_agent = BrowserAgent()
    await browser_agent.start()

    try:
        tool_declarations = types.Tool(function_declarations=[
            types.FunctionDeclaration(name="navigate",      description="Navigates browser to a URL",        parameters=types.Schema(type="OBJECT", properties={"url": types.Schema(type="STRING")}, required=["url"])),
            types.FunctionDeclaration(name="get_page_text", description="Reads the current page text",       parameters=types.Schema(type="OBJECT", properties={})),
            types.FunctionDeclaration(name="click_element", description="Clicks a CSS selector element",     parameters=types.Schema(type="OBJECT", properties={"selector": types.Schema(type="STRING")}, required=["selector"])),
            types.FunctionDeclaration(name="fill_input",    description="Fills an input field",              parameters=types.Schema(type="OBJECT", properties={"selector": types.Schema(type="STRING"), "value": types.Schema(type="STRING")}, required=["selector", "value"])),
            types.FunctionDeclaration(name="press_key",     description="Presses a keyboard key",            parameters=types.Schema(type="OBJECT", properties={"key": types.Schema(type="STRING")}, required=["key"])),
            types.FunctionDeclaration(name="get_interactive_elements",description="Returns visible clickable and fillable elements with suggested selectors",parameters=types.Schema(type="OBJECT", properties={})),
            types.FunctionDeclaration(name="get_current_url",description="Returns the current browser page URL",parameters=types.Schema(type="OBJECT", properties={})),
        ])

        config = types.GenerateContentConfig(
            tools=[tool_declarations],
            system_instruction=SYSTEM_PROMPT
        )

        contents = []
        if chat_history:
            for msg in chat_history:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )
        print(f"[BrowserAgent] Initial response — function_calls: {bool(response.function_calls)}, text: {bool(response.text)}")

        full_answer = ""
        source_link = ""

        for iteration in range(15):
            fn_calls = response.function_calls or []
            print(f"[BrowserAgent] Loop iteration {iteration+1} — function_calls: {fn_calls}")

            # ── No function calls → final text answer ──────────────
            if not fn_calls:
                full_answer = _extract_text(response)
                print(f"[BrowserAgent] Final answer: {full_answer[:100]}")
                break

            # ── Execute each tool call ──────────────────────────────
            for fn in fn_calls:
                print(f"[BrowserAgent] Executing: {fn.name}({fn.args})")
                if fn.name == "navigate":
                    source_link = fn.args.get("url")
                args = dict(fn.args) if fn.args else {}
                tool_result = "Unknown command"

                try:
                    if fn.name == "navigate":
                        tool_result = await browser_agent.navigate(args.get("url"))
                    elif fn.name == "get_page_text":
                        tool_result = await browser_agent.get_page_text()
                    elif fn.name == "click_element":
                        tool_result = await browser_agent.click_element(args.get("selector"))
                    elif fn.name == "fill_input":
                        tool_result = await browser_agent.fill_input(args.get("selector"), args.get("value"))
                    elif fn.name == "press_key":
                        tool_result = await browser_agent.press_key(args.get("key"))
                    elif fn.name == "get_interactive_elements":
                        tool_result = await browser_agent.get_interactive_elements()
                    elif fn.name == "get_current_url":
                        tool_result = await browser_agent.get_current_url()
                except Exception as tool_err:
                    tool_result = f"Tool error: {str(tool_err)}"
                    print(f"[BrowserAgent] Tool error in {fn.name}: {tool_err}")

                print(f"[BrowserAgent] Tool result ({fn.name}): {str(tool_result)[:120]}")

               
                # Append model function call + tool result to conversation history
                contents.append(types.Content(role="model", parts=[types.Part(function_call=fn)]))
                contents.append(types.Content(role="user", parts=[types.Part(
                    function_response=types.FunctionResponse(name=fn.name, response={"result": tool_result})
                )]))
 
            # ── Ask Gemini again with the tool results ──────────────
            # NOTE: This is OUTSIDE the inner for-fn loop on purpose.
            # We send all tool results from this round, THEN ask Gemini once.
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config
            )
            print(f"[BrowserAgent] Gemini reply — fn_calls: {bool(response.function_calls)}, text: {bool(_extract_text(response))}")

        # Fallback: loop exhausted all 15 iterations OR final text was empty
        if not full_answer:
            full_answer = _extract_text(response) or "Agent completed the task but produced no summary."

        # Fetch the true final URL after all clicks and navigations are done
        try:
            source_link = await browser_agent.get_current_url()
        except Exception:
            pass

        # Stream the full answer token by token for a typing effect
        chunk_size = 5
        for i in range(0, len(full_answer), chunk_size):
            piece = full_answer[i:i+chunk_size]
            await websocket.send_json({"type": "token", "content": piece})
            await asyncio.sleep(0.02)
 
        # Save clean final answer to DB
        current_url = await browser_agent.get_current_url()

        if current_url and current_url != "about:blank":
            sources = [{"filename": current_url}]
        elif source_link and source_link != "about:blank":
            sources = [{"filename": source_link}]
        else:
            sources = []

        save_fn(full_answer, sources)

        await websocket.send_json({"type": "end", "sources": sources, "full_answer": full_answer})
        return full_answer

    except Exception as e:
        error_msg = f"⚠️ Browser agent error: {str(e)}"
        print(f"[BrowserAgent] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({"type": "token", "content": error_msg})
        await websocket.send_json({"type": "end", "full_answer": error_msg, "sources": [{"filename": source_link}]})
        save_fn(error_msg, [{"filename": source_link}])
        return error_msg

    finally:
        await browser_agent.close()

