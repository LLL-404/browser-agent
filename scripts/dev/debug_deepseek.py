"""Debug DeepSeek login page state."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(Path("browser_profile/playwright_send").resolve()),
        headless=False, no_viewport=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # Load storage state
    state_path = Path("src/browser_agent/sessions/storage_state.json")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        cookies = state.get("cookies", [])
        if cookies:
            ctx.add_cookies(cookies)
        origins = state.get("origins", [])
        for od in origins:
            origin = od.get("origin", "")
            ls = od.get("localStorage", [])
            if ls and origin:
                page.goto(origin, wait_until="domcontentloaded", timeout=15000)
                for item in ls:
                    try:
                        page.evaluate("([k,v]) => window.localStorage.setItem(k,v)", [item["name"], item["value"]])
                    except Exception:
                        pass

    page.goto("https://chat.deepseek.com/a/chat/s/6ba0590c-3d11-4a43-8d02-4ecb95bcd10b", wait_until="domcontentloaded", timeout=20000)
    import time; time.sleep(2)

    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")
    body = page.inner_text("body")[:2000]
    print(f"Body text: {body[:500]}")

    # Check for login indicators
    for sel in ["div.ProseMirror[contenteditable='true']", "textarea[data-testid='chat-input']", "textarea[placeholder]", "div[contenteditable='true']"]:
        try:
            ct = page.locator(sel).count()
            print(f"  '{sel}': count={ct}")
        except Exception:
            pass

    ctx.close()
