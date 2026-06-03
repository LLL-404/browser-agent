# 核心算法复杂度说明

**生成时间**：2026-06-01 14:10

---

## 1. scraper.py · 核心抓取引擎

### 调用链

```
search_jobs(cities, keywords, max_detail, headless)
  └─ _ensure_login(page)                           # O(1) — 一次页面导航
  └─ for each city:
       └─ _search_one_city(page, city, ...)
            ├─ _goto_search(page, city, keyword)     # O(1) — 一次浏览器导航
            ├─ _collect_list_page(page, city)         # O(M) — M 为当前页卡片数
            │    └─ _parse_list_card(card) per card   # O(1) — 固定字段提取
            ├─ _process_job_entry(page, job)          # O(1) — pre_filter + SQLite insert
            └─ (quick_mode=False) _scrape_detail(...) # O(1) — 一次详情页导航 + DOM 查询
```

### 时间复杂度

| 层次 | 表达式 | 说明 |
|------|--------|------|
| 单卡片解析 | O(1) | 4 次 `query_selector` + 字符串提取，与 N 无关 |
| 单页收集 | O(M) | M 为卡片数（通常 ≤30），逐条解析 |
| 单关键词 | O(M) | 跨页翻页，每页 O(M)，总卡片数线性增长 |
| 单城市 | O(K × M) | K = 关键词数（3~8），M 为每关键词收集的卡片总数 |
| 全流程 | O(C × K × M) | C = 城市数（默认 ≤3） |

**结论**：O(N)，其中 N = 处理的岗位卡片总数。每卡片恒定操作数，无嵌套二次遍历。

### 空间复杂度

| 来源 | 特征 |
|------|------|
| `_collect_list_page` | 结果存入 `list[dict]`，每次最多 ~30 条，每条 ~0.5 KB。**释放于函数返回后** |
| `search_jobs` | 跨城市不累积——每城市完成即写入 SQLite 并释放 |
| `_scrape_detail` | 详情页解析结果直接 `j.update(detail)` 后写库，不累积 |
| 浏览器进程 | 固定开销 200~500 MB，与 N 无关 |
| 总内存 | **O(1)** 与 N 无关，SQLite 逐条写入无累积 |

### 瓶颈

- **详情页抓取**（`_scrape_detail`）：每条约 1~3 秒（页面加载 + 3 组 failover 选择器查询）。通过 `Semaphore(2)` 控制并发，常数因子已被限制。
- **网络 I/O**：`_goto_search` 20 秒超时 + retry（2 次）。浏览器导航是主要耗时来源，但属于外部 I/O 等待，不计入 CPU 复杂度。

---

## 2. pre_filter.py · 岗位预过滤

### 函数分析

#### `parse_salary_min(salary_text) → int | None`
- **实现**：预编译 `re.compile` + `findall` 在短字符串（~20 字符）上匹配。
- **复杂度**：O(1)。正则匹配在预编译后为固定模式匹配，输入长度恒定。
- **调用频率**：每条岗位卡片调用 1 次。

#### `should_skip_job(title, company, salary, tags, recruiter_active) → (bool, str)`
- **实现**：4 个顺序检查步骤：
  1. `parse_salary_min` → O(1)
  2. 标题黑名单 → `word.lower() in title_lower`，最多 K≤6 次子串匹配
  3. 公司黑名单 → 同上
  4. 招聘者活跃度 → `_parse_inactive_days` → O(1)
- **复杂度**：O(1) 常量时间。K（规则数）和 L（文本长度）均为有界常数。
- **调用频率**：每条卡片调用 1 次。

#### `_parse_inactive_days(active_text) → int | None`
- **实现**：if-in 分支（今日/刚刚/分钟/小时）→ 3 组预编译 regex → dict 回退查找。
- **复杂度**：O(1)。输入文本长度通常 ≤10 字符。
- **瓶颈**：无。单次 < 0.01ms。

### 总体结论

- **时间复杂度**：O(1) *per call*。全流程 O(N)，N = 岗位卡片数。
- **空间复杂度**：O(1)。临时字符串和整数变量，无累积数据结构。
- **瓶颈**：无。纯 CPU 逻辑，毫秒级完成。

---

## 3. keyword_strategy.py · 关键词策略

### 函数分析

#### `get_keywords_for_city(city, l1_result_count) → list[str]`
- **实现**：
  1. `get_config()` 单例 → O(1)
  2. `keywords.get("L1", [])` → dict 键查找，O(1)
  3. 分支判断：依 `l1_result_count` 进入 3 个分支之一
  4. 列表推导过滤 L2/L3 → O(K)，K ≤ 6
  5. 列表拼接 → O(len(L1) + len(L2_filtered))
- **复杂度**：O(K)，K 为 config 中关键词列表长度（L1 + L2 + L3 ≤ 8）。常数时间。
- **调用频率**：每城市首次试探后调用 1 次。

#### `get_initial_keyword() → str`
- **实现**：`get_config()` → `keywords["L1"][0]`
- **复杂度**：O(1)。单次 config 键查找。
- **调用频率**：每城市调用 1 次。

### 总体结论

- **时间复杂度**：O(1)，全流程常数时间。
- **空间复杂度**：O(K)，K ≤ 8。临时列表在函数返回后释放。
- **瓶颈**：无。毫秒级完成。

---

*由 `scripts/project_structure_scanner.py` 自动生成的报告中 P5 模块状态分析可交叉验证。*
