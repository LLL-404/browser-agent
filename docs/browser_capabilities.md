# 浏览器自动化能力清单

## 类别索引

| 类别 | 能力数 | 页码 |
|------|--------|------|
| 1. 浏览器生命周期管理 | 7 项 | 下文 |
| 2. 页面导航与信息获取 | 5 项 | 下文 |
| 3. 页面交互操作 | 8 项 | 下文 |
| 4. 反检测与行为模拟 | 10 项 | 下文 |
| 5. 页面分析与调试 | 5 项 | 下文 |

---

## 1. 浏览器生命周期管理

---

### browser_open

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.open()` |
| 用途 | 启动浏览器（Camoufox 优先，回退 Playwright）并导航到起始 URL |
| 调用方式 | MCP `browser_open` / Python `agent.open(headless, url)` |
| 关键参数 | `headless: bool` — 无头模式；`url: str` — 起始地址（默认 about:blank） |
| 返回值 | `{"ok": bool, "url": str, "title": str, "engine": "camoufox"\|"playwright"}` |
| 依赖 | 无（首次调用） |

---

### browser_close

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.close()` / `BrowserController.stop()` |
| 用途 | 关闭浏览器，释放所有资源 |
| 调用方式 | MCP `browser_close` / Python `agent.close()` |
| 关键参数 | 无 |
| 返回值 | `{"ok": bool, "message": str}` |
| 依赖 | 需先 browser_open |

---

### save_session

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.save_session()` |
| 用途 | 将当前浏览器会话的 Cookie + localStorage 保存到 `sessions/{name}.json` |
| 调用方式 | Python `agent.save_session(name)` |
| 关键参数 | `name: str` — 会话标识（默认 `"default"`） |
| 返回值 | `{"ok": bool, "path": str, "cookies_count": int}` |
| 依赖 | 需先 browser_open 并完成登录 |

---

### load_session

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.load_session()` |
| 用途 | 从 `sessions/{name}.json` 恢复 Cookie + localStorage，自动导航回保存时的 URL |
| 调用方式 | Python `agent.load_session(name)` |
| 关键参数 | `name: str` — 会话标识 |
| 返回值 | `{"ok": bool, "url": str, "cookies_restored": int}` |
| 依赖 | 需先 browser_open，会话文件需存在 |

---

### save_cookies_to_file

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/session.py` → `save_cookies_to_file()` |
| 用途 | 将 Cookie 列表持久化为 JSON 文件，自动过滤过期项 |
| 调用方式 | Python `save_cookies_to_file(cookies, name)` |
| 关键参数 | `cookies: list[dict]` — Playwright cookie 格式；`name: str` — 文件名（默认 `"boss"`） |
| 返回值 | `{"ok": bool, "path": str, "count": int}` |
| 依赖 | 需先通过 `BrowserController.save_cookies()` 获取 Cookie 列表 |

---

### load_cookies_from_file

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/session.py` → `load_cookies_from_file()` |
| 用途 | 从 JSON 文件加载 Cookie 列表，自动过滤过期项 |
| 调用方式 | Python `load_cookies_from_file(name)` |
| 关键参数 | `name: str` — 文件名（默认 `"boss"`） |
| 返回值 | `list[dict]` — Cookie 列表 |
| 依赖 | 文件需存在 |

---

### save_storage_state / load_storage_state

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/session.py` → `save_storage_state()` / `load_storage_state()` |
| 用途 | 保存/恢复 Playwright 兼容的 `storage_state.json`（含 Cookie + localStorage），用于 `scripts/send_report.py` 等工具实现开机即登录 |
| 调用方式 | Python `save_storage_state(cookies, origins)` / `load_storage_state()` |
| 关键参数 | 同上，含 origin 级别的 localStorage 数据 |
| 返回值 | 保存返回路径和数量，加载返回完整 state dict |
| 依赖 | 共享登录态文件路径为 `sessions/storage_state.json` |

---

## 2. 页面导航与信息获取

---

### browser_navigate

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.navigate()` / `BrowserController.navigate_to()` |
| 用途 | 导航到指定 URL，等待 `domcontentloaded`，超时时不抛异常（返回 false） |
| 调用方式 | MCP `browser_navigate` / Python `agent.navigate(url)` |
| 关键参数 | `url: str` — 目标网址；`timeout: int` — 超时毫秒（默认 30000） |
| 返回值 | `{"ok": bool, "url": str, "title": str, "step": int}` |
| 依赖 | 需先 browser_open |

---

### browser_url

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.url()` |
| 用途 | 获取当前页面 URL 和标题 |
| 调用方式 | MCP `browser_url` / Python `agent.url()` |
| 关键参数 | 无 |
| 返回值 | `{"url": str, "title": str}` |
| 依赖 | 需先 browser_open |

---

### browser_text

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.text()` / `BrowserController.get_page_text()` |
| 用途 | 获取页面 `<body>` 的纯文本内容（截断至 max_len） |
| 调用方式 | MCP `browser_text` / Python `agent.text(max_len)` |
| 关键参数 | `max_len: int` — 最大字符数（默认 3000） |
| 返回值 | `{"text": str}` |
| 依赖 | 需先 browser_open |

---

### browser_html

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.html()` / `BrowserController.get_page_html()` |
| 用途 | 获取当前页面完整 HTML 源码（截断至 max_len） |
| 调用方式 | MCP `browser_html` / Python `agent.html(max_len)` |
| 关键参数 | `max_len: int` — 最大字符数（默认 8000） |
| 返回值 | `{"html": str}` |
| 依赖 | 需先 browser_open |

---

### browser_snapshot

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.snapshot()` |
| 用途 | 获取页面结构快照：可交互元素树（含 ref 编号）+ DOM 结构摘要 + 纯文本 |
| 调用方式 | MCP `browser_snapshot` / Python `agent.snapshot(max_length)` |
| 关键参数 | `max_length: int` — 文本截断（默认 3000） |
| 返回值 | `{"url": str, "title": str, "elements": str, "dom": dict, "text": str}` |
| 依赖 | 需先 browser_open。`elements` 返回的 `@e1` 引用可用于后续 click/type_text 的 `target` 参数 |

---

## 3. 页面交互操作

---

### browser_click

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.click()` / `BrowserController.click_selector()` |
| 用途 | 点击指定元素。支持两种模式：`selector`（CSS 选择器或 `@e1` ref）或 `text`（文本匹配） |
| 调用方式 | MCP `browser_click` / Python `agent.click(target, mode)` |
| 关键参数 | `target: str` — CSS 选择器 / `@e1` ref / 文本内容；`mode: str` — `"selector"`（默认）或 `"text"` |
| 返回值 | `{"ok": bool, "selector": str, "step": int}` 或 `{"clicked": bool, "text": str}` |
| 依赖 | 需先 browser_open。使用 `@e1` ref 需先调用 browser_snapshot |

---

### browser_type_text

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.type_text()` / `BrowserController.fill_input()` |
| 用途 | 在输入框中输入文本。支持 `@e1` ref 或 CSS 选择器定位 |
| 调用方式 | MCP `browser_type_text` / Python `agent.type_text(selector, text, clear)` |
| 关键参数 | `selector: str` — CSS 选择器或 `@e1` ref；`text: str` — 输入内容；`clear: bool` — 是否先清空（默认 true） |
| 返回值 | `{"ok": bool, "selector": str, "text": str, "step": int}` |
| 依赖 | 需先 browser_open |

---

### browser_press

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.press()` / `BrowserController.press_key()` |
| 用途 | 模拟键盘按键（Enter / Tab / Escape 等 Playwright 支持的按键名） |
| 调用方式 | MCP `browser_press` / Python `agent.press(key)` |
| 关键参数 | `key: str` — 按键名（默认 `"Enter"`） |
| 返回值 | `{"ok": bool, "key": str, "step": int}` |
| 依赖 | 需先 browser_open |

---

### browser_scroll

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.scroll()` / `BrowserController.scroll_page()` |
| 用途 | 按像素滚动页面（正数向下，负数向上） |
| 调用方式 | MCP `browser_scroll` / Python `agent.scroll(delta)` |
| 关键参数 | `delta: int` — 滚动像素（默认 500） |
| 返回值 | `{"ok": bool, "delta": int, "step": int}` |
| 依赖 | 需先 browser_open |

---

### browser_find

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.find()` |
| 用途 | 通过语义定位页面元素并执行操作。支持 5 种定位方式：text / label / placeholder / role / testid |
| 调用方式 | Python `agent.find(target_type, target, action, value)` |
| 关键参数 | `target_type: str` — 定位方式；`target: str` — 定位值；`action: str` — `"click"` 或 `"fill"`；`value: str` — 填充值 |
| 返回值 | `{"ok": bool, "action": str, "target_type": str, "target": str, "step": int}` |
| 依赖 | 需先 browser_open |

---

### browser_select

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.select()` |
| 用途 | 选择下拉框 `<select>` 的选项值 |
| 调用方式 | Python `agent.select(selector, value)` |
| 关键参数 | `selector: str` — CSS 选择器或 `@e1` ref；`value: str` — 选项 value |
| 返回值 | `{"ok": bool, "selector": str, "value": str, "step": int}` |
| 依赖 | 需先 browser_open |

---

### browser_wait

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.wait()` / `BrowserAgent.wait_load()` |
| 用途 | 等待指定元素出现（CSS 选择器），或等待固定时间（ms） |
| 调用方式 | Python `agent.wait(selector, timeout)` / `agent.wait_load(ms)` |
| 关键参数 | `selector: str` — CSS 选择器或 `@e1` ref；`timeout: int` — 超时 ms（默认 10000）；`ms: int` — 等待时长 |
| 返回值 | `{"found": bool, "selector": str}` 或 `{"ok": true, "waited_ms": int}` |
| 依赖 | 需先 browser_open |

---

### extract_table

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.extract_table()` |
| 用途 | 从表格/列表结构批量提取结构化数据。指定行选择器和列映射，JS 端一次性提取 |
| 调用方式 | Python `agent.extract_table(rows_selector, columns, limit)` |
| 关键参数 | `rows_selector: str` — 每行对应的 CSS 选择器；`columns: dict[str,str]` — 列名→列内选择器映射；`limit: int` — 最大行数（默认 30） |
| 返回值 | `{"total": int, "returned": int, "results": list[dict], "step": int}` |
| 依赖 | 需先 browser_open 并导航到含列表结构的页面 |

---

### loop_extract

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.loop_extract()` |
| 用途 | 翻页批量提取。自动点击"下一页"按钮，跨页聚合所有结果 |
| 调用方式 | Python `agent.loop_extract(page_count, row_selector, columns, next_btn)` |
| 关键参数 | `page_count: int` — 最多翻页数；`row_selector: str` — 行选择器；`columns: dict` — 列映射；`next_btn: str` — 下一页按钮 CSS 选择器 |
| 返回值 | `{"pages": int, "total_rows": int, "results": list[dict], "step": int}` |
| 依赖 | 需先 browser_open。列表页需有 "下一页" 按钮 |

---

### execute_js

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.execute_js()` / `BrowserController.execute_js()` |
| 用途 | 在页面中执行任意 JavaScript 表达式，返回执行结果 |
| 调用方式 | Python `agent.execute_js(expression)` |
| 关键参数 | `expression: str` — 任意 JS 表达式（如 `"document.title"`） |
| 返回值 | `{"result": any}` 或 `{"error": str}` |
| 依赖 | 需先 browser_open |

---

## 4. 反检测与行为模拟

---

### STEALTH_SCRIPT 注入

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/anti_detect.py` → `STEALTH_SCRIPT`（第 159~351 行） |
| 用途 | 页面加载时注入综合隐身脚本，16 项检测点全覆盖。通过 `context.add_init_script()` 在每次页面初始化时自动执行 |
| 覆盖检测点 | `navigator.webdriver` → false；Canvas 指纹 → ±0.25 噪声；插件列表 → 3 个真实插件；语言 → zh-CN；平台 → Win32；WebRTC → stun:0.0.0.0；屏幕 → 1920×1080；时区 → Asia/Shanghai；硬件并发 → 8；设备内存 → 8GB；网络类型 → 4g；Chrome runtime → 模拟 |
| 调用方式 | 自动注入（`scraper.py` 中 `context.add_init_script(STEALTH_SCRIPT)`） |
| 关键参数 | 无（自动执行） |
| 返回值 | 无（无感注入） |
| 依赖 | 需在浏览器 context 创建时注入 |

---

### ANTI_REDIRECT_SCRIPT 注入

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/anti_detect.py` → `ANTI_REDIRECT_SCRIPT`（第 91~156 行） |
| 用途 | 拦截所有 `about:blank` / `about:blank#blocked` 反爬重定向。拦截 `location.href` setter、`location.assign()`、`location.replace()`、`window.open()`，并通过 MutationObserver 自动恢复被强制跳转的页面 |
| 调用方式 | 自动注入（`scraper.py` 中 `context.add_init_script(ANTI_REDIRECT_SCRIPT)`） |
| 关键参数 | 无（自动执行） |
| 返回值 | 无（无感注入） |
| 依赖 | 需在浏览器 context 创建时注入 |

---

### BROWSER_STEALTH_ARGS

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/anti_detect.py` → `BROWSER_STEALTH_ARGS`（第 9~18 行） |
| 用途 | Playwright 启动参数集合：禁用 `AutomationControlled` Blink 特性、禁用 WebGL 和 Canvas AA、固定窗口 1400×900、中文语言 |
| 调用方式 | Playwright 路径自动应用；Camoufox 路径不使用此参数（引擎自身处理） |
| 关键参数 | 7 条 Chrome 启动参数 |
| 返回值 | 无（添加到 launch 配置） |
| 依赖 | 仅 Playwright 回退路径生效 |

---

### Camoufox 双引擎回退

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/browser.py` → `BrowserController.start()`（第 92~115 行） |
| 用途 | 优先启动 Camoufox（C++ 反检测引擎），失败时自动回退到 Playwright（JS 注入方案） |
| 调用方式 | 自动（`start()` 方法内部逻辑） |
| 关键参数 | `headless: bool`; `use_camoufox: bool`（默认 true）；Camoufox 特有参数：`humanize=True`, `geoip=True`, `block_images=False` |
| 返回值 | Camoufox 路径：注入已保存 Cookie 并跳过登录；Playwright 路径：启动持久化上下文（`browser_profile/`） |
| 依赖 | `camoufox` 库安装检测在模块加载时完成，`HAS_CAMOUFOX` 全局变量 |

---

### human_scroll

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/anti_detect.py` → `human_scroll(page)`（第 57~62 行） |
| 用途 | 模拟人类分段滚动：3~6 次，每次 300~800px，步间 0.5~1.5 秒随机 |
| 调用方式 | Python `await human_scroll(page)` |
| 关键参数 | 无（参数在函数内部随机化） |
| 返回值 | 无 |
| 依赖 | 需 Playwright Page 对象 |

---

### human_click

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/anti_detect.py` → `human_click(page, element)`（第 65~80 行） |
| 用途 | 拟人化点击：读取元素 bounding box → 3~6 步线性插值移动鼠标（每步 30~80ms，±3px 噪声）→ 最后调用 `element.click()` |
| 调用方式 | Python `await human_click(page, element)` |
| 关键参数 | `page: Page`; `element: ElementHandle` |
| 返回值 | 无 |
| 依赖 | 需 Playwright Page 和 ElementHandle |

---

### random_delay

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/anti_detect.py` → `random_delay(delay_range)`（第 48~54 行） |
| 用途 | 每次操作后随机等待。默认范围 2~5 秒，可通过 `delay_range` 覆盖 |
| 调用方式 | Python `await random_delay((min, max))` |
| 关键参数 | `delay_range: tuple[int,int] \| None` — 秒数范围 |
| 返回值 | 无（`asyncio.sleep`） |
| 依赖 | 无 |

---

### random_viewport

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/anti_detect.py` → `random_viewport()`（第 83~88 行） |
| 用途 | 每次启动生成随机窗口尺寸：宽度 1200~1600，高度 800~1000 |
| 调用方式 | Python `kwargs["viewport"] = random_viewport()` |
| 关键参数 | 无 |
| 返回值 | `{"width": int, "height": int}` |
| 依赖 | 需在 `build_browser_kwargs` 中覆盖默认值 |

---

### Fingerprint Manager

| 字段 | 内容 |
|------|------|
| 所属模块 | `shared/fingerprint_manager.py` → `generate_camoufox_opts()` |
| 用途 | Camoufox 路径的指纹随机化：从 8 种常见分辨率中随机选窗口尺寸；操作系统按权重（Win:Mac:Linux = 14:3:1）；屏幕尺寸在窗口基础上 +0~400/+20~200 二次偏移 |
| 调用方式 | Python `generate_camoufox_opts()` → 解包传给 `AsyncCamoufox(**opts)` |
| 关键参数 | 无（内置 8 组预设） |
| 返回值 | `{"window": (w,h), "os": [str], "screen": {...}}` |
| 依赖 | 仅 Camoufox 路径生效 |

---

## 5. 页面分析与调试

---

### browser_screenshot

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/agent.py` → `BrowserAgent.screenshot()` / `BrowserController.get_page_screenshot_bytes()` |
| 用途 | 截取当前页面截图，返回 PNG 格式的 base64 编码（含 `data:image/png` URI） |
| 调用方式 | MCP `browser_screenshot` / Python `agent.screenshot(full_page)` |
| 关键参数 | `full_page: bool` — 是否截取全页（默认 false） |
| 返回值 | `{"ok": bool, "format": "png", "base64": str, "data_uri": str}` |
| 依赖 | 需先 browser_open |

---

### capture_screenshot (本地文件)

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/page.py` → `capture_screenshot(page, name)` |
| 用途 | 截取全页截图保存为本地文件（`data/screenshots/{name}_{timestamp}.png`） |
| 调用方式 | Python `capture_screenshot(page, name)` |
| 关键参数 | `page: Page`; `name: str` — 文件名标识 |
| 返回值 | `str \| None` — 文件路径 |
| 依赖 | 需 Playwright Page 对象 |

---

### capture_html_snapshot

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/page.py` → `capture_html_snapshot(page, max_len)` |
| 用途 | 获取页面 HTML 源码快照，超长时截断（保留头尾各一半） |
| 调用方式 | Python `capture_html_snapshot(page, max_len)` |
| 关键参数 | `page: Page`; `max_len: int` — 最大字符数（默认 50000） |
| 返回值 | `str \| None` — HTML 源码 |
| 依赖 | 需 Playwright Page 对象 |

---

### get_dom_structure

| 字段 | 内容 |
|------|------|
| 所属模块 | `agent/core/browser.py` → `BrowserController.get_dom_structure()` |
| 用途 | 获取页面 DOM 结构摘要：`<body>` 存在性、正文长度、可选选择器匹配数量。支持通过 `selectors` 参数注入业务选择器列表 |
| 调用方式 | Python `ctrl.get_dom_structure(selectors)` |
| 关键参数 | `selectors: list[str] \| None` — 要统计的 CSS 选择器列表 |
| 返回值 | `{"has_body": bool, "body_len": int, "<selector>": count, ...}` |
| 依赖 | 需先 browser_open |

---

### 验证码/反爬检测链

| 字段 | 内容 |
|------|------|
| 所属模块 | `modes/zhipin/page_analyzer.py` → `_detect_captcha_elements()` + `analyze_page()` + `quick_check()` |
| 用途 | 三层检测：CSS 选择器查 `CAPTCHA_INDICATORS` → 文本关键词匹配（"安全验证""滑块验证"等）→ URL 分析判页面类型 |
| 调用方式 | 由 `scraper.py` 在采集过程中自动调用 |
| 关键参数 | 见 `modes/zhipin/selectors.py` 中 `CAPTCHA_INDICATORS`（6 个选择器）和 `CAPTCHA_KEYWORDS`（6 个关键词） |
| 返回值 | `analyze_page()` 返回 `PageAnalysis` 对象（含 `issues: list[str]` 和 `has_issues: bool`）；`quick_check()` 返回 `{"issues": list, "page_type": str}` |
| 依赖 | 需 Playwright Page 对象和业务选择器配置 |

---

## 能力统计

| 类别 | 数量 |
|------|------|
| 1. 浏览器生命周期管理 | 7 项 |
| 2. 页面导航与信息获取 | 5 项 |
| 3. 页面交互操作 | 8 项 |
| 4. 反检测与行为模拟 | 10 项 |
| 5. 页面分析与调试 | 5 项 |
| **合计** | **35 项** |
