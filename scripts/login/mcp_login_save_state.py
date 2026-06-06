#!/usr/bin/env python3
"""启动 MCP 服务器并打开浏览器，供 Boss 通过 MCP 工具交互。"""
import json, asyncio, subprocess, time, signal
from pathlib import Path

from browser_agent.core.browser import BrowserController
from browser_agent.core.agent import BrowserAgent

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("=" * 55)
    print("  MCP 交互模式 — 浏览器将打开，Boss 手动登录后")
    print("  此脚本将等待并保存登录态。")
    print("=" * 55)

    ctrl = BrowserController()
    agent = BrowserAgent(ctrl)

    # 打开天眼查
    result = await agent.open(url="https://www.tianyancha.com/login")
    if not result.get("ok"):
        print(f"❌ 浏览器启动失败: {result.get('error')}")
        return

    print(f"✅ 浏览器已打开 → https://www.tianyancha.com/login")
    print()
    print(f"  MCP 服务器模式:")
    print(f"    请 Boss 在浏览器中完成天眼查登录（扫码/手机号）")
    print(f"    完成后此脚本将自动检测并保存登录态")
    print()
    print(f"  ⏳ 正在等待登录（最长 5 分钟）...")

    # Use auto_detect_login with longer timeout
    from browser_agent.core.session import auto_detect_login
    page = ctrl._page

    info = await auto_detect_login(
        page=page,
        timeout=300,
        interval=2,
        cookie_names=["tyc_token", "TYC_USER_INFO", "TYC_SESSION", "auth_token"],
        url_has_login=True,
    )

    detected = info.get("detected", False)
    reason = info.get("reason", "")
    detail = info.get("detail", "")

    if detected:
        print(f"\n✅ 检测到登录成功（{detail}）")
    else:
        print(f"\n⚠️  自动检测超时，尝试保存当前状态...")

    await asyncio.sleep(3)

    # Save state
    try:
        state = await page.context.storage_state()
        save_path = SESSIONS_DIR / "tyc_storage_state.json"
        save_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 登录态已保存至 {save_path}")
        print(f"   Cookie 数量: {len(state.get('cookies', []))}")
        print(f"   文件大小: {save_path.stat().st_size} bytes")
    except Exception as e:
        print(f"❌ 保存失败: {e}")

    try:
        await agent.close()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
