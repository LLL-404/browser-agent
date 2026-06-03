# 登录态保存工具链交付报告

**交付时间**：2026-06-01
**任务**：开发智能登录检测能力 + 保存企查查/天眼查登录态

---

## 任务一：auto_detect_login 开发完成

**交付物**：`agent/core/session.py` — `auto_detect_login` 函数
**新增 CLI**：`python -m agent.cli.main login --url <URL> --save <PATH> [--cookie <NAME>]`

### 检测维度

| 维度 | 规则 | 优先级 |
|------|------|--------|
| URL 变化 | 从含 login 的 URL 跳转至不含 login 的 URL | 中 |
| Cookie 出现 | 指定名称的 Cookie 出现（如 auth_token、qcc_token） | 最高 |
| DOM 消失 | 含"登录"文本的按钮/链接从页面消失（需先确认初始存在） | 中 |
| DOM 出现 | 用户信息元素出现（"退出登录"按钮、用户名等） | 高 |
| 自定义规则 | 调用方可传入 URL/DOM 自定义触发条件 | 按需 |

### 执行流程

打开浏览器 → 导航至登录页 → 智能轮询检测（每 2 秒）→ 最长等待 120 秒 → 检测成功自动保存 → 超时回退到手动 Enter 确认

---

## 任务二：企查查/天眼查登录态保存

### 企查查 (qcc.com) — ✅ 成功

- **文件**: `sessions/qcc_storage_state.json`
- **Cookie**: 26 个（含 `QCCSESSID`、`acw_tc` 等关键会话 Cookie）
- **大小**: 25 KB
- **检测依据**: 页面中出现 `a:has-text('退出')` 用户登录元素

### 天眼查 (tianyancha.com) — ⚠️ 部分完成

- **文件**: `sessions/tyc_storage_state.json`
- **Cookie**: 13-26 个（含 `auth_token`、`TYCID`、`tyc-user-info`）
- **大小**: 5-11 KB
- **状态**: Boss 未在 Playwright 浏览器窗口中完成登录操作，当前保存的 Cookie 主要为匿名态
- **待办**: Boss 需登录天眼查后重新保存

### 文件清单

| 文件 | 状态 | Cookie | 大小 |
|------|------|--------|------|
| `sessions/qcc_storage_state.json` | ✅ 已登录 | 26 | 25 KB |
| `sessions/tyc_storage_state.json` | ⚠️ 匿名态 | 26 | 11 KB |
| `sessions/storage_state.json` | ✅ 旧存档 (DeepSeek) | - | 26 KB |

---

## 技术要点

1. **浏览器持久化**：`BrowserController._start_playwright` 使用 `user_data_dir="./browser_profile"`，会话状态跨运行持久化
2. **反爬**：天眼查/企查查登录页均有 Geetest 滑块验证码，无法自动填充密码
3. **CLI 扩展**：`agent/cli/main.py` 新增 `login` 子命令 + `browse` 子命令增加 `--url` 参数
4. **MCP 扩展**：`agent/mcp/server.py` 新增 `browser_save_state`、`browser_get_cookies` 工具
5. **已知 Bug**：`BrowserController.stop()` 中 `__aexit__` 调用已修复为 `await pw.stop()`
