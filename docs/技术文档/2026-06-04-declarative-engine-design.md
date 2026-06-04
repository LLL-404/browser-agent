# 全链路声明式重构设计文档

> 日期: 2026-06-04
> 状态: 待审核
> 目标: 将硬编码的业务逻辑从代码中解耦，迁移到 YAML 声明式配置，实现"改需求 = 改配置"

## 1. 问题诊断

### 1.1 当前痛点

当前 `modes/zhipin/` 目录下的代码存在严重的**策略与流程耦合**：

| 文件 | 硬编码内容 | 变更成本 |
|------|-----------|---------|
| `selectors.py` | BOSS 直聘 DOM CSS 选择器 | BOSS 改版 → 改代码 |
| `pre_filter.py` | 过滤逻辑顺序（薪资→标题黑名单→公司→活跃度） | 加/删/调序过滤条件 → 改代码 |
| `scraper.py` (668行) | 搜索 URL 模式、翻页逻辑、详情提取、报告格式 | 换评估维度/改报告 → 改代码 |
| `config.yaml` | 部分可配置，但大量规则藏在代码里 | 不完整 |

**核心问题**: 配置和代码混在一起，策略写死在流程里。类似 CLI 工具的"命令驱动"理念——用户告诉系统**做什么**（配置），系统自己决定**怎么做**（引擎），而不是把每一步都硬编码。

### 1.2 设计目标

- **90% 的需求变更只需改 YAML**：加过滤条件、换选择器、改报告维度
- **引擎代码极薄且通用**：不包含任何站点特有业务逻辑
- **加新网站 ≈ 写一份 profile + 偶尔补 adapter**：不用重写爬虫
- **向后兼容**：现有功能不退化

---

## 2. 方案概述：混合模式（配置驱动 + 极简适配器）

### 2.1 架构分层

```
┌──────────────────────────────────────────────────┐
│                   用户层                          │
│   CLI 命令 / API 调用 / 定时任务                  │
├──────────────────────────────────────────────────┤
│                 站点画像层 (YAML)                  │
│   profiles/zhipin.yaml                           │
│   ├── meta / navigation / urls                   │
│   ├── dom (所有选择器)                            │
│   ├── filters (过滤规则链)                        │
│   └── report (报告维度)                           │
├──────────────────────────────────────────────────┤
│                  引擎执行层 (Python)               │
│   shared/engine/                                 │
│   ├── ScrapingEngine   — 流程编排 (~150 行)       │
│   ├── FilterChain      — 过滤规则解释器            │
│   ├── DomReader        — DOM 读取器               │
│   ├── UrlBuilder       — URL 模板构建              │
│   ├── ReportBuilder    — 动态报告生成              │
│   └── AdapterProtocol  — 可选适配器接口            │
├──────────────────────────────────────────────────┤
│                适配器层 (可选)                     │
│   modes/zhipin/adapter.py — 仅处理 YAML 无法表达的逻辑 │
└──────────────────────────────────────────────────┘
```

### 2.2 数据流

```
Profile YAML → ScrapingEngine
                ├─→ UrlBuilder.build_search(city, kw)
                ├─→ DomReader.collect_cards(page)
                ├─→ DomReader.parse_card(card)
                ├─→ FilterChain.evaluate(job)
                │     ├─ SalaryThresholdFilter.check()
                │     ├─ ContainsAnyFilter.check()
                │     └─ InactiveDaysFilter.check()
                ├─→ DomReader.scrape_detail(page, url)
                ├─→ Storage.insert(job)
                └─→ ReportBuilder.generate(jobs)
```

---

## 3. 详细设计

### 3.1 站点画像 (SiteProfile)

配置文件路径: `profiles/zhipin.yaml`

```yaml
meta:
  name: zhipin
  display_name: "BOSS 直聘"
  version: 2

navigation:
  home: "https://www.zhipin.com/?ka=header-home"
  login: "https://www.zhipin.com/web/user/?ka=header-login"

urls:
  search:
    - template: "/web/geek/job?city={city_code}&query={keyword}"
      priority: 1
    - template: "/job_detail/?query={keyword}&city={city_code}"
      priority: 2

dom:
  list:
    card: "li.job-card-box, li.search-job-item, .job-list li"
    title: ".job-name, .job-title, [class*='job-name']"
    title_link: "a.job-name, a.job-title, .job-name a"
    company: ".boss-name, .company-name, [class*='company-name']"
    salary: ".job-salary, .salary, [class*='salary']"
    tags: ".tag-list li, .job-tags li, [class*='tag']"

  pagination:
    next_button: ".options-pages .next, .page-next, button.next"
    disabled_class_contains: "disabled"

  detail:
    description:
      - ".job-sec-text"
      - ".job-detail-section-text"
      - ".job-detail-content"
      - "[class*='job-detail']"
    company:
      - ".company-info"
      - ".detail-business-info"
      - "[class*='company-info']"
    recruiter_active:
      - ".boss-active-time"
      - "[class*='active-time']"
    panel_salary: ".job-detail-box .job-detail-salary, [class*='salary']"

  captcha:
    indicators:
      - ".geetest_panel"
      - ".captcha-box"
      - "iframe[src*='captcha']"
    keywords: ["验证码", "安全验证", "滑块验证"]

  login:
    user_menu: ".nav-user-menu, .user-avatar"
    page_auth_patterns: ["/user/", "passport", "login"]
    text_positive: ["欢迎回来", "退出登录"]
    text_negative: ["登录", "注册", "扫码"]

filters:
  - id: min_salary
    type: salary_threshold
    field: salary
    config_key: pre_filters.min_salary
    reason_template: "薪资 {value} 低于 {threshold}"

  - id: title_blacklist
    type: contains_any
    field: title
    case_insensitive: true
    source: pre_filters.title_blacklist
    reason_template: "标题含 '{matched}'"

  - id: company_blacklist
    type: contains_any
    field: company
    case_insensitive: true
    source: pre_filters.company_blacklist
    reason_template: "公司类型含 '{matched}'"

  - id: recruiter_inactive
    type: inactive_days
    field: recruiter_active
    max_days_key: runtime.max_inactive_days
    reason_template: "招聘者已 {value} 天未活跃"

report:
  score_threshold: 6
  dimensions:
    - key: five_insurance
      label: 五险一金
    - key: room_board
      label: 包食宿
    - key: regular_hours
      label: 朝九晚五/双休
```

### 3.2 通用引擎 (ScrapingEngine)

文件: `shared/engine/scraping_engine.py`

职责: 流程编排，不含任何业务逻辑。所有行为参数来自 SiteProfile。

核心方法:
- `run(cities, keywords)` — 主入口
- `_navigate_home(page)` — 导航首页
- `_ensure_login(page)` — 登录检测与等待
- `_search_city(page, city, keywords)` — 单城市搜索循环
- `_launch()` — 浏览器启动与反检测初始化

预期代码量: ~150 行（当前 scraper.py 668 行）

### 3.3 过滤链 (FilterChain)

文件: `shared/engine/filter_chain.py`

职责: 解释执行 Profile 中声明的过滤器规则列表。

内置规则类型:

| 类型 | 说明 | 参数 |
|------|------|------|
| `salary_threshold` | 薪资下限过滤 | field, config_key |
| `contains_any` | 黑名单关键词匹配 | field, source, case_insensitive |
| `inactive_days` | 招聘者活跃度过滤 | field, max_days_key |

扩展新规则类型:
1. 实现 `BaseFilter` 接口（`check(job) -> tuple[bool, str]`）
2. 在 `FilterChain._RULE_TYPES` 注册

### 3.4 DOM 读取器 (DomReader)

文件: `shared/engine/dom_reader.py`

职责: 所有 DOM 操作的选择器来自 Profile.dom 配置。

核心方法:
- `collect_cards(page)` — 用 `dom.list.card` 选择卡片
- `parse_card(card, page)` — 用 `dom.list.*` 解析单张卡片字段
- `scrape_detail(page, url)` — 用 `dom.detail.*` 提取详情（fallback 链）
- `_try_selectors(page, selector_list)` — 按顺序尝试选择器列表直到命中

### 3.5 URL 构建器 (UrlBuilder)

文件: `shared/engine/url_builder.py`

职责: 从 Profile.urls 模板构建实际 URL。

特性:
- 支持多模板 + 优先级（v1 失败自动 fallback 到 v2）
- 模板变量: `{city_code}`, `{keyword}`, `{city}`

### 3.6 报告生成器 (ReportBuilder)

文件: `shared/engine/report_builder.py`

职责: 报告内容和格式完全由 Profile.report 驱动。

- 维度列表来自 `report.dimensions`
- 分数阈值来自 `report.score_threshold`
- 加维度只改配置，不改代码

### 3.7 适配器协议 (AdapterProtocol)

文件: `shared/engine/adapter_protocol.py`

职责: 处理 YAML 无法表达的特殊解析逻辑（预计 < 10% 场景需要）。

```python
class SiteAdapter(Protocol):
    """可选适配器。大多数场景不需要实现。"""
    def parse_salary(self, text: str) -> int | None: ...
    def parse_inactive_days(self, text: str) -> int | None: ...

class DefaultAdapter:
    """默认适配器 — 内置通用解析逻辑（覆盖 80% 场景）。"""
    # 薪资解析: "4K-6K" → 4000, "3000-5000元/月" → 3000
    # 活跃时间: "3天前" → 3, "刚刚" → 0
```

BOSS 直聘特有适配器 (`modes/zhipin/adapter.py`):
- 继承 `DefaultAdapter`
- 大多数情况下直接用默认实现即可
- 只在 BOSS 有特殊数据格式时覆盖对应方法

---

## 4. 目录结构变化

### 4.1 新增

```
src/
├── profiles/                      # 站点画像（新增）
│   └── zhipin.yaml
│
├── shared/
│   └── engine/                    # 通用引擎（新增）
│       ├── __init__.py
│       ├── scraping_engine.py     # ~150 行
│       ├── filter_chain.py
│       ├── dom_reader.py
│       ├── url_builder.py
│       ├── report_builder.py
│       └── adapter_protocol.py
```

### 4.2 精简

```
src/modes/zhipin/                  # 从 ~10 个文件精简为 ~2 个
├── __init__.py                    # 入口转发（精简）
├── adapter.py                     # 可选适配器（通常 < 50 行）
├── city_codes.py                  # 保留（城市代码映射）
├── keyword_strategy.py            # 保留（关键词策略）
├── storage.py                     # 保留（存储层）
└── page_analyzer.py               # 保留（页面分析）
```

### 4.3 废弃

以下文件的逻辑被配置化替代:
- `selectors.py` → `profiles/zhipin.yaml` 的 `dom` 段
- `pre_filter.py` → `profiles/zhipin.yaml` 的 `filters` 段 + `filter_chain.py`
- `scraper.py` 业务逻辑 → 引擎 (~150 行) + 配置

---

## 5. 迁移计划

### Phase 1: 基础设施（无行为变更）
1. 创建 `shared/engine/` 目录结构
2. 实现 `SiteProfile` 数据类 + YAML 加载器
3. 实现 `DomReader`, `UrlBuilder`, `FilterChain`, `ReportBuilder`
4. 创建 `profiles/zhipin.yaml`（从现有代码逆向提取）

### Phase 2: 引擎替换（行为对等）
5. 实现 `ScrapingEngine`（复用现有 storage/page_analyzer 等）
6. 双轨运行: 新旧引擎并行，对比输出一致性
7. 切换入口: `__init__.py` 转发到新引擎

### Phase 3: 清理
8. 标记 `selectors.py`, `pre_filter.py` 为 deprecated
9. 精简 `scraper.py`（仅保留兼容导出）
10. 更新测试套件

### Phase 4: 扩展验证
11. 写一份 `profiles/58tongcheng.yaml` 验证多站能力
12. 文档更新

---

## 6. 验收标准

- [ ] `profiles/zhipin.yaml` 包含当前全部选择器/过滤规则/URL/报告配置
- [ ] `ScrapingEngine.run()` 输出与当前 `scraper.search_jobs()` 一致
- [ ] 新增过滤条件只需改 YAML（不改 Python）
- [ ] BOSS 直聘改版换选择器只需改 YAML
- [ ] 报告加维度只需改 YAML
- [ ] 所有现有测试通过
- [ ] 引擎代码量 ≤ 200 行（不含 adapter/protocol）
