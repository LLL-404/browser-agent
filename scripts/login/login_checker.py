"""
登录状态验证工具 — 检查 DeepSeek 和 BOSS直聘 登录信息是否有效
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_storage_state():
    """读取共享 storage_state 文件。"""
    state_path = PROJECT_ROOT / "sessions" / "storage_state.json"
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_login_status(target: str = "boss"):
    profile_dir = Path("./browser_profile/persistent/Default")
    if target == "deepseek":
        return _check_deepseek_login()
    return _check_boss_login(profile_dir)


def _check_deepseek_login():
    results = {
        "target": "deepseek",
        "storage_state_found": False,
        "deepseek_cookies": [],
        "has_valid_session": False,
        "login_status": "unknown",
        "last_saved": None,
    }
    state = _get_storage_state()
    if not state:
        results["login_status"] = "not_logged_in"
        results["message"] = "未找到共享登录态文件"
        return results

    results["storage_state_found"] = True
    results["last_saved"] = state.get("saved_at") or state.get("_saved_at")

    cookies = state.get("cookies", [])
    deepseek_cookies = [
        c for c in cookies
        if "deepseek.com" in c.get("domain", "")
        or "chat.deepseek.com" in c.get("domain", "")
    ]
    results["deepseek_cookies"] = [
        {"name": c.get("name"), "domain": c.get("domain"),
         "expires": c.get("expires"), "has_value": bool(c.get("value"))}
        for c in deepseek_cookies
    ]

    from browser_agent.core.session import filter_expired_cookies
    valid = filter_expired_cookies(deepseek_cookies)
    results["has_valid_session"] = len(valid) > 0

    if len(valid) > 3:
        results["login_status"] = "confirmed_logged_in"
    elif len(valid) > 0:
        results["login_status"] = "likely_logged_in"
    else:
        results["login_status"] = "not_logged_in"

    return results


def _check_boss_login(profile_dir):
    
    if not profile_dir.exists():
        return {"status": "no_profile", "message": "未找到浏览器配置文件"}
    
    results = {
        "profile_exists": True,
        "profile_size_mb": 0,
        "cookies_found": False,
        "login_data_found": False,
        "boss_cookies": [],
        "last_session_time": None,
        "login_status": "unknown"
    }
    
    total_size = 0
    for root, dirs, files in os.walk(profile_dir):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size += os.path.getsize(fp)
            except OSError:
                pass
    
    results["profile_size_mb"] = round(total_size / (1024 * 1024), 2)
    
    cookies_db = profile_dir / "Network" / "Cookies"
    if cookies_db.exists():
        results["cookies_found"] = True
        try:
            conn = sqlite3.connect(str(cookies_db))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name, value, expires_utc, is_secure 
                FROM cookies 
                WHERE host_key LIKE '%zhipin.com%' OR host_key LIKE '%bosszhipin.com%'
                ORDER BY expires_utc DESC
                LIMIT 20
            """)
            
            boss_cookies = cursor.fetchall()
            
            for cookie in boss_cookies:
                cookie_info = {
                    "name": cookie[0],
                    "has_value": bool(cookie[1]),
                    "expires": cookie[2],
                    "is_secure": cookie[3] == 1
                }
                
                if cookie[1]:
                    cookie_info["value_preview"] = cookie[1][:10] + "***" if len(cookie[1]) > 10 else "***"
                
                results["boss_cookies"].append(cookie_info)
            
            cursor.execute("""
                SELECT COUNT(*) FROM cookies 
                WHERE host_key LIKE '%zhipin.com%' 
                AND (name LIKE '%token%' OR name LIKE '%session%' OR name LIKE '%login%' OR name LIKE '%uid%')
            """)
            
            login_cookie_count = cursor.fetchone()[0]
            if login_cookie_count > 0:
                results["login_status"] = "likely_logged_in"
            
            conn.close()
            
        except Exception as e:
            results["cookies_error"] = str(e)
    
    login_data = profile_dir / "Login Data"
    if login_data.exists() and login_data.stat().st_size > 100:
        results["login_data_found"] = True
        results["login_status"] = "likely_logged_in"
    
    sessions_dir = profile_dir / "Sessions"
    if sessions_dir.exists():
        session_files = list(sessions_dir.glob("Session_*"))
        if session_files:
            latest_session = max(session_files, key=lambda f: f.stat().st_mtime)
            mod_time = datetime.fromtimestamp(latest_session.stat().st_mtime)
            results["last_session_time"] = mod_time.strftime("%Y-%m-%d %H:%M:%S")
    
    if len(results["boss_cookies"]) > 5 and results["login_data_found"]:
        results["login_status"] = "confirmed_logged_in"
    elif len(results["boss_cookies"]) > 0:
        results["login_status"] = "possibly_logged_in"
    else:
        results["login_status"] = "not_logged_in"
    
    return results


def print_login_report(target: str = "boss"):
    target_name = "DeepSeek" if target == "deepseek" else "BOSS直聘"
    print(f"🔍 检查{target_name}登录状态...")
    print("=" * 60)
    
    status = check_login_status(target)
    
    print(f"\n📁 配置文件状态:")
    print(f"   ✅ 存在: {status['profile_exists']}")
    print(f"   📊 大小: {status['profile_size_mb']} MB")
    
    print(f"\n🍪 Cookies状态:")
    print(f"   ✅ 文件存在: {status['cookies_found']}")
    print(f"   🔐 登录数据: {status['login_data_found']}")
    
    if status.get('boss_cookies'):
        print(f"\n📱 BOSS直聘Cookies ({len(status['boss_cookies'])} 个):")
        for i, cookie in enumerate(status['boss_cookies'][:10], 1):
            preview = cookie.get('value_preview', '无值')
            print(f"   {i}. {cookie['name']}: {preview}")
        
        if len(status['boss_cookies']) > 10:
            print(f"   ... 还有 {len(status['boss_cookies']) - 10} 个")
    
    if status.get('last_session_time'):
        print(f"\n⏰ 最后会话时间: {status['last_session_time']}")
    
    print(f"\n{'='*60}")
    print(f"🎯 **登录状态判定**: {status['login_status'].upper()}")
    print(f"{'='*60}")
    
    status_messages = {
        "confirmed_logged_in": "✅ 已确认登录 - Cookies和登录数据完整",
        "likely_logged_in": "🟡 可能已登录 - 找到部分登录数据",
        "possibly_logged_in": "🟠 可能有登录信息 - 建议验证",
        "not_logged_in": "❌ 未登录 - 未找到有效的登录信息",
        "unknown": "❓ 无法确定 - 请手动检查",
        "no_profile": "❌ 无配置文件 - 需要重新登录"
    }
    
    print(f"\n💡 说明: {status_messages.get(status['login_status'], '未知状态')}")
    
    return status


if __name__ == "__main__":
    import sys
    
    target = "boss"
    json_output = False
    
    for arg in sys.argv[1:]:
        if arg == "--json":
            json_output = True
        elif arg in ("--target", "-t"):
            idx = sys.argv.index(arg)
            if idx + 1 < len(sys.argv):
                target = sys.argv[idx + 1]
        elif arg in ("deepseek", "boss"):
            target = arg
    
    status = check_login_status(target)
    if json_output:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print_login_report(target)
