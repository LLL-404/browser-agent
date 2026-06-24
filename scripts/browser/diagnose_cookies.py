"""Cookie 注入诊断脚本 — 追踪浏览器引擎选择、Cookie 加载和实际状态。"""

import asyncio
import sys
import time
import warnings
from pathlib import Path

# 确保能引用到项目源码
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

# 忽略 Python 3.14 Windows asyncio 关闭时的无害警告（CPython 内部清理顺序问题）
warnings.filterwarnings("ignore",
                        message="unclosed transport",
                        category=ResourceWarning)

from browser_agent.core.browser import BrowserController
from browser_agent.core.session import (
    COOKIE_DIR,
    auto_detect_login,
    cookie_path,
    has_saved_cookies,
    load_cookies_from_file,
    save_cookies_to_file,
)
from shared.logging_config import get_logger

logger = get_logger("diagnose")


def _fmt_expires(expires: float | None) -> str:
    if expires is None or expires <= 0:
        return "会话级（关闭后失效）"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(expires)))
    except (ValueError, TypeError):
        return str(expires)


def _fmt_age(expires: float | None) -> str:
    """计算 Cookie 剩余有效期描述。"""
    if expires is None or expires <= 0:
        return "N/A"
    remaining = float(expires) - time.time()
    if remaining < 0:
        return f"已过期 {abs(remaining):.0f}s"
    if remaining < 60:
        return f"剩余 {remaining:.0f}s"
    if remaining < 3600:
        return f"剩余 {remaining / 60:.0f}min"
    return f"剩余 {remaining / 3600:.1f}h"


async def diagnose() -> None:
    """执行完整的 Cookie 诊断流程。"""
    print("=" * 70)
    print("  🍪 Cookie 注入诊断 — 追踪登录态丢失的根因")
    print("=" * 70)

    # ── 阶段 1：检查 Cookie 文件状态 ──
    print("\n📋 [阶段 1] Cookie 文件状态")
    print("-" * 50)
    print(f"  Cookie 目录: {COOKIE_DIR}")
    print(f"  目录是否存在: {'✅' if COOKIE_DIR.exists() else '❌'}")

    boss_path = cookie_path("boss")
    print(f"  期望的 Cookie 文件: {boss_path}")
    print(f"  文件是否存在: {'✅' if boss_path.exists() else '❌'}")

    # 列出 sessions 目录下所有 JSON 文件
    json_files = list(COOKIE_DIR.glob("*.json")) if COOKIE_DIR.exists() else []
    if json_files:
        print(f"  实际存在的 JSON 文件 ({len(json_files)}):")
        for f in json_files:
            size = f.stat().st_size
            print(f"    - {f.name} ({size} bytes)")
    else:
        print("  实际存在的 JSON 文件: ❌ 无")

    print(f"  has_saved_cookies('boss'): {has_saved_cookies('boss')}")

    # 尝试加载 Cookie
    cookies_from_file = await load_cookies_from_file("boss")
    print(f"  load_cookies_from_file() 返回: {len(cookies_from_file)} 条 Cookie")

    # 检查 profiles 目录
    profiles_dir = COOKIE_DIR / "profiles"
    if profiles_dir.exists():
        profile_dirs = [d for d in profiles_dir.iterdir() if d.is_dir()]
        print(f"  profiles 目录: {len(profile_dirs)} 个旧 session 目录")
        for d in profile_dirs[-3:]:  # 只显示最近 3 个
            mtime = time.strftime(
                "%m-%d %H:%M",
                time.localtime(d.stat().st_mtime),
            )
            print(f"    - {d.name} (mtime={mtime})")
        if len(profile_dirs) > 3:
            print(f"    ... 还有 {len(profile_dirs) - 3} 个")
    else:
        print("  profiles 目录: 不存在")

    # ── 阶段 2：启动浏览器并追踪 Cookie 注入 ──
    print("\n🚀 [阶段 2] 启动浏览器")
    print("-" * 50)

    ctrl = BrowserController()

    print(f"  Camoufox 可用: {ctrl.has_camoufox}")

    # 检查 camoufox 是否可导入
    try:
        from camoufox import AsyncCamoufox  # noqa: F401
        print("  camoufox 包: ✅ 已安装")
    except ImportError:
        print("  camoufox 包: ❌ 未安装")

    started = await ctrl.start(headless=False, use_camoufox=True, profile_name="zhipin")
    print(f"  浏览器启动: {'✅' if started else '❌'}")
    print(f"  启动引擎: {ctrl.engine}")
    print(f"  运行状态: {ctrl.is_running}")

    if not started or not ctrl.page:
        print("\n❌ 浏览器启动失败，停止诊断")
        return

    # ── 阶段 3：导航前检查 Cookie 注入结果 ──
    print("\n🍪 [阶段 3] 导航前 — Cookie 注入状态")
    print("-" * 50)

    # 从浏览器上下文读取 Cookie
    try:
        ctx = ctrl.page.context
        pre_nav_cookies = await ctx.cookies()
        print(f"  浏览器上下文中 Cookie 数量: {len(pre_nav_cookies)}")
        if pre_nav_cookies:
            for c in pre_nav_cookies[:10]:
                status = "⚠️ 已过期" if _is_expired(c) else "✅"
                print(f"    {status} {c['name']:25s} domain={c['domain']:20s} "
                      f"path={c['path']:10s} expires={_fmt_age(c.get('expires'))}")
            if len(pre_nav_cookies) > 10:
                print(f"    ... 还有 {len(pre_nav_cookies) - 10} 条")
        else:
            print("  ⚠️ 上下文没有 Cookie！")
            print("  → 可能原因：has_saved_cookies() 返回 False，add_cookies 未被调用")
    except Exception as e:
        print(f"  ❌ 读取 Cookie 失败: {e}")

    # ── 阶段 4：导航到 BOSS直聘 ──
    print("\n🌐 [阶段 4] 导航到 BOSS直聘首页")
    print("-" * 50)

    url = "https://www.zhipin.com/?ka=header-home"
    nav_ok = await ctrl.navigate_to(url, check_health=False)
    print(f"  导航结果: {'✅' if nav_ok else '❌'}")
    print(f"  当前 URL: {await ctrl.get_current_url()}")
    print(f"  页面标题: {await ctrl.get_page_title()}")

    await asyncio.sleep(3)  # 等待页面渲染 + JS 执行

    # ── 阶段 5：导航后检查 Cookie 状态 ──
    print("\n🍪 [阶段 5] 导航后 — 浏览器实际 Cookie 状态")
    print("-" * 50)

    try:
        ctx = ctrl.page.context
        post_nav_cookies = await ctx.cookies()
        print(f"  浏览器上下文中 Cookie 数量: {len(post_nav_cookies)}")
        if post_nav_cookies:
            # 按域名分组展示
            domains = {}
            for c in post_nav_cookies:
                d = c["domain"]
                if d not in domains:
                    domains[d] = []
                domains[d].append(c)

            for domain, cookies in sorted(domains.items()):
                print(f"\n  📂 domain: {domain}")
                for c in cookies:
                    expires_str = _fmt_age(c.get("expires"))
                    value_preview = (c.get("value", "")[:20] + "...") if c.get("value") else "(空)"
                    print(f"     ├ {c['name']:25s} = {value_preview}")
                    print(f"     │  path={c['path']:20s} secure={c.get('secure')} httpOnly={c.get('httpOnly')} sameSite={c.get('sameSite')}")
                    print(f"     │  expires={expires_str}")

            # 检查是否有登录态相关的 Cookie
            auth_cookies = [
                c for c in post_nav_cookies
                if any(k in c["name"].lower() for k in [
                    "session", "token", "auth", "login", "sid",
                    "passport", "ssotoken", "user",
                ])
            ]
            if auth_cookies:
                print(f"\n  🔐 登录态相关 Cookie ({len(auth_cookies)} 条):")
                for c in auth_cookies:
                    print(f"     ✅ {c['name']:30s} domain={c['domain']}")
            else:
                print("\n  ❌ 未检测到登录态相关 Cookie")
                print("  → 可能原因：未注入 Cookie，或服务端 session 已过期")
        else:
            print("  ❌ 浏览器上下文中没有任何 Cookie")
            print("  → 确认是未被注入，还是被网站清除了？")
    except Exception as e:
        print(f"  ❌ 读取 Cookie 失败: {e}")

    # ── 阶段 6：检查页面 UI 登录状态 ──
    print("\n👤 [阶段 6] 页面 UI 登录状态检测")
    print("-" * 50)

    is_logged_in = False
    try:
        page_text = await ctrl.get_page_text(3000)
        login_keywords = ["登录", "注册", "未登录", "请登录"]
        user_keywords = ["退出", "我的", "个人中心", "用户名"]
        found_login = any(kw in page_text for kw in login_keywords)
        found_user = any(kw in page_text for kw in user_keywords)

        if found_user:
            print("  ✅ 页面显示已登录状态")
            is_logged_in = True
        elif found_login:
            print("  ❌ 页面显示未登录状态（存在登录/注册按钮）")
        else:
            print("  ⚠️ 无法确定登录状态")

        # 检查是否有验证码或拦截
        if "验证" in page_text or "安全" in page_text:
            print("  ⚠️ 页面可能被安全验证拦截")
    except Exception as e:
        print(f"  ❌ 检测失败: {e}")

    # ── 阶段 7：自动刷新登录态 ──
    if not is_logged_in and pre_nav_cookies and post_nav_cookies:
        print("\n🔄 [阶段 7] 检测到 Session 过期，尝试自动刷新登录态")
        print("-" * 50)
        print("  服务端 Session 已过期，需要重新登录")
        print("  浏览器将打开登录页面，请手动完成登录")
        print("  登录方式: 扫码 / 手机号验证码")
        print("-" * 50)

        # 导航到登录页面
        login_url = "https://www.zhipin.com/web/user/?ka=header-login"
        print(f"  导航到登录页: {login_url}")
        await ctrl.navigate_to(login_url, check_health=False)
        await asyncio.sleep(2)

        # 等待用户登录
        print(f"\n  ⏳ 等待登录（最长 5 分钟）...")
        login_result = await auto_detect_login(
            ctrl.page,
            timeout=300,
            cookie_names=["__zp_stoken__"],
            url_has_login=True,
        )

        if login_result.get("detected"):
            print(f"  ✅ 登录成功！({login_result.get('detail')})")
            
            # 保存新的 Cookie
            try:
                ctx = ctrl.page.context
                new_cookies = await ctx.cookies()
                save_result = await save_cookies_to_file(new_cookies, "boss")
                if save_result.get("ok"):
                    print(f"  ✅ 新 Cookie 已保存到 {save_result.get('path')}")
                    print(f"  Cookie 数量: {save_result.get('count')} 条")
                else:
                    print(f"  ❌ 保存 Cookie 失败: {save_result.get('error')}")
            except Exception as e:
                print(f"  ❌ 保存 Cookie 失败: {e}")
        else:
            print(f"  ❌ 登录超时或未检测到登录 ({login_result.get('detail')})")
    else:
        print("\n💡 [阶段 7] 登录状态检查结果")
        print("-" * 50)
        if not boss_path.exists():
            print("  ❌ Cookie 文件不存在 → 登录态永不会被加载")
            print("  解决方案：")
            print("  1. 手动在浏览器中登录 BOSS直聘")
            print("  2. 然后运行以下命令保存 Cookie:")
            print("     python scripts/login/save_login_state.py")
            print("     （或手动调用 save_cookies_to_file(cookies, 'boss')）")
        elif not pre_nav_cookies and not post_nav_cookies:
            print("  ❌ Cookie 文件存在但未成功注入浏览器上下文")
            print("  解决方案：检查 add_cookies 的 Cookie 格式是否正确")
        elif pre_nav_cookies and not post_nav_cookies:
            print("  ❌ Cookie 注入成功但在导航后被清除")
            print("  可能原因：网站检测到环境变化，清除了旧 Cookie")
        elif pre_nav_cookies and post_nav_cookies:
            print("  ✅ Cookie 注入成功且导航后仍然存在")
            print("  ✅ 页面显示已登录状态")

    print("\n" + "=" * 70)
    print("  诊断完成")
    print("=" * 70)

    # 保持浏览器窗口打开，让用户观察
    input("\n按 Enter 键关闭浏览器...")


def _is_expired(cookie: dict) -> bool:
    expires = cookie.get("expires")
    if expires is None:
        return False
    try:
        exp = float(expires)
        if exp <= 0:
            return False
        return exp < time.time()
    except (ValueError, TypeError):
        return False


if __name__ == "__main__":
    asyncio.run(diagnose())
