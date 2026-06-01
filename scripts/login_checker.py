"""
登录状态验证工具 — 检查并确认BOSS直聘登录信息是否有效
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime


def check_login_status():
    profile_dir = Path("./browser_profile/persistent/Default")
    
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


def print_login_report():
    print("🔍 检查BOSS直聘登录状态...")
    print("=" * 60)
    
    status = check_login_status()
    
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
    
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        status = check_login_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print_login_report()
