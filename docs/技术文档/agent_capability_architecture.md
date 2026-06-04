# 浏览器 Agent 能力架构设计说明

## 一、能力的静态结构 —— 分层模型

### 1.1 严格的三层依赖关系

35 项能力之间**不是平行的五大类，而是严格的三层金字塔**。五大类（生命周期、导航与信息获取、页面交互、反检测、分析与调试）在架构上分属三个层次：

```
                    ┌──────────────────────────────────────┐
  第3层              │         组合能力层                   │
  (编排)             │  loop_extract / extract_table       │
                    │  save_session / load_session         │
                    │  browser_snapshot                    │
                    │  browser_find                        │
                    └──────────────┬───────────────────────┘
                                   │ 调用 1 个或多个原子能力
                                   ▼
                    ┌──────────────────────────────────────┐
  第2层              │         原子能力层                   │
  (基础操作)          │  navigate / click / type_text /     │
                    │  press / scroll / select / wait      │
                    │  execute_js / url / text / html      │
                    └──────────────┬───────────────────────┘
                                   │ 依赖浏览器引擎
                                   ▼
                    ┌──────────────────────────────────────┐
  第1层              │         浏览器引擎层                 │
  (基础设施)          │  browser_open / browser_close       │
                    │  save_cookies / load_cookies         │
                    │  screenshot / get_page_text / ...    │
                    └──────────────────────────────────────┘
```

**反检测不是一层，而是一个贯穿各层的切面（Aspect）**：

```
  组合能力层  ──→  每次调用原子能力前/后，随机延迟（random_delay）
  原子能力层  ──→  click/scroll 内部调用 human_click/human_scroll
  浏览器引擎层 ──→  STEALTH_SCRIPT / ANTI_REDIRECT 在 Context 创建时注入
                    Camoufox 从 C++ 层覆盖 16 个检测点
          反检测切面（横切关注点，非独立层次）
```

这意味着：
- **第 1 层不依赖第 2 层**，但第 2 层依赖第 1 层
- **第 3 层不依赖第 2 层的实现细节**，只依赖其接口
- **反检测代码不重复**——它在三个入口位置（context 初始化、单次操作封装、跨操作调度）被织入，而不是在每个能力中复制

### 1.2 原子能力 vs 组合能力

**原子能力**（7 项）——不可再分，直接封装 Playwright API：

| 能力 | 为何不可再分 | 封装层级 |
|------|------------|---------|
| `browser_open` | 启动浏览器进程是 OS 级操作，无法用其他能力组合实现 | BrowserController |
| `browser_close` | 关闭进程同上 | BrowserController |
| `navigate_to` | `page.goto()` 是 Playwright 单次网络请求 | BrowserController |
| `click_selector` | 单次 DOM 点击，封装异常分支处理 | BrowserController |
| `fill_input` | 输入框填充，封装异常分支处理 | BrowserController |
| `press_key` | 键盘事件模拟，Playwright 单次调用 | BrowserController |
| `execute_js` | JS 求值，Playwright 单次调用 | BrowserController |

**组合能力**（5 项）——由 2 项以上原子能力编排而成：

| 能力 | 编排过程 | 涉及的原子能力 |
|------|---------|--------------|
| `loop_extract` | 翻页循环：提取当前页数据 → 点击下一页 → 等待加载 → 继续提取 | `extract_table` + `click_selector` + `wait` |
| `save_session` | 读出 Cookie + localStorage → 序列化 → 写入文件 | `save_cookies` + `save_local_storage` |
| `load_session` | 读取文件 → 反序列化 → 写入 Cookie + localStorage → 导航回原页面 | `load_cookies` + `load_local_storage` + `navigate_to` |
| `browser_snapshot` | 获取可交互元素 → 构建 DOM 摘要 → 获取文本摘要 → 三合一 | `get_interactive_elements` + `get_dom_structure` + `get_page_text` |
| `browser_find` | 按语义查找元素 → 定位成功 → 执行点击/填充 | Playwright `get_by_text/label/role/placeholder/testid` + `click`/`fill` |

---

## 二、能力的动态编排 —— 使用流水线

### 2.1 通用自动化流水线

所有自动化任务背后共享一个隐式的 6 阶段流水线：

```
Phase 1          Phase 2          Phase 3          Phase 4
启动浏览器  ──→  恢复会话   ──→  反检测注入  ──→  导航到目标
browser_open    load_session    (自动)           navigate
                                      ↑
                          STEALTH_SCRIPT 在 context.add_init_script 注入
                          每次 new_page 自动执行，phase 无关

Phase 5                    Phase 6
页面交互/数据提取  ──→  结果处理/关闭
click / extract_table    save_session / browser_close
scroll / type_text
```

这个流水线的关键特征：
- **Phase 1-3 是固定前摇**，任何任务都必须经过（启动 → 恢复 → 反检测）
- **Phase 4-5 是任务特定部分**，不同任务在此分支
- **Phase 6 是固定收尾**，任何任务最终都会落在这里
- **反检测不固定在 Phase 3**，它在 Phase 3 注入 JS，在 Phase 5 的操作中生效

### 2.2 BOSS 搜索流水线（具体实例）

以 `search_jobs` 为例，流水线实例化：

```
Phase 1: browser_open(headless=False)
Phase 3: STEALTH_SCRIPT + ANTI_REDIRECT_SCRIPT 自动注入
Phase 4: navigate("https://www.zhipin.com/")
         ↓ 检测登录态（is_logged_in）
         ↓ 未登录 → 等待手动登录（wait_for_login）
Phase 5: 对每个城市×关键词：
           navigate(search_url)
           wait_for_selector(JOB_CARD)
           extract_table → 列表页提取
           click(NEXT_PAGE) × max_pages → loop_extract
Phase 6: generate_report / 数据入库
```

这个流水线中，**循环嵌套的结构**（城市 → 关键词 → 翻页）是业务逻辑，**每个矩形操作**（navigate / wait / extract / click）是能力的实例化。

### 2.3 `loop_extract` 的模块化复用的体现

`loop_extract` 是组合能力复用原子能力的最佳例证：

```python
async def loop_extract(self, page_count, row_selector, columns, next_btn):
    for pg in range(page_count):                    # 控制逻辑
        data = await self.extract_table(...)         # 复用组合能力
        if pg < page_count - 1 and next_btn:
            clicked = await self._ctrl.click_selector(next_btn)  # 复用原子能力
            if not clicked: break
            await asyncio.sleep(2)                   # 固定延迟，非随机
```

它复用了：
- `extract_table`（组合能力）—— 负责单页结构化提取
- `click_selector`（原子能力）—— 负责翻页点击
- 自己没有实现任何 Playwright API 调用

如果要新增一个类似 `loop_extract` 的能力（如 `loop_detail` 逐条进详情页抓取），只需将 `extract_table` 替换为 `navigate` + `get_page_text` 的组合，**复用模式完全相同**。

---

## 三、能力的规律性 —— 统一设计模式

### 3.1 函数签名统一范式

所有能力遵循**两种签名模式**之一：

**模式 A：控制器模式（BrowserController 层）**
```python
async def action_name(self, param1: type, param2: type, ...) -> bool | dict:
    # 1. 状态检查（_require_page）
    # 2. try: Playwright 调用
    # 3. except: 异常分类 → 日志 → 返回 false/空
    # 4. finally: 不抛异常到上层
```

示例：`click_selector`、`fill_input`、`press_key`、`scroll_page` 均此模式。返回值统一为 `bool`（成功/失败），调用方不需要 try/except。

**模式 B：Agent 模式（BrowserAgent 层）**
```python
async def action_name(self, ..., ) -> dict[str, Any]:
    self._step_count += 1
    # 参数解析（ref 解析、默认值）
    # 调用 controller 方法
    # 返回 dict 含 "ok"、"step" 和业务字段
```

所有 Agent 方法的返回值**始终为 `dict`**，始终包含 `"ok": bool` 和 `"step": int`。这保证了：
- MCP JSON 序列化无歧义
- 调用方可通过 `"ok"` 判断成败
- `"step"` 支持断点续传（记录已执行的步骤数）

### 3.2 元素定位统一规范

所有与页面元素交互的能力，遵循**两级定位链**：

```
            ┌── 语义定位（第 1 优先）
            │   例：click("登录", mode="text")
            │       find("text", "登录", "click")
            │
参数传入 ──→ ├── @e1 引用定位（第 2 优先）
            │   例：click("@e3")
            │       type_text("@e5", "Hello")
            │       wait("@e3")
            │   @e1~eN 由 browser_snapshot 生成，无需记忆 CSS 选择器
            │
            └── CSS 选择器定位（兜底）
                例：click(".job-name")
                    type_text("#search-input", "普工")
```

**任何交互能力**（click / type_text / wait / select / find）都遵守这个两级定位链。新增一个交互能力时，只需套用这个参数模式。

### 3.3 扩展性验证 —— 以「拖拽」为例

假设要新增一个 `drag_and_drop` 能力，按现有设计规律推导：

**所属层次**：第 2 层（原子能力层），因为它是单次 DOM 操作，不可再分。

**所属类别**：页面交互操作（与 click 同级）。

**调用模式**：遵循模式 A（Controller 层）+ 模式 B（Agent 层）两层封装。

**Controller 层签名**（已有 Playwright `page.drag_and_drop` 封装）：
```python
async def drag_and_drop(self, source: str, target: str) -> bool:
    # 复用 find_selector 做元素存在检查
    # 调用 page.drag_and_drop(source_sel, target_sel)
    # 保持统一错误处理：try/except → 分类 → 日志 → false
```

**Agent 层签名**：
```python
async def drag(self, source: str, target: str) -> dict[str, Any]:
    self._step_count += 1
    source_sel = self._resolve_ref(source) or source  # 复用 ref 定位链
    target_sel = self._resolve_ref(target) or target
    ok = await self._ctrl.drag_and_drop(source_sel, target_sel)
    return {"ok": ok, "source": source_sel, "target": target_sel,
            "step": self._step_count}
```

**参数规律**：`source` 和 `target` 都支持 `@e1` / CSS 选择器，与 click 的参数格式一致。不需要新增定位方式。

**返回值规律**：`{"ok": bool, "source": str, "target": str, "step": int}`，含 `ok` + `step`，与所有 Agent 方法一致。

**组合复用**：无人会调用 `drag_and_drop` 本身——它会内嵌在组合能力中，例如"登录页拖滑块验证"：
```python
async def solve_slider_captcha(self):
    await self.drag("@slider_knob", "@slider_end")  # 复用新原子能力
    await self.wait_load(1000)                       # 复用已有组合能力
    return await self.snapshot()                     # 复用已有组合能力
```

**结论**：新增拖拽能力，不改变现有架构、不引入新参数模式、不修改返回值规范、不需要新异常类型。只需在 `BrowserController` 加一个方法，`BrowserAgent` 加一个方法，`agent/mcp/server.py` 的 `_collect_all_tools` 加一行注册。**这就是"有规律可循"的证明。**

---

## 四、总结

| 维度 | 设计结论 |
|------|---------|
| 静态结构 | 三层金字塔（引擎层 → 原子能力层 → 组合能力层）+ 反检测是横切面 |
| 元素定位 | 统一两级链：语义定位 → @e1 ref → CSS 选择器 |
| 函数签名 | 两层封装（Controller 返回 bool，Agent 返回 dict<ok,step>） |
| 异常处理 | Playwright 异常永不外抛，全部在 Controller 层分类+日志+转 false |
| 反检测织入 | 三入口（context 初始化 + 单操作封装 + 跨操作调度），不重复代码 |
| 新增一项能力 | 只需加一个 Controller 方法 + 一个 Agent 方法 + 一行 MCP 注册 |
