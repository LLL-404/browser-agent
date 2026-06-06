"""
浏览器配置文件清理工具 — 清除被BOSS直聘标记的浏览器数据
"""

import os
import shutil
from pathlib import Path


def clear_browser_profile():
    profile_dirs = [
        "./browser_profile/persistent",
        "./browser_profile",
        "./browser_data"
    ]
    
    cleaned = []
    for profile_dir in profile_dirs:
        if os.path.exists(profile_dir):
            try:
                shutil.rmtree(profile_dir)
                cleaned.append(profile_dir)
                print(f"✓ 已清除: {profile_dir}")
            except Exception as e:
                print(f"✗ 清除失败 {profile_dir}: {e}")
    
    if not cleaned:
        print("ℹ 没有找到需要清除的浏览器配置文件")
    
    return cleaned


def check_profile_status():
    profile_dir = Path("./browser_profile/persistent")
    if not profile_dir.exists():
        return {"status": "clean", "message": "无现有配置文件"}
    
    files_to_check = [
        "Cookies",
        "Preferences", 
        "Local Storage/leveldb",
        "Session Storage",
        "GPUCache"
    ]
    
    status = {
        "status": "exists",
        "path": str(profile_dir.absolute()),
        "files_found": [],
        "size_mb": 0
    }
    
    for file_pattern in files_to_check:
        target = profile_dir / file_pattern
        if target.exists():
            status["files_found"].append(file_pattern)
    
    total_size = 0
    for root, dirs, files in os.walk(profile_dir):
        for f in files:
            fp = os.path.join(root, f)
            total_size += os.path.getsize(fp)
    
    status["size_mb"] = round(total_size / (1024 * 1024), 2)
    
    return status


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("🧹 开始清理浏览器配置文件...")
        cleared = clear_browser_profile()
        if cleared:
            print(f"\n✅ 清理完成！已清除 {len(cleared)} 个配置目录")
            print("建议重启MCP服务器以使用干净的浏览器实例")
        else:
            print("\nℹ 无需清理")
    else:
        print("📊 检查浏览器配置文件状态...")
        status = check_profile_status()
        
        print(f"\n状态: {status['status']}")
        if status['status'] == 'exists':
            print(f"路径: {status['path']}")
            print(f"大小: {status['size_mb']} MB")
            print(f"包含文件: {', '.join(status['files_found'])}")
            print("\n💡 提示: 如果遇到空白页面或反爬虫检测，运行:")
            print("   python scripts/browser_cleaner.py clear")
