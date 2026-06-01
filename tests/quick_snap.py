"""极简测试：导航后立即截图，不做任何等待"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT = Path("tests/output")
OUTPUT.mkdir(parents=True, exist_ok=True)

async def snap():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        # 注入反重定向脚本
        await context.add_init_script("""
            (() => {
                const BLOCKED = ['about:blank', 'about:blank#/', 'about:blank#blocked'];
                const blocked = (url) => BLOCKED.some(b => url === b || (url || '').startsWith('about:blank'));
                const _locDesc = Object.getOwnPropertyDescriptor(Location.prototype, 'href');
                const _origGet = _locDesc.get, _origSet = _locDesc.set;
                if (_origSet) {
                    Object.defineProperty(Location.prototype, 'href', {
                        get: function() { return _origGet.call(this); },
                        set: function(val) { if (!blocked(val)) _origSet.call(this, val); },
                        configurable: true, enumerable: true
                    });
                }
                const _assign = Location.prototype.assign;
                const _replace = Location.prototype.replace;
                Location.prototype.assign = function(url) { if (!blocked(url)) _assign.call(this, url); };
                Location.prototype.replace = function(url) { if (!blocked(url)) _replace.call(this, url); };
                const _open = window.open;
                window.open = function(url) { if (blocked(url)) return null; return _open.apply(this, arguments); };
            })();
        """)

        page = await context.new_page()
        url = "https://www.zhipin.com/web/geek/jobs?city=101280600&query=普工"
        print(f"[→] goto {url}")
        await page.goto(url, wait_until="domcontentloaded")
        print(f"     URL: {page.url}")
        print(f"     Title: {await page.title()}")

        # 每 0.5 秒记录一次状态
        for i in range(20):
            await asyncio.sleep(0.5)
            u = page.url
            t = await page.title()
            cards = await page.query_selector_all("li.job-card-box")
            print(f"  [{i*0.5:.1f}s] url={u[:80]} | title={t[:40]} | cards={len(cards)}")
            if "about:blank" in u:
                print("  [!] 检测到 about:blank 重定向！")
                break

        await page.screenshot(path=str(OUTPUT / "quick_snap.png"), full_page=True)
        html = await page.content()
        (OUTPUT / "quick_snap.html").write_text(html, encoding="utf-8")
        print("\n[✓] 截图和 HTML 已保存")

        await asyncio.sleep(3)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(snap())
