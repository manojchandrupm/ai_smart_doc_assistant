from fastapi import WebSocket
from services.browser_service import BrowserAgent
from google import genai
from google.genai import types
import asyncio
import os

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def _extract_text(response) -> str:
    try:
        if response.text:
            return response.text
    except Exception:
        pass
    try:
        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", None)
                if text and text.strip():
                    return text.strip()
    except Exception:
        pass
    return ""


SYSTEM_PROMPT = """
You are an E-commerce Research Agent. Your job is to visit real shopping websites, extract actual product listings, compare them, and recommend the best option.

════════════════════════════════════════════════════
CRITICAL STRATEGY
════════════════════════════════════════════════════

1. USE PRE-BUILT SEARCH URLs — never fill search forms. Navigate directly to search result URLs.
2. WAIT after every navigate before reading the page.
3. READ PAGE TEXT TWICE — once after loading, once after scrolling down.
4. EXTRACT real product names, prices, ratings from page text.
5. If one site fails (CAPTCHA / blank / error) → try next site immediately.
6. NEVER give up without trying at least 3 sites.

════════════════════════════════════════════════════
PRE-BUILT URL TEMPLATES
════════════════════════════════════════════════════

Replace {QUERY} with the URL-encoded product search term (spaces become +).

1. AMAZON (try first):
   https://www.amazon.in/s?k={QUERY}&sort=price-asc-rank

2. FLIPKART:
   https://www.flipkart.com/search?q={QUERY}&sort=price_asc

3. CROMA:
   https://www.croma.com/search/?q={QUERY}&searchRedirect=true

4. RELIANCE DIGITAL:
   https://www.reliancedigital.in/search?q={QUERY}

5. MEESHO:
   https://www.meesho.com/search?q={QUERY}

Examples for "wireless earbuds under 2000":
  Amazon  : https://www.amazon.in/s?k=wireless+earbuds+under+2000&sort=price-asc-rank
  Flipkart: https://www.flipkart.com/search?q=wireless+earbuds+under+2000&sort=price_asc
  Croma   : https://www.croma.com/search/?q=wireless+earbuds&searchRedirect=true

════════════════════════════════════════════════════
PHASE 1 — VALIDATE INPUT
════════════════════════════════════════════════════
Ask ONLY if the product type is completely unclear.
Budget and brand preference are optional — proceed without them if not given.

════════════════════════════════════════════════════
PHASE 2 — VISIT & EXTRACT (try all sites)
════════════════════════════════════════════════════
For each site:
  a. navigate(url)          — use pre-built search URL
  b. wait(ms=3000)          — let page render
  c. get_page_text()        — first read
  d. scroll_down(1000)      — load lazy content
  e. wait(ms=2000)
  f. get_page_text()        — second read with more results
  g. Extract ALL products visible: name, price, rating, specs
  h. If CAPTCHA / error / empty → note it, move to next site

Collect products from at least 2 sites before moving to Phase 3.
More sites = better comparison.

════════════════════════════════════════════════════
PHASE 3 — EXTRACT PER PRODUCT
════════════════════════════════════════════════════
For EVERY product found, record:
  • Product name (full model name)
  • Price (₹)
  • Rating (out of 5, and number of reviews if shown)
  • Key specs (storage, RAM, battery, display, camera — whatever is visible)
  • Availability (In Stock / Out of Stock)
  • Source site

════════════════════════════════════════════════════
PHASE 4 — COMPARE & PRESENT
════════════════════════════════════════════════════
Present EXACTLY in this format:

---
🛒 PRODUCT SEARCH: [What user asked for]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 PRODUCTS FOUND:

1. [Full Product Name]
   💰 Price  : ₹[Amount]
   ⭐ Rating : [X.X]/5 ([N] reviews)
   📋 Specs  : [Key specs comma separated]
   🏪 Source : [Site name]
   ✅ [One line strongest selling point]
   ❌ [One line biggest drawback]

2. [Full Product Name]
   💰 Price  : ₹[Amount]
   ⭐ Rating : [X.X]/5 ([N] reviews)
   📋 Specs  : [Key specs]
   🏪 Source : [Site name]
   ✅ [Strength]
   ❌ [Weakness]

[... all products found ...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 COMPARISON SUMMARY:

| # | Product        | Price  | Rating | Best For         |
|---|----------------|--------|--------|------------------|
| 1 | [Short name]   | ₹[Amt] | [X.X]  | [Use case]       |
| 2 | [Short name]   | ₹[Amt] | [X.X]  | [Use case]       |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 BEST PICK: [Product Name]  ₹[Price]
   Why: [2-3 sentences — best value, highest rating, best specs for price]
   🔗 Buy here: [URL]

💡 ALSO CONSIDER: [Runner-up name] if [specific reason e.g. you need more storage / lower budget]
---

════════════════════════════════════════════════════
NON-NEGOTIABLE RULES
════════════════════════════════════════════════════
• NEVER fabricate product names, prices, or ratings. Only report what you read.
• NEVER fill search forms — use pre-built URLs only.
• NEVER attempt login, add to cart (unless user asks), CAPTCHA, or payment.
• NEVER stop after 1 site failure — try all 5.
• ALWAYS show pros AND cons for each product.
• ALWAYS give a clear single best recommendation at the end.
• If ALL sites fail, list each site tried + exact error seen.
"""


TOOL_DECLARATIONS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="navigate",
        description="Open a URL. Use pre-built search URLs with product query already in the URL. Never navigate to a homepage and fill forms.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"url": types.Schema(type="STRING")},
            required=["url"]
        )
    ),
    types.FunctionDeclaration(
        name="get_page_text",
        description="Read all visible text on the current page. Call TWICE per site — once after loading, once after scrolling. Look for product names, ₹ prices, and star ratings.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="get_interactive_elements",
        description="Get clickable and fillable elements on the page.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="click_element",
        description="Click a page element by CSS selector.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"selector": types.Schema(type="STRING")},
            required=["selector"]
        )
    ),
    types.FunctionDeclaration(
        name="fill_input",
        description="Type into an input field by CSS selector.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "selector": types.Schema(type="STRING"),
                "value": types.Schema(type="STRING")
            },
            required=["selector", "value"]
        )
    ),
    types.FunctionDeclaration(
        name="press_key",
        description="Press a keyboard key (Enter, Tab, Escape, etc.)",
        parameters=types.Schema(
            type="OBJECT",
            properties={"key": types.Schema(type="STRING")},
            required=["key"]
        )
    ),
    types.FunctionDeclaration(
        name="get_current_url",
        description="Get the current browser URL.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="wait",
        description="Wait for page to render. Use ms=3000 after navigate, ms=2000 after scroll.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"ms": types.Schema(type="INTEGER")},
            required=["ms"]
        )
    ),
    types.FunctionDeclaration(
        name="scroll_down",
        description="Scroll down to reveal more product listings. Use pixels=1000.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"pixels": types.Schema(type="INTEGER")},
            required=["pixels"]
        )
    ),
])


async def _execute_tool(fn, browser_agent) -> str:
    args = dict(fn.args) if fn.args else {}
    name = fn.name
    try:
        if name == "navigate":
            return await browser_agent.navigate(args.get("url", ""))
        elif name == "get_page_text":
            text = await browser_agent.get_page_text()
            if isinstance(text, str) and len(text) > 9000:
                return text[:6000] + "\n...[truncated]...\n" + text[-2000:]
            return text
        elif name == "get_interactive_elements":
            elems = await browser_agent.get_interactive_elements()
            if isinstance(elems, str) and len(elems) > 4000:
                return elems[:4000] + "\n...[truncated]..."
            return elems
        elif name == "click_element":
            return await browser_agent.click_element(args.get("selector", ""))
        elif name == "fill_input":
            return await browser_agent.fill_input(args.get("selector", ""), args.get("value", ""))
        elif name == "press_key":
            return await browser_agent.press_key(args.get("key", ""))
        elif name == "get_current_url":
            return await browser_agent.get_current_url()
        elif name == "wait":
            ms = min(int(args.get("ms", 2000)), 5000)
            await asyncio.sleep(ms / 1000)
            return f"Waited {ms}ms."
        elif name == "scroll_down":
            pixels = int(args.get("pixels", 1000))
            try:
                await browser_agent.page.evaluate(f"window.scrollBy(0, {pixels})")
                await asyncio.sleep(1.5)
                return f"Scrolled down {pixels}px."
            except Exception as e:
                return f"Scroll failed: {e}"
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error ({name}): {str(e)}"


async def run_ecommerce_research_agent(
    message: str,
    websocket: WebSocket,
    save_fn,
    chat_history: list = None
) -> str:
    browser_agent = BrowserAgent()
    await browser_agent.start()
    source_link = ""

    try:
        config = types.GenerateContentConfig(
            tools=[TOOL_DECLARATIONS],
            system_instruction=SYSTEM_PROMPT,
        )

        contents = []
        if chat_history:
            for msg in chat_history[-6:]:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

        full_answer = ""
        MAX_ITERATIONS = 35

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )
        print(f"[EcommerceAgent] Start — fn_calls={bool(response.function_calls)}, text={bool(_extract_text(response))}")

        for iteration in range(MAX_ITERATIONS):
            fn_calls = response.function_calls or []
            print(f"[EcommerceAgent] Iter {iteration + 1} — {len(fn_calls)} tool call(s)")

            if not fn_calls:
                full_answer = _extract_text(response)
                print(f"[EcommerceAgent] Done. Preview: {full_answer[:200]}")
                break

            for fn in fn_calls:
                print(f"  → {fn.name}({dict(fn.args) if fn.args else {}})")
                tool_result = await _execute_tool(fn, browser_agent)
                print(f"  ← {str(tool_result)[:200]}")

                if fn.name == "navigate":
                    url_arg = (fn.args or {}).get("url", "")
                    if url_arg and url_arg.startswith("http"):
                        source_link = url_arg
                elif fn.name == "get_current_url" and isinstance(tool_result, str) and tool_result.startswith("http"):
                    source_link = tool_result

                contents.append(types.Content(role="model", parts=[types.Part(function_call=fn)]))
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(
                        function_response=types.FunctionResponse(
                            name=fn.name,
                            response={"result": str(tool_result)}
                        )
                    )]
                ))

            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config
            )
            print(f"[EcommerceAgent] Next — fn_calls={bool(response.function_calls)}, text={bool(_extract_text(response))}")

        if not full_answer:
            full_answer = (
                "⚠️ Could not retrieve product data after trying multiple websites.\n"
                "Please search directly on:\n"
                "• https://www.amazon.in\n"
                "• https://www.flipkart.com\n"
                "• https://www.croma.com"
            )

        try:
            current = await browser_agent.get_current_url()
            if current and current.startswith("http"):
                source_link = current
        except Exception:
            pass

        CHUNK = 6
        for i in range(0, len(full_answer), CHUNK):
            await websocket.send_json({"type": "token", "content": full_answer[i:i + CHUNK]})
            await asyncio.sleep(0.018)

        sources = [{"filename": source_link}] if source_link else []
        save_fn(full_answer, sources)
        await websocket.send_json({"type": "end", "sources": sources, "full_answer": full_answer})
        return full_answer

    except Exception as e:
        error_msg = f"⚠️ E-commerce Research Agent error: {str(e)}"
        print(f"[EcommerceAgent] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({"type": "token", "content": error_msg})
        await websocket.send_json({"type": "end", "full_answer": error_msg, "sources": []})
        save_fn(error_msg, [])
        return error_msg

    finally:
        await browser_agent.close()