import asyncio
from concurrent.futures import ThreadPoolExecutor
# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright
try:
    # pyrefly: ignore [missing-import]
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

# ─────────────────────────────────────────────────────────
# WHY sync_playwright instead of async_playwright?
#
# async_playwright internally calls asyncio.create_subprocess_exec()
# to launch the Chromium process. On Windows, uvicorn uses
# SelectorEventLoop which does NOT support subprocess creation,
# causing NotImplementedError — regardless of any policy fix.
#
# Solution: Use sync_playwright (the synchronous Playwright API)
# and run it inside a ThreadPoolExecutor. Each BrowserAgent
# gets its own single-threaded executor so Playwright objects
# are never shared across threads (they are NOT thread-safe).
# The `await loop.run_in_executor(...)` bridge lets us call
# blocking sync code from async FastAPI/WebSocket handlers.
# ─────────────────────────────────────────────────────────

class BrowserAgent:
    def __init__(self):
        self._pw = None
        self._browser = None
        self.page = None
        # One dedicated thread per browser session — Playwright is not thread-safe
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._loop = None  # set in start()

    # ── Lifecycle ──────────────────────────────────────────

    async def start(self):
        """Launch the browser in the dedicated background thread."""
        self._loop = asyncio.get_event_loop()
        await self._loop.run_in_executor(self._executor, self._sync_start)

    def _sync_start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,   # ← True = silent background, False = visible window
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        self.page = context.new_page()
        if STEALTH_AVAILABLE:
            stealth_sync(self.page)
            print("[BrowserAgent] Stealth mode active")

    async def close(self):
        """Close the browser and shut down the executor."""
        await self._loop.run_in_executor(self._executor, self._sync_close)
        self._executor.shutdown(wait=False)

    def _sync_close(self):
        try:
            if self.page:    self.page.close()
            if self._browser: self._browser.close()
            if self._pw:     self._pw.stop()
        except Exception:
            pass

    # ── Tools (called by the AI agent) ────────────────────

    async def navigate(self, url: str) -> str:
        return await self._loop.run_in_executor(self._executor, self._sync_navigate, url)

    def _sync_navigate(self, url: str) -> str:
        try:
            if not url.startswith("http"):
                url = "https://" + url
            # "domcontentloaded" is much faster and doesn't get stuck on tracking scripts like "networkidle" does
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # Optionally wait for "load" but don't crash if it times out
            try:
                self.page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass
                
            return f"Navigated to {url}. Page title: {self.page.title()}"
        except Exception as e:
            return f"Error navigating: {str(e)}"

    async def get_page_text(self) -> str:
        return await self._loop.run_in_executor(self._executor, self._sync_get_page_text)

    def _sync_get_page_text(self) -> str:
        try:
            text = self.page.evaluate("document.body.innerText")
            return text[:5000] + "\n...(truncated)"
        except Exception as e:
            return f"Error extracting text: {str(e)}"

    async def click_element(self, selector: str) -> str:
        return await self._loop.run_in_executor(self._executor, self._sync_click, selector)

    def _sync_click(self, selector: str) -> str:
        try:
            self.page.click(selector, timeout=10000)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            return f"Clicked element: {selector}"
        except Exception as e:
            return f"Error clicking: {str(e)}"

    async def fill_input(self, selector: str, value: str) -> str:
        return await self._loop.run_in_executor(self._executor, self._sync_fill, selector, value)

    def _sync_fill(self, selector: str, value: str) -> str:
        try:
            self.page.fill(selector, value)
            return f"Filled {selector} with '{value}'"
        except Exception as e:
            return f"Error filling input: {str(e)}"

    async def press_key(self, key: str) -> str:
        return await self._loop.run_in_executor(self._executor, self._sync_press, key)

    def _sync_press(self, key: str) -> str:
        try:
            self.page.keyboard.press(key)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            return f"Pressed key: {key}"
        except Exception as e:
            return f"Error pressing key: {str(e)}"
        
    async def get_interactive_elements(self) -> str:
        return await self._loop.run_in_executor(self._executor, self._sync_get_interactive_elements)

    def _sync_get_interactive_elements(self) -> str:
        try:
            elements = self.page.locator("input, button, select, textarea, a").evaluate_all("""
            els => els.slice(0, 80).map((el, i) => ({
            index: i,
            tag: el.tagName,
            text: el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '',
            type: el.getAttribute('type'),
            name: el.getAttribute('name'),
            id: el.id,
            placeholder: el.getAttribute('placeholder'),
            selector:
                el.id ? '#' + el.id :
                el.name ? el.tagName.toLowerCase() + '[name="' + el.name + '"]' :
                el.placeholder ? el.tagName.toLowerCase() + '[placeholder="' + el.placeholder + '"]' :
                null
        }))
        """)
            return str(elements)
        except Exception as e:
            return f"Error getting interactive elements: {str(e)}"
    
    async def get_current_url(self) -> str:
        return await self._loop.run_in_executor(self._executor, self._sync_get_current_url)

    def _sync_get_current_url(self) -> str:
        try:
            return self.page.url
        except Exception as e:
            return f"Error getting URL: {str(e)}"