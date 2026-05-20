from fastapi import WebSocket
from services.browser_service import BrowserAgent
from google import genai
from google.genai import types
import asyncio
import os
from datetime import datetime, timedelta
from urllib.parse import quote_plus

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


def _parse_date(date_str: str) -> datetime:
    """Parse date from common formats the user might provide."""
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%B %d %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.now() + timedelta(days=1)  # fallback to tomorrow


def _build_system_prompt(checkin_dt: datetime, checkout_dt: datetime, adults: int, city: str) -> str:
    """Build prompt with ALL search URLs fully pre-computed — model just copies them."""
    now = datetime.now()
    today = now.strftime("%d %B %Y (%A)")

    ci_ymd  = checkin_dt.strftime("%Y-%m-%d")
    co_ymd  = checkout_dt.strftime("%Y-%m-%d")
    ci_dmy  = checkin_dt.strftime("%d-%m-%Y")
    co_dmy  = checkout_dt.strftime("%d-%m-%Y")
    ci_8    = checkin_dt.strftime("%Y%m%d")
    co_8    = checkout_dt.strftime("%Y%m%d")
    nights  = (checkout_dt - checkin_dt).days
    ci_disp = checkin_dt.strftime("%d %B %Y (%A)")
    co_disp = checkout_dt.strftime("%d %B %Y (%A)")

    city_q  = quote_plus(city)          # "Ooty" → "Ooty"
    city_lo = city.lower().replace(" ", "-")  # "Ooty" → "ooty"

    # Fully built URLs — model does NOT modify these
    url_booking   = f"https://www.booking.com/searchresults.html?ss={city_q}&checkin={ci_ymd}&checkout={co_ymd}&group_adults={adults}&no_rooms=1&order=price&nflt=mealplan%3D1%3Bparkingincluded%3D1"
    url_agoda     = f"https://www.agoda.com/search?city={city_q}&checkIn={ci_ymd}&checkOut={co_ymd}&rooms=1&adults={adults}&sort=priceLowToHigh"
    url_mmt       = f"https://www.makemytrip.com/hotels/hotel-listing/?checkin={ci_8}&checkout={co_8}&city={city_q}&roomStayQualifier={adults}e0e&country=IN&searchText={city_q}"
    url_goibibo   = f"https://www.goibibo.com/hotels/hotels-in-{city_lo}-ct/?ci={ci_8}&co={co_8}&r=1&a={adults}&c=0"
    url_cleartrip = f"https://www.cleartrip.com/hotels/results/?adults={adults}&children=0&checkin={ci_dmy}&checkout={co_dmy}&city={city_q}&country=IN"

    return f"""
You are a Hotel Comparison Agent. Find real hotels by visiting booking websites and reading page text.

════════════════════════════════════════════════════
TODAY: {today}
SEARCH PARAMETERS (FIXED — DO NOT CHANGE):
  City      : {city}
  Check-in  : {ci_disp}  ({ci_ymd})
  Check-out : {co_disp}  ({co_ymd})
  Nights    : {nights}
  Adults    : {adults}
════════════════════════════════════════════════════

════════════════════════════════════════════════════
⚠️  ABSOLUTE RULE — READ BEFORE ANYTHING ELSE
════════════════════════════════════════════════════
YOU MUST ONLY USE THE EXACT URLs LISTED BELOW.
DO NOT navigate to any homepage.
DO NOT fill any form, date picker, search box, or input field.
DO NOT click any search button.
JUST navigate() to the ready-made URL, wait, and read.

If a URL shows a CAPTCHA, homepage, or error → mark it FAILED and try the NEXT URL.
DO NOT attempt to interact with the page at all if it is not a results page.

════════════════════════════════════════════════════
READY-MADE SEARCH URLs — COPY EXACTLY AS SHOWN
════════════════════════════════════════════════════

URL 1 — BOOKING.COM (filtered for breakfast + parking):
{url_booking}

URL 2 — AGODA:
{url_agoda}

URL 3 — MAKEMYTRIP:
{url_mmt}

URL 4 — GOIBIBO:
{url_goibibo}

URL 5 — CLEARTRIP:
{url_cleartrip}

════════════════════════════════════════════════════
EXECUTION STEPS (repeat for each URL)
════════════════════════════════════════════════════
Step 1: navigate(url)           ← use exact URL above, nothing else
Step 2: wait(ms=4000)           ← mandatory, page needs time to render
Step 3: get_page_text()         ← first read — check if it's a results page
        → If you see hotel names and prices → GOOD, continue
        → If you see homepage / CAPTCHA / error → SKIP to next URL
Step 4: scroll_down(pixels=1200)
Step 5: wait(ms=2000)
Step 6: get_page_text()         ← second read — collect all hotel data

Repeat for all 5 URLs. Collect hotels from as many sites as possible.
STOP trying more URLs only after you have 5+ hotels OR all 5 URLs are exhausted.

════════════════════════════════════════════════════
EXTRACT PER HOTEL
════════════════════════════════════════════════════
For every hotel visible in the page text, record:
  • Hotel name
  • Price per night (₹)
  • Rating (out of 5 or 10)
  • Amenities visible (breakfast, parking, pool, WiFi, AC, etc.)
  • Location / area
  • Source site

════════════════════════════════════════════════════
FILTER
════════════════════════════════════════════════════
User wants: parking + breakfast + family-friendly
Keep hotels that mention any of: breakfast, parking, family, kids, garden, resort.
Still show hotels missing 1 amenity but mark them clearly.

════════════════════════════════════════════════════
RANK
════════════════════════════════════════════════════
Sort hotels by:
  1. Amenity match (has both parking AND breakfast = top tier)
  2. Rating (highest first within tier)
  3. Price (lowest first at same rating)

════════════════════════════════════════════════════
PRESENT RESULTS — USE THIS EXACT FORMAT
════════════════════════════════════════════════════

---
🏨 HOTELS IN {city.upper()} — FAMILY FRIENDLY WITH PARKING & BREAKFAST
📅 {ci_disp} → {co_disp}  |  {nights} Night(s)  |  {adults} Adults
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏨 RANKED OPTIONS:

1. [Hotel Name]
   💰 Price    : ₹[Amount]/night  (₹[Total] for {nights} night(s))
   ⭐ Rating   : [X.X]/5 or [X.X]/10
   📍 Location : [Area]
   🛎️  Amenities: [Breakfast ✅/❌]  [Parking ✅/❌]  [Pool ✅/❌]  [WiFi ✅/❌]
   👨‍👩‍👧 Family   : [Yes/No — any family mention]
   ✅ Best for : [One line]
   ❌ Watch out: [One line drawback]
   🔗 Source   : [Site name]

[repeat for all hotels...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 COMPARISON TABLE:

| # | Hotel        | Price/Night | Rating | Breakfast | Parking |
|---|--------------|-------------|--------|-----------|---------|
| 1 | [Name]       | ₹[Amt]      | [X.X]  | ✅        | ✅      |
| 2 | [Name]       | ₹[Amt]      | [X.X]  | ✅        | ❌      |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 TOP PICK: [Hotel Name]  ₹[Price]/night
   Why: [2-3 sentences]
   🔗 Book: [URL]

💡 BUDGET PICK: [Hotel Name]  ₹[Price]/night
   Why: [One sentence]
---

════════════════════════════════════════════════════
RULES SUMMARY
════════════════════════════════════════════════════
• Only use the 5 URLs listed above. Never build your own URL.
• Never interact with any page element — only navigate + wait + read + scroll.
• Never fabricate hotel data. Only report what page text contains.
• Never attempt login, CAPTCHA, or payment.
• If ALL 5 URLs fail, list each one and the exact failure reason.
"""


TOOL_DECLARATIONS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="navigate",
        description="Open a URL in the browser. ONLY use the exact pre-built URLs provided in your instructions. Never navigate to a homepage.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"url": types.Schema(type="STRING")},
            required=["url"]
        )
    ),
    types.FunctionDeclaration(
        name="get_page_text",
        description="Read all visible text on the current page. Call after wait. Look for hotel names, prices per night, and ratings.",
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
        description="Wait for page to render. Always use ms=4000 after navigate, ms=2000 after scroll.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"ms": types.Schema(type="INTEGER")},
            required=["ms"]
        )
    ),
    types.FunctionDeclaration(
        name="scroll_down",
        description="Scroll down to reveal more hotel listings. Use pixels=1200.",
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


def _parse_search_params(message: str, chat_history: list) -> tuple[str, datetime, datetime, int]:
    """
    Extract city, checkin, checkout, adults from the conversation.
    Returns (city, checkin_dt, checkout_dt, adults).
    Falls back to sensible defaults.
    """
    import re

    full_text = message
    if chat_history:
        for msg in chat_history[-10:]:
            full_text += " " + msg.get("content", "")

    # --- city ---
    city = "Ooty"  # default; will be overridden if found
    city_patterns = [
        r"hotels?\s+in\s+([A-Za-z\s]+?)(?:\s+with|\s+for|\s+on|\s+from|\s+check|,|$)",
        r"in\s+([A-Za-z\s]{3,20}?)(?:\s+with|\s+for|\s+check|,|\.|\?|$)",
    ]
    for pat in city_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            city = m.group(1).strip().title()
            break

    # --- checkin date ---
    checkin_dt = datetime.now() + timedelta(days=1)
    date_pat = r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"
    dates_found = re.findall(date_pat, full_text)
    if dates_found:
        checkin_dt = _parse_date(dates_found[0])

    # --- nights / checkout ---
    nights = 1
    nights_m = re.search(r"(\d+)\s*nights?", full_text, re.IGNORECASE)
    if nights_m:
        nights = int(nights_m.group(1))
    checkout_dt = checkin_dt + timedelta(days=nights)

    # --- adults ---
    adults = 2
    adults_m = re.search(r"(\d+)\s*adults?", full_text, re.IGNORECASE)
    if adults_m:
        adults = int(adults_m.group(1))

    return city, checkin_dt, checkout_dt, adults


async def run_hotel_comparison_agent(
    message: str,
    websocket: WebSocket,
    save_fn,
    chat_history: list = None
) -> str:
    browser_agent = BrowserAgent()
    await browser_agent.start()
    source_link = ""

    try:
        # Parse search params from conversation so URLs are pre-built in Python
        city, checkin_dt, checkout_dt, adults = _parse_search_params(message, chat_history or [])
        print(f"[HotelAgent] Params → city={city}, checkin={checkin_dt.date()}, checkout={checkout_dt.date()}, adults={adults}")

        system_prompt = _build_system_prompt(checkin_dt, checkout_dt, adults, city)

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
        print(f"[HotelAgent] Start — fn_calls={bool(response.function_calls)}, text={bool(_extract_text(response))}")

        for iteration in range(MAX_ITERATIONS):
            fn_calls = response.function_calls or []
            print(f"[HotelAgent] Iter {iteration + 1} — {len(fn_calls)} tool call(s)")

            if not fn_calls:
                full_answer = _extract_text(response)
                print(f"[HotelAgent] Done. Preview: {full_answer[:200]}")
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
            print(f"[HotelAgent] Next — fn_calls={bool(response.function_calls)}, text={bool(_extract_text(response))}")

        if not full_answer:
            full_answer = (
                "⚠️ Could not retrieve hotel data after trying multiple websites.\n"
                "Please search directly:\n"
                "• https://www.booking.com\n"
                "• https://www.agoda.com\n"
                "• https://www.makemytrip.com/hotels"
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
        error_msg = f"⚠️ Hotel Comparison Agent error: {str(e)}"
        print(f"[HotelAgent] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({"type": "token", "content": error_msg})
        await websocket.send_json({"type": "end", "full_answer": error_msg, "sources": []})
        save_fn(error_msg, [])
        return error_msg

    finally:
        await browser_agent.close()
