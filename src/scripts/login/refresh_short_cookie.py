"""短效 Cookie 自动刷新 — 检测 + 刷新 + 验证。

用法:
    python src/scripts/login/check_qcc_login.py --refresh

功能:
    1. 加载已保存的企查查 storage_state
    2. 检查 acw_tc 等短效 Cookie 是否即将过期
    3. 如需刷新，启动浏览器访问企查查首页获取新令牌
    4. 保存更新后的 storage_state
"""
import asyncio
import json
import sys
from pathlib import Path

# 将 src/ 加入 sys.path 以便导入项目模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.core.session import (
    check_short_lived_cookies,
    refresh_short_lived_cookies,
    load_storage_state,
)
from playwright.async_api import async_playwright


def eprint(*a, **kw):
    s = " ".join(str(x) for x in a) + kw.get("end", "\n")
    sys.stdout.buffer.write(s.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


async def main():
    eprint("=" * 60)
    eprint("  短效 Cookie 自动检测与刷新工具")
    eprint("=" * 60)

    # ── Step 1: 加载 storage_state ──
    # 优先加载企查查专用 storage_state，回退到默认路径
    state = None
    qcc_path = Path("sessions/qcc_storage_state.json")
    if qcc_path.exists():
        import aiofiles
        async with aiofiles.open(qcc_path, "r", encoding="utf-8") as f:
            content = await f.read()
        state = json.loads(content)
    if not state:
        state = await load_storage_state()
    if not state:
        eprint("[!] 未找到 storage_state 文件，请先运行 qcc_login.py 登录")
        return

    cookies = state.get("cookies", [])
    eprint(f"\n[1/4] 已加载 {len(cookies)} 条 Cookie")

    # ── Step 2: 检测短效 Cookie ──
    stale = check_short_lived_cookies(cookies)

    if not stale:
        eprint("[2/4] 所有短效 Cookie 均在有效期内，无需刷新")
        for c in cookies:
            name = c.get("name")
            exp = c.get("expires")
            if exp is None or exp <= 0:
                continue
            from datetime import datetime as dt
            exp_dt = dt.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M:%S")
            eprint(f"      {name}: 过期于 {exp_dt}")
        return

    eprint(f"\n[2/4] 检测到 {len(stale)} 条需关注的短效 Cookie:")
    for s in stale:
        status = "⚠️ 即将过期" if s["need_refresh"] else "✅ 正常"
        eprint(f"      [{status}] {s['name']} ({s['description']})")
        eprint(f"         剩余: {s['remaining_sec']} 秒 | 占比: {s['ratio']*100:.1f}%")
        eprint(f"         域名: {s['domain']}")
        need_refresh = any(s["need_refresh"] for s in stale)

    if not need_refresh:
        eprint("\n[3/4] 所有 Cookie 剩余充足，跳过刷新")
        return

    # ── Step 3: 启动浏览器刷新 ──
    eprint(f"\n[3/4] 正在启动浏览器刷新 Cookie...")
    profile_dir = Path("./browser_profile_qcc")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        result = await refresh_short_lived_cookies(
            page, target_url="https://www.qcc.com"
        )

        if result["ok"] and result["refreshed"]:
            eprint(f"[OK] 成功刷新 {len(result['refreshed'])} 条 Cookie:")
            for r in result["refreshed"]:
                eprint(f"      + {r['name']} ({r['description']})")
                eprint(f"        新值: {r['new_value_preview']}")
        elif result["ok"]:
            eprint("[OK] 页面访问成功，但 Cookie 值未变化（可能已被服务端续期）")
        else:
            eprint(f"[!] 刷新失败: {result.get('error', '未知错误')}")

        eprint(f"\n[4/4] 当前总 Cookie 数: {result.get('total_cookies', '?')}")

        # ── Step 4: 再次检测确认 ──
        try:
            fresh_cookies = await context.cookies()
            fresh_stale = check_short_lived_cookies(fresh_cookies)
            if fresh_stale:
                any_need = any(s["need_refresh"] for s in fresh_stale)
                if any_need:
                    eprint("[!] 刷新后仍有 Cookie 接近过期（可能是 WAF 规则变化）")
                else:
                    eprint("[OK] 刷新后所有短效 Cookie 均在安全范围内")
            else:
                eprint("[OK] 无需关注的短效 Cookie")
        except Exception:
            pass

        await context.close()

    eprint("\n" + "=" * 60)
    eprint("  完成")
    eprint("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
