# 核心算法复杂度 — 补充交付

**交付时间**: 2026-06-01  
**任务**: 核心算法复杂度说明（口头回复归档）

---

## scraper.py — O(N)

`_collect_list_page` 遍历 P=5 页 × 每页 N≈30 张卡片。每张卡片调用 `_parse_list_card`：

| 操作 | 复杂度 | 依据 |
|------|--------|------|
| `card.hover()` | O(1) | Playwright DOM 操作 |
| `query_selector` ×4 | O(1) | CSS 选择器引擎 |
| `query_selector_all` + 标签遍历 | O(T) | T≈2~4（常数） |
| `re.search` 提取 ID | O(L) | L≈50 字符（常数） |

**渐近 O(N)**。P、T、L 均为小常数。每卡片独立解析，无跨卡片状态。

`_scrape_detail` 单详情页：3 个选择器 + 3 次 `inner_text()` → **O(1)**。

---

## pre_filter.py — O(1)

`should_skip_job` 逐条顺序检查，命中任一即提前返回：

| 检查项 | 操作 | 复杂度 |
|--------|------|--------|
| 薪资下限 | 2 条预编译正则 `.findall`，输入 ≤15 字符 | O(1) |
| 标题黑名单 | `word.lower() in title_lower`，B≤10 次 | O(B) |
| 公司黑名单 | 同上，C≤5 次 | O(C) |
| 活跃度 | 3 条正则 + dict 回退 | O(1) |

**最好 O(1)**（第 1 项命中），**最坏 O(B+C)**（全部通过）。B=10、C=5 均为小数常量 → **渐近 O(1)**。

---

## keyword_strategy.py — O(1)

全程基于 Python dict（YAML 配置反序列化）：

| 操作 | 复杂度 | 依据 |
|------|--------|------|
| `cfg.get("search").get("keywords")` | O(1) | dict 哈希查找 |
| `keywords.get("L1")` / L2 / L3 | O(1) | dict 哈希查找 |
| `[k for k in l2 if k in (...)]` | O(k) | k≤5 项，tuple in 测试 |
| `l1 + mfg_l2` | O(k) | k≤10 项，列表拼接 |

**渐近 O(1)**。全部操作在 ≤10 项的 dict/list 上，无输入规模依赖。

---

## 空间复杂度 — 运行时 O(N)，线性增长

| 来源 | 峰值 | 说明 |
|------|------|------|
| `_collect_list_page` 的 `all_jobs` | ~75KB | 5页×30卡片×500字节/卡片 |
| `search_jobs` 主循环 | 不叠加 | 每个城市+关键词对采集完后释放 |
| SQLite 查询 | 不随总行数增长 | `get_stats` 用 COUNT(*) 聚合，`get_jobs` 默认 limit 50 |
| DB 文件 377 条 | ~200KB（磁盘） | SQLite 页缓存按需加载，不预读全表 |

**运行时峰值与单批采集卡片数 N 线性，不随 DB 总存量增长**。

---

## 结论

| 模块 | 时间复杂度 | 空间复杂度 | 数据规模假设 |
|------|-----------|-----------|-------------|
| scraper.py | O(N) | O(N) 瞬时 | N≤150/批次 |
| pre_filter.py | O(1) | O(1) | — |
| keyword_strategy.py | O(1) | O(1) | — |

全部模块 **不存在 O(N²) 或 O(N log N) 操作**。最可能成为瓶颈的是 scraper 的 O(N) Playwright DOM 操作（单卡片 ~500ms），此为浏览器自动化固有延迟，非算法问题。
