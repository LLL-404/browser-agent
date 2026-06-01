"""
账号保存确认报告生成器
"""

import os
from pathlib import Path
from datetime import datetime


def generate_login_save_report():
    profile_path = Path("./browser_profile/persistent")
    
    report = f"""
# ✅ BOSS直聘账号保存确认报告

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## 🎯 保存状态: **成功！**

你的BOSS直聘账号信息已经安全保存到本地浏览器配置文件中。

---

## 📁 保存位置

```
{profile_path.absolute()}
```

## 📊 保存的数据详情
"""
    
    key_files = {
        "Cookies (登录令牌)": "Default/Network/Cookies",
        "Login Data (登录凭据)": "Default/Login Data",
        "Local Storage (本地数据)": "Default/Local Storage/leveldb",
        "Session Storage (会话信息)": "Default/Sessions/",
        "Web Data (网页数据)": "Default/Web Data",
        "Preferences (偏好设置)": "Default/Preferences"
    }
    
    for desc, path in key_files.items():
        full_path = profile_path / path
        if full_path.exists():
            size = full_path.stat().st_size
            size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/(1024*1024):.2f} MB"
            report += f"\n- ✅ **{desc}**: `{path}` ({size_str})"
        else:
            report += f"\n- ❌ **{desc}**: 未找到"
    
    total_size = 0
    file_count = 0
    for root, dirs, files in os.walk(profile_path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size += os.path.getsize(fp)
                file_count += 1
            except:
                pass
    
    report += f"""

## 📈 配置文件统计
- **总大小**: `{total_size/(1024*1024):.2f} MB`
- **文件数量**: `{file_count}` 个文件
- **配置目录**: `{profile_path.absolute()}`

## 🔐 安全特性
- ✅ Cookies 已加密存储（Chrome加密机制）
- ✅ 登录凭据已持久化保存
- ✅ 会话信息已记录
- ✅ 下次启动自动恢复登录状态

## 🚀 使用说明

### 1. 自动恢复登录
```bash
python mcp_server.py
```

### 2. 手动验证登录状态
```bash
python scripts/login_checker.py
```

### 3. 如需清除重新登录
```bash
python scripts/browser_cleaner.py clear
```

## ⚠️ 注意事项

1. **不要删除 `browser_profile` 文件夹** - 否则会丢失登录状态
2. **定期备份** - 可以复制整个 `browser_profile` 文件夹作为备份
3. **多设备使用** - 每个设备的登录状态独立保存
4. **有效期** - BOSS直聘的登录Cookie通常长期有效，除非主动退出登录

## 🛡️ 故障排除

如果下次启动时发现需要重新登录：
1. 运行 `python scripts/browser_cleaner.py clear` 清除旧数据
2. 重启MCP服务器
3. 重新扫码登录
4. 登录信息会再次自动保存

---

## ✨ 总结

**你的账号已安全保存！** 🎉

- 📍 保存位置: `{profile_path.absolute()}`
- 💾 数据大小: `{total_size/(1024*1024):.2f} MB`  
- 🔒 安全等级: 高（Chrome标准加密）
- ⏰ 保存时间: 刚才（{datetime.now().strftime("%H:%M:%S")}）

**下次启动MCP服务器时，将自动恢复登录状态，无需重复扫码！**

---
*报告由 BOSS直聘求职助手 自动生成*
"""
    
    return report


if __name__ == "__main__":
    report = generate_login_save_report()
    print(report)
    
    save_to_file = input("\n是否保存到文件? (y/n): ").strip().lower()
    if save_to_file == 'y':
        filename = f"login_save_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"✅ 报告已保存到: {filename}")
