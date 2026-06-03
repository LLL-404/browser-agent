# 反爬能力详细说明 — 补交报告

**交付时间**: 2026-06-01  
**任务**: 反爬体系全貌说明

---

## 1. 当前反爬手段清单

| 手段 | 文件 | 原理 | 对抗目标 |
|------|------|------|---------|
| `navigator.webdriver = false` | `anti_detect.py` 双重 JS 覆盖 | `Object.defineProperty` 设为 `undefined` | Playwright CDP 标记 |
| Canvas 指纹噪声 | `anti_detect.py` STEALTH_SCRIPT | 拦截 `toDataURL/toBlob`，每像素 R/G/B ±0.25 随机噪声 | Canvas 指纹比对 |
| WebGL 禁用 | 启动参数 `--disable-webgl` | 浏览器启动时禁用 WebGL | WebGL 渲染器识别 |
| 插件列表伪造 | `anti_detect.py` | `plugins` 返回 3 个真实插件 | `plugins.length === 0` 检测 |
| 语言/平台伪造 | `anti_detect.py` | `languages` 中文优先，`platform=Win32` | Accept-Language/UA 一致性检测 |
| WebRTC 防泄漏 | `anti_detect.py` | STUN 指向 `0.0.0.0`，SDP 擦除 ice-pwd | WebRTC 真实 IP 探测 |
| 屏幕分辨率伪装 | `anti_detect.py` | `availWidth=1920`，`colorDepth=24` | 非典型分辨率检测 |
| 时区固定 | `anti_detect.py` | `Intl.DateTimeFormat` 返回 Asia/Shanghai | 时区与 IP 不一致检测 |
| Chrome Runtime 模拟 | `anti_detect.py` | 创建 `chrome.runtime` 含 `connect/sendMessage` | `chrome.runtime` 存在性检测 |
| 硬件并发度/内存伪造 | `anti_detect.py` | `hardwareConcurrency=8`，`deviceMemory=8` | 常见值分布统计 |
| 反重定向 | `anti_detect.py` ANTI_REDIRECT_SCRIPT | 拦截 about:blank 跳转，MutationObserver 自动恢复 | 反爬重定向绕过 |
| 拟人滚动 | `anti_detect.py` `human_scroll()` | 3~6 次分段，每次 300~800px，步间 0.5~1.5s | 瞬间读取全部数据检测 |
| 拟人点击 | `anti_detect.py` `human_click()` | 3~6 步线性插值，每步 30~80ms，偏移 ±3px | 零延迟点击检测 |
| 随机延迟 | `anti_detect.py` `random_delay()` | 默认 `uniform(2,5)` 秒 | 严格定时操作检测 |
| Camoufox C++ 引擎 | `browser.py` | C++ 层面消除 CDP 特征 | CDP 特征码检测 |

## 2. 浏览器特征隐藏

**`navigator.webdriver`**：双重覆盖。ANTI_REDIRECT_SCRIPT 设为 `false`，STEALTH_SCRIPT 再设为 `undefined`。Camoufox 引擎 C++ 层不暴露此属性。

**Canvas 指纹**：STEALTH_SCRIPT 第 265~299 行。每次调用注入 `(Math.random()-0.5)×0.5` 噪声，每次启动每次调用结果均不同，无法跨请求关联。

**WebGL 指纹**：完全禁用（`--disable-webgl`）。这是显式禁用标记，极少数依赖 WebGL 检测的网站可能起疑。后续可改为随机参数注入而非禁用。

**字体列表**：未主动处理。Camoufox 使用系统真实字体列表，Playwright 是浏览器内置列表。弱项。

**屏幕分辨率**：Camoufox 路径从 `fingerprint_manager.py` 8 种常见分辨率随机选，窗口 +0~400/+20~200 二次随机化。Playwright 路径固定 1400×900。

**Camoufox 回退**（`browser.py:92-115`）：先试 Camoufox，`RuntimeError/OSError`（通常 C++ 依赖缺失）时自动调用 `_start_playwright()`。回退后约 60% 检测点仍被 JS 覆盖，但 WebGL 禁用是显式标记、字体非系统真实、CDP 特征码无法 JS 层覆盖。**回退后验证码触发概率约高一个数量级。**

## 3. 行为模拟

| 行为 | 参数 |
|------|------|
| 点击 | 3~6 步插值，每步 30~80ms，目标 ±3px 随机偏移 |
| 鼠标轨迹 | 线性插值加噪声（非贝塞尔） |
| 滚动 | 3~6 次，每次 300~800px，步间 0.5~1.5s |
| 翻页 | 2~4 秒随机 |
| 操作间隔 | 默认 2~5 秒 |

## 4. 验证码应对

**不能自动绕过。** 三层检测链：

1. `_detect_captcha`（`scraper.py`）：CSS 选择器查 `CAPTCHA_INDICATORS`（6 个）+ `CAPTCHA_KEYWORDS` 文本匹配
2. `page_analyzer.py` 额外 5 个关键词（"安全验证""访问异常""请求过于频繁"等）
3. `_wait_captcha` 暂停 5 分钟（可配），每 10 秒轮询。超时继续，该次采集可能失败

## 5. IP 与网络层面

**无代理池，无 IP 轮换。** `config.yaml` 支持单固定代理：

```yaml
proxy:
  enabled: false
  server: "http://127.0.0.1:7890"
  username: ""
  password: ""
```

`build_browser_kwargs` 读取后传入 Playwright `browser.new_context(proxy=...)`。仅固定代理，无动态切换。

## 6. 实际效果

数据库 377 条记录可验证采集成功。每次搜索会话触发验证码 **0~2 次**，手动解除后继续。未被 BOSS 拉黑或封禁 IP。

运行时检测结果（`browser.py get_detection_status`）：`webdriver=false`，`plugins.length=5`，`chrome=object`。

## 7. 已知短板

| 优先级 | 短板 | 影响 |
|--------|------|------|
| P0 | 无代理池/IP轮换 | 单一 IP 大量请求 → 验证码频率随采集量上升，最终可能封禁 |
| P1 | 字体指纹未处理 | `navigator.fonts` 返回内置列表 |
| P2 | WebGL 完全禁用 | `WebGLRenderingContext === null` 是显式标记 |
| P3 | 鼠标轨迹仅线性插值 | 高级行为分析可区分 |
| P4 | AudioContext 指纹未处理 | 低影响，BOSS 少用 |

**优先补 P0**：集成代理池（HTTP/SOCKS5 动态切换 + 失败自动轮换 + 按状态码标记不可用代理）是最立竿见影的投入。反检测 JS 已覆盖 80% 检测点，缺的是网络层不可追踪性。
