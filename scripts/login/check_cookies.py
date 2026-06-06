#!/usr/bin/env python3
"""检查当前项目中的登录 Cookie 状态。"""

from pathlib import Path
import json
from datetime import datetime
import time

def get_session_dir():
    """获取 Cookie 存储目录路径。"""
    return Path(__file__).resolve().parent.parent.parent / "agent" / "sessions"

def get_browser_profile_dir():
    """获取浏览器配置文件目录。"""
    return Path(__file__).resolve().parent.parent.parent.parent / "browser_profile_qcc"

def is_expired(expires):
    """检查 Cookie 是否过期。"""
    if expires is None:
        return False
    try:
        exp = float(expires)
        if exp <= 0:
            return False
        return exp < time.time()
    except (ValueError, TypeError):
        return False

def format_expires(expires):
    """格式化过期时间。"""
    if expires is None or expires == 0:
        return "会话 Cookie（关闭浏览器后失效）"
    try:
        exp = float(expires)
        if exp <= 0:
            return "会话 Cookie"
        return datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(expires)

def check_stored_cookies():
    """检查已存储的 Cookie 文件。"""
    session_dir = get_session_dir()
    print("=" * 60)
    print("📋 已存储的 Cookie 文件")
    print("=" * 60)
    
    if not session_dir.exists():
        print("  ❌ 未找到 sessions 目录")
        return
    
    cookie_files = list(session_dir.glob("*_cookies.json"))
    storage_files = list(session_dir.glob("*storage_state*.json"))
    
    if not cookie_files and not storage_files:
        print("  ❌ 未找到已保存的 Cookie 文件")
        return
    
    for cookie_file in cookie_files:
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            cookies = data.get("cookies", [])
            saved_at = data.get("saved_at", "未知")
            
            print(f"\n  📁 {cookie_file.name}")
            print(f"     ├─ 保存时间: {saved_at}")
            print(f"     └─ Cookie 数量: {len(cookies)}")
            
            for i, cookie in enumerate(cookies[:5], 1):
                expired = is_expired(cookie.get("expires"))
                status = "❌ 已过期" if expired else "✅ 有效"
                print(f"        [{i}] {cookie.get('name')} - {status}")
                print(f"           域名: {cookie.get('domain', '')}")
                print(f"           路径: {cookie.get('path', '')}")
                print(f"           过期: {format_expires(cookie.get('expires'))}")
            
            if len(cookies) > 5:
                print(f"        ... 还有 {len(cookies) - 5} 条 Cookie")
                
        except Exception as e:
            print(f"  ⚠️ 读取 {cookie_file.name} 失败: {e}")

def check_browser_profile():
    """检查浏览器配置文件目录中的登录状态。"""
    profile_dir = get_browser_profile_dir()
    print("\n" + "=" * 60)
    print("🌐 浏览器配置文件目录")
    print("=" * 60)
    
    if not profile_dir.exists():
        print("  ❌ 未找到浏览器配置文件目录")
        return
    
    print(f"  目录路径: {profile_dir}")
    
    # 检查 Cookie 文件
    cookie_db = profile_dir / "Default" / "Network" / "Cookies"
    if cookie_db.exists():
        print(f"  ✅ Cookie 数据库: {cookie_db.name} ({cookie_db.stat().st_size} bytes)")
    else:
        print("  ❌ Cookie 数据库不存在")
    
    # 检查 IndexedDB
    indexed_db = profile_dir / "Default" / "IndexedDB"
    if indexed_db.exists():
        sites = [d for d in indexed_db.iterdir() if d.is_dir()]
        print(f"  ✅ IndexedDB 站点数量: {len(sites)}")
        for site in sites:
            print(f"     └─ {site.name}")
    
    # 检查 Local Storage
    local_storage = profile_dir / "Default" / "Local Storage"
    if local_storage.exists():
        print("  ✅ Local Storage: 存在")
    
    # 检查登录数据
    login_data = profile_dir / "Default" / "Login Data"
    if login_data.exists():
        print(f"  ✅ 登录数据: {login_data.name} ({login_data.stat().st_size} bytes)")

def main():
    print("\n" + "=" * 60)
    print("🍪 Cookie 登录状态检查工具")
    print("=" * 60)
    
    check_stored_cookies()
    check_browser_profile()
    
    print("\n" + "=" * 60)
    print("📝 说明")
    print("=" * 60)
    print("  1. JSON 格式 Cookie: 通过 export_cookies.py 导出，供后续会话自动登录")
    print("  2. 浏览器配置文件: browser_profile_qcc/ 包含企查查的持久化登录状态")
    print("  3. 如需导出新 Cookie，请运行: python export_cookies.py")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
