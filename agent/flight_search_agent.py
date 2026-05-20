from fastapi import WebSocket
from services.browser_service import BrowserAgent
from google import genai
from google.genai import types
import asyncio
import os
from datetime import datetime, timedelta

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


def _build_system_prompt() -> str:
    """Build system prompt with real injected dates at call time."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    today_display = now.strftime("%d %B %Y (%A)")
    tomorrow_display = (now + timedelta(days=1)).strftime("%d %B %Y (%A)")

    # Pre-format date variants for easy URL substitution
    def fmt(date_str, style):
        d = datetime.strptime(date_str, "%Y-%m-%d")
        if style == "YYYYMMDD":    return d.strftime("%Y%m%d")
        if style == "DD-MM-YYYY":  return d.strftime("%d-%m-%Y")
        if style == "DD/MM/YYYY":  return d.strftime("%d/%m/%Y")
        return date_str  # YYYY-MM-DD

    return f"""
You are a Flight Search Agent. Find REAL flight prices by scraping live travel websites.

════════════════════════════════════════════════════
🗓️  REAL DATE CONTEXT — USE THESE EXACT DATES
════════════════════════════════════════════════════
TODAY    : {today_display}  →  {today}
TOMORROW : {tomorrow_display}  →  {tomorrow}

When the user says "tomorrow", use: {tomorrow}
When the user says "today",    use: {today}
For any other date, parse it correctly from what the user says.
NEVER use dates from your training data. ALWAYS use the dates above.

════════════════════════════════════════════════════
CRITICAL STRATEGY
════════════════════════════════════════════════════

1. USE PRE-BUILT SEARCH URLs — never fill forms. Navigate directly to URLs with route+date embedded.
2. WAIT 4 SECONDS after every navigate before reading.
3. SCROLL DOWN then read again — results load lazily.
4. ALWAYS call get_page_text() at least TWICE per site (before and after scrolling).
5. Look for ₹ or INR followed by numbers — that's your price data.
6. If a site fails → try next immediately. Try ALL 5 before giving up.
7. Report ANY price you find — partial data beats zero data.

════════════════════════════════════════════════════
IATA CODES
════════════════════════════════════════════════════
Chennai=MAA  Bangalore=BLR  Mumbai=BOM  Delhi=DEL
Hyderabad=HYD  Kolkata=CCU  Pune=PNQ  Goa=GOI
Kochi=COK  Ahmedabad=AMD  Jaipur=JAI  Lucknow=LKO

════════════════════════════════════════════════════
URL TEMPLATES  (substitute FROM, TO, and dates)
════════════════════════════════════════════════════

For tomorrow's date the pre-formatted values are:
  YYYY-MM-DD  : {tomorrow}
  YYYYMMDD    : {fmt(tomorrow, "YYYYMMDD")}
  DD-MM-YYYY  : {fmt(tomorrow, "DD-MM-YYYY")}
  DD/MM/YYYY  : {fmt(tomorrow, "DD/MM/YYYY")}

1. IXIGO  (try first)
   https://www.ixigo.com/search/result/flight/{{FROM}}/{{TO}}/{{YYYYMMDD}}/null/1/0/0/E/O/cheapest?currency=INR

2. CLEARTRIP
   https://www.cleartrip.com/flights/results?from={{FROM}}&to={{TO}}&depart_date={{DD-MM-YYYY}}&adults=1&childs=0&infants=0&class=Economy&intl=n

3. EASEMYTRIP
   https://www.easemytrip.com/flights/search?org={{FROM}}&des={{TO}}&dd={{DD/MM/YYYY}}&ad=1&ch=0&inf=0&cls=Economy&trip=O

4. PAYTM FLIGHTS
   https://flights.paytm.com/search?src={{FROM}}&dst={{TO}}&depart={{YYYY-MM-DD}}&class=E&adults=1&children=0&infants=0&type=O

5. YATRA
   https://www.yatra.com/air/search?from_code={{FROM}}&to_code={{TO}}&depart_date={{YYYY-MM-DD}}&adults=1&children=0&infants=0&journey_type=O

════════════════════════════════════════════════════
PHASE 1 — VALIDATE INPUT
════════════════════════════════════════════════════
Only ask if source city, destination, or passengers are missing.
For date: "tomorrow" = {tomorrow}. Do NOT ask again for date if user said "tomorrow".

════════════════════════════════════════════════════
PHASE 2 — SEARCH LOOP
════════════════════════════════════════════════════
For each site (try all 5):
  a. navigate(url)          ← use exact pre-built URL with real dates substituted
  b. wait(ms=4000)          ← MANDATORY — let JS render
  c. get_page_text()        ← first read
  d. scroll_down(1200)      ← load lazy content
  e. wait(ms=2000)
  f. get_page_text()        ← second read — look for ₹ prices here
  g. If prices found → record them, mark site as SUCCESS, continue to collect more
  h. If no prices / CAPTCHA / error → note failure, move to next site

DO NOT stop at first success — try at least 2 sites to get more options for comparison.

════════════════════════════════════════════════════
PHASE 3 — EXTRACT
════════════════════════════════════════════════════
For every flight price you saw in page text, extract:
  • Airline name (IndiGo, Air India, SpiceJet, Akasa, Vistara, etc.)
  • Departure time → Arrival time
  • Duration and stops
  • Price (₹)

If details are incomplete, still record airline + price. That's enough to compare.

════════════════════════════════════════════════════
PHASE 4 — COMPARE & PRESENT
════════════════════════════════════════════════════
Sort all found options by price (lowest first).
Present EXACTLY in this format:

---
✈️  [Source City] → [Destination City]
📅  [Full date e.g. Wednesday, 20 May 2026] | 1 Adult | Economy

OPTIONS FOUND (cheapest first):

1. [Airline]  ₹[Price]
   [Depart time] → [Arrive time]  |  [Duration]  |  [Stops]

2. [Airline]  ₹[Price]
   [Depart time] → [Arrive time]  |  [Duration]  |  [Stops]

[... all options ...]

🏆 BEST PICK:  [Airline]  ₹[Price]
   [One sentence reason]
   🔗 Book at: [site URL]

⚠️  Complete payment manually on the website.
---

════════════════════════════════════════════════════
NON-NEGOTIABLE RULES
════════════════════════════════════════════════════
• NEVER use dates from training data. TODAY={today}, TOMORROW={tomorrow}.
• NEVER say "I cannot find flights" without trying all 5 URL templates.
• NEVER fabricate prices. Only report numbers read from page text.
• NEVER fill forms — pre-built URLs only.
• NEVER attempt login, CAPTCHA, or payment.
• ALWAYS report partial data — even 1 airline+price is a valid result.
• If ALL 5 sites fail, list each site + exact error message received.
"""


TOOL_DECLARATIONS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="navigate",
        description="Open a URL in the browser. Use pre-built search URLs with route and date already embedded in the URL.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"url": types.Schema(type="STRING")},
            required=["url"]
        )
    ),
    types.FunctionDeclaration(
        name="get_page_text",
        description="Read all visible text on the current page. Call TWICE per site: once right after wait, once after scrolling. Look for ₹ prices and airline names in the output.",
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
        description="Type into an input field.",
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
        description="Press a keyboard key.",
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
        description="Wait for the page to render. Use ms=4000 after navigate, ms=2000 after scroll.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"ms": types.Schema(type="INTEGER")},
            required=["ms"]
        )
    ),
    types.FunctionDeclaration(
        name="scroll_down",
        description="Scroll down to reveal lazy-loaded flight results. Use pixels=1200.",
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
                return text[:6000] + "\n...[truncated middle]...\n" + text[-2000:]
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
            ms = min(int(args.get("ms", 2000)), 6000)
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


async def run_flight_search_agent(
    message: str,
    websocket: WebSocket,
    save_fn,
    chat_history: list = None
) -> str:
    browser_agent = BrowserAgent()
    await browser_agent.start()
    source_link = ""

    try:
        # Build prompt with real current date injected
        system_prompt = _build_system_prompt()

        config = types.GenerateContentConfig(
            tools=[TOOL_DECLARATIONS],
            system_instruction=system_prompt,
        )

        contents = []
        if chat_history:
            for msg in chat_history[-6:]:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

        full_answer = ""
        MAX_ITERATIONS = 40

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )
        print(f"[FlightAgent] Start — fn_calls={bool(response.function_calls)}, text={bool(_extract_text(response))}")

        for iteration in range(MAX_ITERATIONS):
            fn_calls = response.function_calls or []
            print(f"[FlightAgent] Iter {iteration + 1} — {len(fn_calls)} tool call(s)")

            if not fn_calls:
                full_answer = _extract_text(response)
                print(f"[FlightAgent] Done. Preview: {full_answer[:200]}")
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
            print(f"[FlightAgent] Next — fn_calls={bool(response.function_calls)}, text={bool(_extract_text(response))}")

        if not full_answer:
            full_answer = (
                "⚠️ Could not retrieve live flight data after trying multiple websites.\n"
                "Please search directly:\n"
                "• https://www.ixigo.com/flights\n"
                "• https://www.cleartrip.com/flights\n"
                "• https://www.google.com/travel/flights"
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
        error_msg = f"⚠️ Flight Search Agent error: {str(e)}"
        print(f"[FlightAgent] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({"type": "token", "content": error_msg})
        await websocket.send_json({"type": "end", "full_answer": error_msg, "sources": []})
        save_fn(error_msg, [])
        return error_msg

    finally:
        await browser_agent.close()
