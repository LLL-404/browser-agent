# BOSS 直聘求职助手 — 设计规格

## 概述

一个基于 Python + Camoufox（底层 Playwright）的半自动求职助手，面向 BOSS 直聘网页版。
核心逻辑：自动搜索采集职位 → 借力 IDE 内置 AI 分析匹配度 → 生成推荐报告和招呼语 → 用户手动确认后去 BOSS 直聘发送沟通。

目标用户画像：大专学历，追求"朝九晚五 + 五险一金 + 包食宿"的规律保障型工作，不限行业、不限城市。

---

## 1. 项目结构

```
boss-job-hunter/
  config.yaml              # 用户唯一需要编辑的配置文件
  main.py                  # CLI 入口（python main.py search|analyze|report|chat|status）
  mcp_server.py            # MCP Server，暴露工具给 IDE 内置 AI
  core/
    __init__.py
    scraper.py             # Camoufox 浏览器操控
    storage.py             # SQLite 读写（批量操作）
    exporter.py            # 数据序列化（Markdown / JSON）
    anti_detect.py         # 拟人延迟 / 鼠标轨迹 / 节流控制
    keyword_strategy.py    # 三层 + 自适应关键词策略
    city_codes.py          # BOSS 直聘城市代码映射表
    pre_filter.py          # 前置规则过滤（不进详情）
  data/
    jobs.db                # SQLite 数据库（自动创建）
    export/                # 导出给 AI 分析的文件
    reports/               # AI 分析后的推荐报告
```

---

## 2. 配置文件 (config.yaml)

```yaml
# 用户搜索条件
search:
  education: "大专"               # 学历
  expected_benefits:              # 期望福利（用于 AI 匹配，非平台筛选）
    - "五险一金"
    - "包食宿"
    - "朝九晚五"
    - "双休"
  keywords:                       # 三层关键词，L1 必搜，L2/L3 按城市特征自适应
    L1: ["普工", "操作工", "包装工", "学徒", "保安", "保洁"]
    L2: ["仓管", "质检", "叉车工", "厨师", "服务员", "电工"]
    L3: ["文员", "客服", "司机", "焊工", "后勤", "搬运工"]

# 城市优先级（全国搜索分四档）
cities:
  priority_1: ["深圳", "广州", "东莞", "佛山", "苏州", "杭州", "成都", "重庆"]
  priority_2: ["武汉", "南京", "长沙", "郑州", "西安", "合肥", "宁波", "无锡"]
  priority_3: ["常州", "嘉兴", "绍兴", "温州", "福州", "厦门", "珠海", "中山"]
  priority_4: ["泉州", "漳州", "湖州", "金华", "台州", "惠州", "江门", "南宁", "贵阳", "昆明", "南昌", "太原", "哈尔滨", "长春", "沈阳", "大连", "济南", "青岛", "烟台", "潍坊"]

# 前置过滤规则（列表页判断，不进详情页，节省请求量）
pre_filters:
  min_salary: 3000               # 月薪低于此值直接跳过
  title_blacklist:               # 标题含这些词说明学历/资历门槛高于大专
    - "高级"
    - "资深"
    - "经理"
    - "总监"
    - "硕士"
    - "本科及以上"
  company_blacklist:             # 这些行业大概率底薪+提成，无固定作息
    - "金融"
    - "保险"
    - "房产中介"
    - "投资"
  tag_whitelist:                 # 标签中至少含其中一个才考虑进详情
    - "包住"
    - "包吃"
    - "五险"
    - "双休"
    - "社保"
    - "住宿"

# 运行参数
runtime:
  cities_per_session: 3          # 每次 search 搜索城市数
  max_detail_pages_per_city: 30  # 每个城市最多进详情页数
  page_scroll_delay: [2, 5]      # 翻页延迟范围（秒）
  detail_delay: [3, 7]           # 详情页延迟范围（秒）
  captcha_pause_minutes: 5       # 遇到验证码暂停时间
  max_inactive_days: 7           # 招聘者超过此天数未活跃则视为不招了
  batch_size: 50                 # AI 批量分析时每次处理的职位数
```

---

## 3. MCP Server 设计

通过 MCP (Model Context Protocol) 将求职助手的核心能力暴露为工具，IDE 内置 AI 直接调用，全程对话驱动。

### 3.0 交互模型

```
你（在 IDE 中对话）           MCP Server               Camoufox 浏览器
        │                         │                         │
        │ "搜东莞佛山苏州"         │                         │
        │ ──────────────────────→ │                         │
        │                         │ 启动浏览器，打开BOSS直聘   │
        │                         │ ────────────────────────→ │
        │                         │      ← 等待你扫码登录 ←    │
        │ 「已登录」               │                         │
        │ ──────────────────────→ │                         │
        │                         │ 按城市代码拼URL直接跳转     │
        │                         │ 列表页前置过滤 → 详情页抓取 │
        │                         │ ────────────────────────→ │
        │                         │      ← 返回结果 ←         │
        │ 「搜完了，85条入库」     │                         │
        │ ← ───────────────────── │                         │
        │                         │                         │
        │ "分析这批"              │                         │
        │ ──────────────────────→ │                         │
        │                         │ 返回50条职位数据（JSON）   │
        │ ← ───────────────────── │                         │
        │ [AI 内部分析...]        │                         │
        │ 一次性写回50条评分       │                         │
        │ ──────────────────────→ │                         │
```

### 3.1 工具列表

#### search_jobs

```
参数: cities, keywords (可选), max_detail (可选)
返回: 摘要 {城市: {搜到数, 入库数, 跳过数}}
```

**内部流程**：
1. 启动 Chromium 浏览器（非无头，用户可见）
2. 打开 BOSS 直聘首页，等待用户手动登录（扫码或手机验证码）
3. 登录确认后，遍历城市列表
4. 每个城市：用 city_codes 映射表拼 URL 直接跳转（如 `?city=101280600`）
5. 若未指定 keywords，按关键词自适应策略选定关键词
6. 列表页采集：标题、公司、薪资、标签、招聘者活跃时间
7. **前置过滤**（不进详情）：
   - 薪资 < min_salary → 跳过
   - 标题含 title_blacklist 关键词 → 跳过
   - 公司名含 company_blacklist → 跳过
   - 标签中不含 tag_whitelist 任意一项 → 跳过
   - 招聘者超过 max_inactive_days 天未活跃 → 跳过
8. 通过前置过滤的，进入详情页抓取完整描述 + 公司信息
9. 实时写入 SQLite（逐条，防丢失）
10. 每城详情页合计上限 max_detail_pages_per_city 条
11. 搜完返回摘要

**状态管理**：
- `search_log` 表记录每个城市搜索状态（pending / in_progress / done）
- 每次启动跳过 done 的城市，支持断点续跑

#### list_jobs

```
参数: status, city, min_score, limit, offset
返回: 职位列表（不含 description 全文，轻量）
```

用于 AI 快速浏览和筛选。不含全文减少 token 消耗。

#### get_job_detail

```
参数: job_id
返回: 单条职位的完整信息（含 description 全文 + 公司信息）
```

AI 需要深度分析特定职位时使用。

#### batch_analyze

```
参数: (无，自动读取 status='new' 的职位)
返回: 最多 batch_size 条职位数据，每条含完整描述 + 城市租金参考
```

**设计要点**：AI 收到数据后，在自己的上下文中逐条分析，一次性用 `batch_update` 写回结果。避免 2N 次 MCP 往返，降为 2 次。

#### batch_update

```
参数: results [{job_id, fields...}, ...]
返回: 更新成功/失败数
```

批量写入 AI 分析结果。fields 包括：
- five_insurance, room_board, regular_hours
- overtime_risk, diploma_ok, recruiter_active_bool
- match_score, reason
- status 自动改为 'analyzed'，写入 analyzed_at

#### get_stats

```
参数: (无)
返回: {
  总职位数, 各状态数量, 已搜索城市数/总数,
  待分析数, 推荐数(≥6分), 各城市分布
}
```

#### update_status

```
参数: job_id, status
有效值: applied / interview / offered / rejected / ignored
返回: 更新确认
```

手动追踪投递进展。设为 applied 时自动写入 applied_at。

---

## 3.2 对话驱动示例

```
用户: "帮我搜东莞、佛山、苏州，各城上限20条详情"
AI:   [调用 search_jobs(cities=["东莞","佛山","苏州"], max_detail=20)]
      → 浏览器弹出，用户扫码登录
      → 脚本搜索中...
      → "搜索完成：东莞 18条，佛山 22条，苏州 15条，共入库 55 条"

用户: "分析一下刚搜的"
AI:   [调用 batch_analyze] → 返回 50 条职位数据
      [AI 内部分析 50 条...]
      [调用 batch_update 写回结果]
      → "分析完成：7分以上 6 条，6-7分 12 条，低于6分 32 条"

用户: "7分以上的给我看看"
AI:   [调用 list_jobs(min_score=7)] → 展示推荐列表

用户: "给前3条生成招呼语"
AI:   [调用 get_job_detail × 3] → 针对每条生成招呼语

用户: "第一条我投了，第三条不感兴趣"
AI:   [调用 update_status(job_id=1, status="applied")]
      [调用 update_status(job_id=3, status="ignored")]
```

---

## 4. 数据库设计 (SQLite)

### 表：jobs

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| boss_job_id | TEXT UNIQUE | BOSS 直聘职位 ID，用于去重 |
| title | TEXT | 职位标题 |
| company | TEXT | 公司名称 |
| salary | TEXT | 薪资范围（原始文本） |
| city | TEXT | 城市 |
| tags | TEXT | 列表页标签（JSON 数组） |
| recruiter_active | TEXT | 招聘者活跃时间（原始文本，如"今日活跃"） |
| description | TEXT | 详情页职位描述全文 |
| company_info | TEXT | 公司规模/行业信息 |
| job_url | TEXT | 职位直达链接 |
| status | TEXT | new / analyzed / applied / interview / offered / rejected / ignored |
| five_insurance | INTEGER | 0=未判断, 1=是, -1=否 |
| room_board | INTEGER | 同上 |
| regular_hours | INTEGER | 同上 |
| overtime_risk | TEXT | low / mid / high |
| diploma_ok | INTEGER | 0=未判断, 1=可投, -1=不可投 |
| recruiter_active_bool | INTEGER | 0=未判断, 1=7天内活跃, -1=超过7天 |
| match_score | INTEGER | 0-10 |
| ai_reason | TEXT | AI 分析理由 |
| created_at | TEXT | 入库时间 |
| analyzed_at | TEXT | 分析时间 |
| applied_at | TEXT | 投递时间 |

### 表：search_log

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| city | TEXT | 城市名 |
| status | TEXT | pending / in_progress / done |
| job_count | INTEGER | 该城市搜到的职位数 |
| started_at | TEXT | |
| finished_at | TEXT | |

### 表：chat_templates

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | |
| job_id | INTEGER FK | 关联 jobs.id |
| template | TEXT | 生成的招呼语 |
| used | INTEGER | 0=未使用, 1=已使用 |
| created_at | TEXT | |

招呼语标记为已使用时，自动将对应 `jobs.status` 更新为 `applied`，并写入 `applied_at`。

---

## 5. 关键词策略

### 5.1 三层分层

| 层级 | 含义 | 策略 |
|------|------|------|
| L1 | 高福利岗位（包食宿概率 > 50%）| 每个城市都搜 |
| L2 | 中等福利岗位（包食宿概率 20-50%）| 按城市特征自适应选择 |
| L3 | 低福利岗位（包食宿概率 < 20%）| 仅 L1 结果少时追加 |

### 5.2 自适应调度

不做盲扫，先用 L1 试探城市产业特征，再决定后续关键词：

```
第 1 轮：搜 L1[0]（如"普工"）→ 看结果数
  结果多（>80）→ 该城市制造业发达
    → L2 选"质检""仓管""叉车工"
    → L3 跳过（不需追，结果已多）
  结果中等（20-80）
    → L1 全部关键词
    → L2 选"服务员""厨师"（探索服务业）
  结果少（<20）
    → L1 全部关键词
    → L2 选"文员""客服""司机"（探索其他领域）
    → 若仍少，追加 L3
```

每次搜索的实际关键词数由城市的实际需求决定，避免在无结果的城市浪费搜索。

---

## 6. 反检测与拟人策略

| 策略 | 实现 |
|------|------|
| 非无头浏览器 | 始终以可见模式运行，不隐藏窗口 |
| viewport 随机化 | 每次启动随机窗口尺寸 |
| 翻页延迟 | 每次翻页前等待 2-5 秒随机值 |
| 详情页延迟 | 打开详情页后等待 3-7 秒再抓取 |
| 鼠标模拟 | 点击前先移动鼠标到元素位置（缓慢移动） |
| 滚动模拟 | 列表页分段滚动，模拟人类浏览 |
| 单次上限 | 每个城市最多 30 条详情 |
| 验证码处理 | 检测到验证码 → 暂停 5 分钟 → 弹出提示让用户手动处理 |

---

## 7. 错误处理与容错

| 场景 | 处理 |
|------|------|
| 浏览器崩溃 | 捕获异常，保存进度，提示重试 |
| 网络超时 | 重试最多 3 次，每次间隔 30 秒 |
| Cookie 过期 | 检测到未登录状态 → 暂停 → 提示重新登录 |
| 验证码 | 暂停 5 分钟，用户手动过 |
| 页面元素变化 | 使用多个备选选择器，全部失败则跳过该条 |
| JSON 解析失败 | 逐条验证，跳过格式错误的记录并报告 |

---

## 8. 技术依赖

```
playwright        # 浏览器自动化
pyyaml            # 配置文件解析
```

不依赖外部 AI API，AI 分析通过 IDE 内置 AI 完成（零成本、零配置）。

---

## 9. 购买力修正参考数据

AI 分析时需考虑不同城市的生活成本差异。脚本导出分析数据时，自动附加该城市的租金参考（内置对照表）：

| 城市等级 | 示例城市 | 单间月租参考 |
|----------|----------|-------------|
| 一线 | 深圳、广州、杭州 | 1500-2500 |
| 新一线/二线 | 成都、武汉、南京、东莞、佛山 | 800-1500 |
| 三四线 | 惠州、江门、嘉兴、漳州 | 400-800 |

AI 收到职位后会综合判断：薪资减去参考租金后的可支配收入。

---

## 10. 数据文件说明

| 文件 | 用途 | 生命周期 |
|------|------|----------|
| data/jobs.db | 职位数据持久化 | 持续累积 |
| data/export/todo_YYYY-MM-DD.md | 待分析职位（人类阅读） | 分析后可删除 |
| data/export/todo_YYYY-MM-DD.json | 待分析职位（JSON 骨架） | 入库后可删除 |
| data/reports/report_YYYY-MM-DD.md | 推荐报告 | 长期保留 |

---

## 11. BOSS 直聘城市代码映射

城市切换通过 URL 参数实现，`city_codes.py` 内置对照表：

| 城市 | 代码 | 城市 | 代码 |
|------|------|------|------|
| 深圳 | 101280600 | 广州 | 101280100 |
| 东莞 | 101281600 | 佛山 | 101280800 |
| 苏州 | 101190400 | 杭州 | 101210100 |
| 成都 | 101270100 | 重庆 | 100040000 |
| 武汉 | 101200100 | 南京 | 101190100 |
| 长沙 | 101250100 | 郑州 | 101180100 |
| 西安 | 101110100 | 合肥 | 101220100 |
| 宁波 | 101210400 | 无锡 | 101190200 |
| 常州 | 101191100 | 嘉兴 | 101210300 |
| 绍兴 | 101210500 | 温州 | 101210700 |
| 福州 | 101230100 | 厦门 | 101230200 |
| 珠海 | 101280700 | 中山 | 101281700 |
| 泉州 | 101230500 | 漳州 | 101230600 |
| 湖州 | 101210200 | 金华 | 101210900 |
| 台州 | 101210800 | 惠州 | 101280300 |
| 江门 | 101281100 | 南宁 | 101300100 |
| 贵阳 | 101260100 | 昆明 | 101290100 |
| 南昌 | 101240100 | 太原 | 101100100 |
| 哈尔滨 | 101050100 | 长春 | 101060100 |
| 沈阳 | 101070100 | 大连 | 101070200 |
| 济南 | 101120100 | 青岛 | 101120200 |
| 烟台 | 101120500 | 潍坊 | 101120600 |

URL 构造方式：`https://www.zhipin.com/web/geek/job?city={代码}&query={关键词}`
