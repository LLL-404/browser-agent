"""Find send button on DeepSeek page."""
import json, time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(Path("browser_profile/playwright_send").resolve()),
        headless=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    state = json.loads(Path("sessions/storage_state.json").read_text(encoding="utf-8"))
    cookies = state.get("cookies", [])
    if cookies:
        ctx.add_cookies(cookies)
    for od in state.get("origins", []):
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
    time.sleep(3)
    buttons = page.evaluate("""() => Array.from(document.querySelectorAll("button")).map(b => ({
        text: (b.innerText || "").trim().slice(0,40),
        aria: b.getAttribute("aria-label") || "",
        cls: (b.className || "").slice(0,80),
        type: b.type || "",
    }))""")
    print("=== All buttons ===")
    for b in buttons:
        if b["text"] or b["aria"]:
            print(json.dumps(b, ensure_ascii=False))
    all_els = page.evaluate("""() => Array.from(document.querySelectorAll("button, div[role='button'], a[role='button']")).filter(el => el.offsetParent !== null).map(el => ({
        tag: el.tagName,
        text: (el.innerText || "").trim().slice(0,40),
        aria: el.getAttribute("aria-label") || "",
        role: el.getAttribute("role") || "",
    }))""")
    print("=== Visible clickable elements ===")
    for el in all_els:
        if el["text"] or el["aria"]:
            print(json.dumps(el, ensure_ascii=False))
    ctx.close()
