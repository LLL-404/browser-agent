# 全链路声明式引擎实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 modes/zhipin/ 中硬编码的业务逻辑解耦到 YAML 声明式配置 + 通用引擎，实现改需求只改配置。

**Architecture:** 站点画像(YAML) → 通用引擎(Python) → 可选适配器。引擎不含业务逻辑，所有选择器/过滤规则/URL模板/报告维度来自配置文件。

**Tech Stack:** Python 3.7+, Pydantic/dataclasses (YAML → 对象), Playwright (DOM 操作), pytest (TDD)

**Spec:** [2026-06-04-declarative-engine-design.md](../specs/2026-06-04-declarative-engine-design.md)

---

## 文件结构总览

### 新建文件

| 文件 | 职责 | 预估行数 |
|------|------|---------|
| `src/shared/engine/__init__.py` | 包导出 | ~10 |
| `src/shared/engine/profile.py` | SiteProfile 数据类 + YAML 加载器 | ~120 |
| `src/shared/engine/adapter_protocol.py` | SiteAdapter 协议 + DefaultAdapter | ~80 |
| `src/shared/engine/url_builder.py` | URL 模板构建（多模板+优先级） | ~60 |
| `src/shared/engine/dom_reader.py` | 配置驱动的 DOM 读取器 | ~150 |
| `src/shared/engine/filter_chain.py` | 过滤链解释器 + 内置规则类型 | ~130 |
| `src/shared/engine/report_builder.py` | 动态报告生成器 | ~100 |
| `src/shared/engine/scraping_engine.py` | 主流程编排引擎 | ~180 |
| `profiles/zhipin.yaml` | BOSS 直聘站点画像 | ~100 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/modes/zhipin/__init__.py` | 入口转发到新引擎 |
| `src/shared/config.py` | 增加 profile 加载路径 |

### 废弃文件（Phase 3 清理）

| 文件 | 替代 |
|------|------|
| `src/modes/zhipin/selectors.py` | `profiles/zhipin.yaml` → `dom` 段 |
| `src/modes/zhipin/pre_filter.py` | `profiles/zhipin.yaml` → `filters` 段 |

---

## Task 1: SiteProfile 数据模型 + YAML 加载器

**Files:**
- Create: `src/shared/engine/__init__.py`
- Create: `src/shared/engine/profile.py`
- Test: `src/tests/test_profile.py`

**目标:** 定义完整的 SiteProfile 数据结构，能从 YAML 文件加载为 Python 对象。

- [ ] **Step 1: 创建包初始化文件**

```python
# src/shared/engine/__init__.py
"""通用爬取引擎 — 配置驱动，不含业务逻辑。"""

from shared.engine.profile import SiteProfile, load_profile
from shared.engine.scraping_engine import ScrapingEngine

__all__ = ["SiteProfile", "load_profile", "ScrapingEngine"]
```

- [ ] **Step 2: 编写 Profile 数据模型**

```python
# src/shared/engine/profile.py
"""站点画像数据模型 — 从 YAML 声明式配置加载站点全部行为参数。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class MetaConfig:
    name: str = ""
    display_name: str = ""
    version: int = 1


@dataclass
class NavigationConfig:
    home: str = ""
    login: str = ""


@dataclass
class UrlTemplate:
    template: str = ""
    priority: int = 1


@dataclass
class UrlsConfig:
    search: List[UrlTemplate] = field(default_factory=list)


@dataclass
class DomListConfig:
    card: str = ""
    title: str = ""
    title_link: str = ""
    company: str = ""
    salary: str = ""
    tags: str = ""


@dataclass
class PaginationConfig:
    next_button: str = ""
    disabled_class_contains: str = "disabled"


@dataclass
class DetailSelectors:
    description: List[str] = field(default_factory=list)
    company: List[str] = field(default_factory=list)
    recruiter_active: List[str] = field(default_factory=list)
    panel_salary: str = ""


@dataclass
class CaptchaConfig:
    indicators: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


@dataclass
class LoginConfig:
    user_menu: str = ""
    page_auth_patterns: List[str] = field(default_factory=list)
    text_positive: List[str] = field(default_factory=list)
    text_negative: List[str] = field(default_factory=list)


@dataclass
class DomConfig:
    list: DomListConfig = field(default_factory=DomListConfig)
    pagination: PaginationConfig = field(default_factory=PaginationConfig)
    detail: DetailSelectors = field(default_factory=DetailSelectors)
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    login: LoginConfig = field(default_factory=LoginConfig)


@dataclass
class FilterRule:
    id: str = ""
    type: str = ""
    field: str = ""
    case_insensitive: bool = False
    config_key: str = ""
    source: str = ""
    max_days_key: str = ""
    reason_template: str = ""


@dataclass
class ReportDimension:
    key: str = ""
    label: str = ""


@dataclass
class ReportConfig:
    score_threshold: int = 6
    dimensions: List[ReportDimension] = field(default_factory=list)


@dataclass
class SiteProfile:
    """站点完整画像 — 一个 YAML 文件对应一个实例。"""
    meta: MetaConfig = field(default_factory=MetaConfig)
    navigation: NavigationConfig = field(default_factory=NavigationConfig)
    urls: UrlsConfig = field(default_factory=UrlsConfig)
    dom: DomConfig = field(default_factory=DomConfig)
    filters: List[FilterRule] = field(default_factory=list)
    report: ReportConfig = field(default_factory=ReportConfig)

    # 运行时合并的全局配置引用（从 config.yaml 注入）
    _global_config: dict = field(default_factory=dict, repr=False)

    def get_global(self, dot_path: str, default: Any = None) -> Any:
        """按点分路径读取全局配置值，如 'pre_filters.min_salary'。"""
        keys = dot_path.split(".")
        val: Any = self._global_config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default
        return val if val is not None else default


def load_profile(name: str, global_config: dict | None = None) -> SiteProfile:
    """从 profiles/{name}.yaml 加载站点画像。

    Args:
        name: 站点名称（不含 .yaml 后缀），如 "zhipin"
        global_config: 全局配置（config.yaml 内容），用于 filters 引用

    Returns:
        解析后的 SiteProfile 实例
    """
    import yaml

    # 定位 profile 文件：先找项目 profiles/ 目录，再找包内
    base_dir = _get_base_dir()
    profile_path = os.path.join(base_dir, "profiles", f"{name}.yaml")

    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"站点画像不存在: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        raw: dict = yaml.safe_load(f) or {}

    profile = _dict_to_profile(raw)
    if global_config:
        profile._global_config = global_config
    return profile


def _get_base_dir() -> str:
    """获取项目根目录（shared/ 的上级）。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _dict_to_profile(d: dict) -> SiteProfile:
    """将 YAML 字典递归转换为 SiteProfile 数据类。"""
    def _get(key: str, factory) -> Any:
        val = d.get(key)
        if val is None:
            return factory() if callable(factory) else factory
        if isinstance(factory, type) and hasattr(factory, '__dataclass_fields__'):
            # 嵌套 dataclass：递归转换
            return _dict_to_nested(val, factory)
        return val

    def _dict_to_nested(val: Any, cls: type) -> Any:
        if isinstance(val, dict):
            field_defaults = {f.name: f.default for f in cls.__datafields__.values()
                              if not isinstance(f.default, type)}
            kwargs = {}
            for fname, ftype in cls.__datafields__.items():
                if fname in val:
                    inner_type = ftype.type
                    # 处理 List 字段
                    origin = getattr(inner_type, "__origin__", None)
                    if origin is list:
                        item_type = inner_type.__args__[0]
                        if hasattr(item_type, '__datafields__'):
                            kwargs[fname] = [_dict_to_nested(item, item_type) for item in val[fname]]
                        else:
                            kwargs[fname] = val[fname]
                    elif hasattr(inner_type, '__datafields__'):
                        kwargs[fname] = _dict_to_nested(val[fname], inner_type)
                    else:
                        kwargs[fname] = val[fname]
                elif fname in field_defaults:
                    kwargs[fname] = field_defaults[fname]
            return cls(**kwargs)
        return val

    # 手动映射顶层字段（避免过度泛化）
    meta_raw = d.get("meta", {})
    nav_raw = d.get("navigation", {})
    urls_raw = d.get("urls", {})
    dom_raw = d.get("dom", {})
    filters_raw = d.get("filters", [])
    report_raw = d.get("report", {})

    return SiteProfile(
        meta=MetaConfig(
            name=meta_raw.get("name", ""),
            display_name=meta_raw.get("display_name", ""),
            version=meta_raw.get("version", 1),
        ),
        navigation=NavigationConfig(
            home=nav_raw.get("home", ""),
            login=nav_raw.get("login", ""),
        ),
        urls=UrlsConfig(
            search=[
                UrlTemplate(template=u.get("template", ""), priority=u.get("priority", 1))
                for u in urls_raw.get("search", [])
            ],
        ),
        dom=_parse_dom_config(dom_raw),
        filters=[
            FilterRule(
                id=r.get("id", ""),
                type=r.get("type", ""),
                field=r.get("field", ""),
                case_insensitive=r.get("case_insensitive", False),
                config_key=r.get("config_key", ""),
                source=r.get("source", ""),
                max_days_key=r.get("max_days_key", ""),
                reason_template=r.get("reason_template", ""),
            )
            for r in filters_raw
        ],
        report=ReportConfig(
            score_threshold=report_raw.get("score_threshold", 6),
            dimensions=[
                ReportDimension(key=dim.get("key", ""), label=dim.get("label", ""))
                for dim in report_raw.get("dimensions", [])
            ],
        ),
    )


def _parse_dom_config(raw: dict) -> DomConfig:
    list_raw = raw.get("list", {})
    pag_raw = raw.get("pagination", {})
    detail_raw = raw.get("detail", {})
    captcha_raw = raw.get("captcha", {})
    login_raw = raw.get("login", {})

    return DomConfig(
        list=DomListConfig(
            card=list_raw.get("card", ""),
            title=list_raw.get("title", ""),
            title_link=list_raw.get("title_link", ""),
            company=list_raw.get("company", ""),
            salary=list_raw.get("salary", ""),
            tags=list_raw.get("tags", ""),
        ),
        pagination=PaginationConfig(
            next_button=pag_raw.get("next_button", ""),
            disabled_class_contains=pag_raw.get("disabled_class_contains", "disabled"),
        ),
        detail=DetailSelectors(
            description=detail_raw.get("description", []),
            company=detail_raw.get("company", []),
            recruiter_active=detail_raw.get("recruiter_active", []),
            panel_salary=detail_raw.get("panel_salary", ""),
        ),
        captcha=CaptchaConfig(
            indicators=captcha_raw.get("indicators", []),
            keywords=captcha_raw.get("keywords", []),
        ),
        login=LoginConfig(
            user_menu=login_raw.get("user_menu", ""),
            page_auth_patterns=login_raw.get("page_auth_patterns", []),
            text_positive=login_raw.get("text_positive", []),
            text_negative=login_raw.get("text_negative", []),
        ),
    )
```

- [ ] **Step 3: 编写测试 — Profile 加载与字段访问**

```python
# src/tests/test_profile.py
"""SiteProfile 数据模型测试。"""
import os
import tempfile
import pytest

from shared.engine.profile import (
    SiteProfile, load_profile, MetaConfig, NavigationConfig,
    UrlsConfig, DomConfig, FilterRule, ReportConfig,
)


class TestProfileLoading:
    def test_load_minimal_profile(self):
        """最小化 YAML 能正确加载。"""
        yaml_content = """
meta:
  name: test_site
navigation:
  home: "https://example.com"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            path = f.name

        try:
            # 通过 monkeypatch 路径来测试
            profile = _load_from_string(yaml_content)
            assert profile.meta.name == "test_site"
            assert profile.navigation.home == "https://example.com"
        finally:
            os.unlink(path)

    def test_full_profile_all_fields(self):
        """完整 YAML 所有字段都能正确解析。"""
        yaml_content = """
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
    card: "li.job-card-box"
    title: ".job-name"
    title_link: "a.job-name"
    company: ".boss-name"
    salary: ".job-salary"
    tags: ".tag-list li"
  pagination:
    next_button: ".next"
  detail:
    description: [".desc", ".detail"]
    company: [".company-info"]
    recruiter_active: [".active-time"]
  captcha:
    indicators: [".captcha"]
    keywords: ["验证码"]
  login:
    user_menu: ".user-menu"
    page_auth_patterns: ["/user/", "login"]
    text_positive: ["欢迎回来"]
    text_negative: ["登录"]
filters:
  - id: min_salary
    type: salary_threshold
    field: salary
    config_key: pre_filters.min_salary
    reason_template: "薪资低于阈值"
  - id: title_blacklist
    type: contains_any
    field: title
    source: pre_filters.title_blacklist
    reason_template: "标题含关键词"
report:
  score_threshold: 6
  dimensions:
    - key: five_insurance
      label: 五险一金
"""
        profile = _load_from_string(yaml_content)

        # meta
        assert profile.meta.name == "zhipin"
        assert profile.meta.display_name == "BOSS 直聘"
        assert profile.meta.version == 2

        # navigation
        assert "?ka=header-home" in profile.navigation.home

        # urls
        assert len(profile.urls.search) == 2
        assert profile.urls.search[0].priority == 1
        assert "{city_code}" in profile.urls.search[0].template

        # dom.list
        assert profile.dom.list.card == "li.job-card-box"
        assert profile.dom.list.title == ".job-name"

        # dom.detail
        assert len(profile.dom.detail.description) == 2
        assert profile.dom.detail.panel_salary == ""

        # filters
        assert len(profile.filters) == 2
        assert profile.filters[0].type == "salary_threshold"
        assert profile.filters[1].source == "pre_filters.title_blacklist"

        # report
        assert profile.report.score_threshold == 6
        assert len(profile.report.dimensions) == 1
        assert profile.report.dimensions[0].key == "five_insurance"

    def test_get_global_config_ref(self):
        """get_global 能按点分路径读取全局配置值。"""
        from shared.engine.profile import _dict_to_profile
        profile = _dict_to_profile({
            "meta": {"name": "test"},
            "filters": [
                {"id": "test", "type": "salary_threshold", "field": "salary",
                 "config_key": "pre_filters.min_salary"}
            ],
        })
        profile._global_config = {
            "pre_filters": {"min_salary": 3000, "title_blacklist": ["高级"]},
            "runtime": {"max_inactive_days": 7},
        }

        assert profile.get_global("pre_filters.min_salary") == 3000
        assert profile.get_global("pre_filters.title_blacklist") == ["高级"]
        assert profile.get_global("runtime.max_inactive_days") == 7
        assert profile.get_global("nonexistent.key") is None
        assert profile.get_global("nonexistent.key", 0) == 0

    def test_empty_yaml_returns_defaults(self):
        """空 YAML 返回默认值，不报错。"""
        profile = _load_from_string("{}")
        assert profile.meta.name == ""
        assert profile.navigation.home == ""
        assert len(profile.urls.search) == 0
        assert len(profile.filters) == 0
        assert len(profile.report.dimensions) == 0


def _load_from_string(yaml_str: str) -> SiteProfile:
    """辅助函数：从字符串加载 Profile（用于测试）。"""
    import yaml
    from shared.engine.profile import _dict_to_profile
    d = yaml.safe_load(yaml_str) or {}
    return _dict_to_profile(d)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/test_profile.py -v`

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/shared/engine/__init__.py src/shared/engine/profile.py src/tests/test_profile.py
git commit -m "feat(engine): add SiteProfile data model and YAML loader"
```

---

## Task 2: 适配器协议 + 默认实现

**Files:**
- Create: `src/shared/engine/adapter_protocol.py`
- Test: `src/tests/test_adapter.py`

**目标:** 定义可选的站点适配器接口和内置默认实现（覆盖薪资解析、活跃时间解析等通用逻辑）。

- [ ] **Step 1: 编写适配器协议和默认实现**

```python
# src/shared/engine/adapter_protocol.py
"""站点适配器协议 — 仅当 YAML 无法表达时才需要实现。

大多数场景使用内置的 DefaultAdapter 即可。
只有特殊数据格式或交互逻辑才需自定义适配器。
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable


@runtime_checkable
class SiteAdapter(Protocol):
    """可选适配器接口。引擎在需要时调用，未实现则跳过。"""

    def parse_salary(self, text: str) -> int | None:
        """从薪资文本提取最低月薪。如 '4K-6K' → 4000"""
        ...

    def parse_inactive_days(self, text: str) -> int | None:
        """从活跃时间文本提取天数。如 '3天前' → 3, '刚刚' → 0"""
        ...


class DefaultAdapter:
    """默认适配器 — 覆盖 80% 常见招聘网站的解析逻辑。
    
    继承此类并覆盖差异方法即可创建站点特有适配器。
    """

    # 预编译正则（避免高频调用重复编译）
    _RE_SALARY_K = re.compile(r'(\d+)\s*[Kk]')
    _RE_SALARY_NUM = re.compile(r'(\d+)')
    _RE_DAY = re.compile(r'(\d+)\s*天')
    _RE_WEEK = re.compile(r'(\d+)\s*周')
    _RE_MONTH = re.compile(r'(\d+)\s*个月')

    def parse_salary(self, text: str) -> int | None:
        """从薪资文本中提取最低月薪。
        
        支持格式：
        - '4K-6K' → 4000
        - '3000-5000元/月' → 3000
        - '5-8千' → 5000
        - '6000-8000' → 6000
        """
        if not text:
            return None

        # K 格式: 4K, 4K-6K
        nums = self._RE_SALARY_K.findall(text)
        if nums:
            return int(nums[0]) * 1000

        # 纯数字格式: 3000-5000
        nums = self._RE_SALARY_NUM.findall(text)
        if len(nums) >= 1:
            return int(nums[0])

        return None

    def parse_inactive_days(self, text: str) -> int | None:
        """解析活跃时间文本 → 天数。
        
        支持格式：
        - '今日活跃', '刚刚', '3分钟前' → 0
        - '昨天' → 1
        - '3天前' → 3
        - '2周前' → 14
        - '1个月前' → 30
        """
        if not text:
            return None

        text = text.strip()

        # 今天级别
        if any(kw in text for kw in ("今日", "刚刚", "分钟", "小时")):
            return 0

        # 正则匹配数字+单位
        patterns = [
            (self._RE_DAY, 1),
            (self._RE_WEEK, 7),
            (self._RE_MONTH, 30),
        ]
        for pat, multiplier in patterns:
            m = re.search(pat, text)
            if m:
                return int(m.group(1)) * multiplier

        # 关键词 fallback
        fallback_map = {"昨天": 1, "周前": 7, "月前": 30}
        for keyword, days in fallback_map.items():
            if keyword in text:
                return days

        return None


# 适配器注册表 — 按站点名查找适配器实例
_ADAPTER_REGISTRY: dict[str, SiteAdapter] = {}


def register_adapter(site_name: str, adapter: SiteAdapter) -> None:
    """注册站点适配器。"""
    _ADAPTER_REGISTRY[site_name] = adapter


def get_adapter(site_name: str) -> SiteAdapter:
    """获取站点适配器，未注册则返回默认适配器。"""
    return _ADAPTER_REGISTRY.get(site_name, DefaultAdapter())
```

- [ ] **Step 2: 编写测试**

```python
# src/tests/test_adapter.py
"""适配器协议和默认实现测试。"""
import pytest
from shared.engine.adapter_protocol import (
    DefaultAdapter, SiteAdapter, register_adapter, get_adapter,
)


class TestDefaultAdapterSalary:
    def setup_method(self):
        self.adapter = DefaultAdapter()

    def test_k_format(self):
        assert self.adapter.parse_salary("4K-6K") == 4000
        assert self.adapter.parse_salary("8K-12K") == 8000
        assert self.adapter.parse_salary("5K") == 5000

    def test_number_format(self):
        assert self.adapter.parse_salary("3000-5000元/月") == 3000
        assert self.adapter.parse_salary("6000-8000") == 6000

    def test_empty_input(self):
        assert self.adapter.parse_salary("") is None
        assert self.adapter.parse_salary(None) is None

    def test_case_insensitive_k(self):
        assert self.adapter.parse_salary("4k-6k") == 4000


class TestDefaultAdapterInactiveDays:
    def setup_method(self):
        self.adapter = DefaultAdapter()

    def test_today_level(self):
        assert self.adapter.parse_inactive_days("今日活跃") == 0
        assert self.adapter.parse_inactive_days("刚刚") == 0
        assert self.adapter.parse_inactive_days("3分钟前") == 0
        assert self.adapter.parse_inactive_days("2小时前") == 0

    def test_day_format(self):
        assert self.adapter.parse_inactive_days("3天前") == 3
        assert self.adapter.parse_inactive_days("7天前活跃") == 7

    def test_week_format(self):
        assert self.adapter.parse_inactive_days("2周前") == 14

    def test_month_format(self):
        assert self.adapter.parse_inactive_days("1个月前") == 30

    def test_fallback_keywords(self):
        assert self.adapter.parse_inactive_days("昨天") == 1
        assert self.adapter.parse_inactive_days("周前活跃") == 7

    def test_empty_input(self):
        assert self.adapter.parse_inactive_days("") is None
        assert self.adapter.parse_inactive_days(None) is None


class TestAdapterRegistry:
    def test_register_and_get(self):
        custom = DefaultAdapter()
        register_adapter("custom_site", custom)
        assert get_adapter("custom_site") is custom

    def test_fallback_to_default(self):
        adapter = get_adapter("nonexistent")
        assert isinstance(adapter, DefaultAdapter)

    def teardown_method(self):
        from shared.engine.adapter_protocol import _ADAPTER_REGISTRY
        _ADAPTER_REGISTRY.clear()
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/test_adapter.py -v`

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/shared/engine/adapter_protocol.py src/tests/test_adapter.py
git commit -m "feat(engine): add SiteAdapter protocol with DefaultAdapter"
```

---

## Task 3: URL 构建器

**Files:**
- Create: `src/shared/engine/url_builder.py`
- Test: `src/tests/test_url_builder.py`

**目标:** 根据 Profile.urls 配置构建搜索 URL，支持多模板 + 优先级 fallback。

- [ ] **Step 1: 实现 UrlBuilder**

```python
# src/shared/engine/url_builder.py
"""URL 构建器 — 从 Profile.urls 模板构建实际访问地址。"""
from __future__ import annotations

from typing import Optional

from shared.engine.profile import SiteProfile, UrlsConfig


class UrlBuilder:
    """基于站点画像的 URL 构建。"""

    def __init__(self, profile: SiteProfile):
        self.profile = profile
        self.urls: UrlsConfig = profile.urls

    def build_search(self, city_code: str, keyword: str,
                     priority: int | None = None) -> str:
        """构建搜索 URL。
        
        Args:
            city_code: 城市 ID（如 101280600）
            keyword: 搜索关键词
            priority: 指定优先级，None 则用最高优先级模板
            
        Returns:
            完整的搜索 URL
        """
        base = self.profile.navigation.home.rstrip("/")
        templates = self.urls.search

        if not templates:
            return f"{base}/web/search?city={city_code}&query={keyword}"

        # 按 priority 排序
        sorted_templates = sorted(templates, key=lambda t: t.priority)

        if priority is not None:
            matched = [t for t in sorted_templates if t.priority == priority]
            if matched:
                tmpl = matched[0].template
            else:
                tmpl = sorted_templates[0].template
        else:
            tmpl = sorted_templates[0].template

        url = base + tmpl.format(city_code=city_code, keyword=keyword)
        return url

    def get_home_url(self) -> str:
        """获取首页 URL。"""
        return self.profile.navigation.home

    def get_login_url(self) -> str:
        """获取登录页 URL。"""
        return self.profile.navigation.login

    def get_all_search_urls(self, city_code: str,
                             keyword: str) -> list[tuple[int, str]]:
        """获取所有搜索模板对应的 URL（含优先级）。
        
        用于重试场景：优先级高的先用，失败后降级。
        """
        base = self.profile.navigation.home.rstrip("/")
        results = []
        for tmpl in sorted(self.urls.search, key=lambda t: t.priority):
            full_url = base + tmpl.template.format(
                city_code=city_code, keyword=keyword
            )
            results.append((tmpl.priority, full_url))
        return results
```

- [ ] **Step 2: 编写测试**

```python
# src/tests/test_url_builder.py
"""UrlBuilder 测试。"""
import pytest
from shared.engine.profile import SiteProfile, UrlsConfig, UrlTemplate, NavigationConfig
from shared.engine.url_builder import UrlBuilder


def _make_profile(search_templates: list[dict]) -> SiteProfile:
    return SiteProfile(
        navigation=NavigationConfig(home="https://www.zhipin.com/?ka=header-home"),
        urls=UrlsConfig(search=[
            UrlTemplate(t["template"], t.get("priority", 1))
            for t in search_templates
        ]),
    )


class TestBuildSearch:
    def test_single_template(self):
        profile = _make_profile([
            {"template": "/web/geek/job?city={city_code}&query={keyword}"}
        ])
        builder = UrlBuilder(profile)
        url = builder.build_search("101280600", "普工")
        assert url == "https://www.zhipin.com/web/geek/job?city=101280600&query=普工"

    def test_multi_template_uses_highest_priority(self):
        profile = _make_profile([
            {"template": "/v1?c={city_code}&q={keyword}", "priority": 1},
            {"template": "/v2?c={city_code}&q={keyword}", "priority": 2},
        ])
        builder = UrlBuilder(profile)
        url = builder.build_search("101", "test")
        assert "/v1?" in url  # priority 1 最高

    def test_specific_priority(self):
        profile = _make_profile([
            {"template": "/v1?c={city_code}", "priority": 1},
            {"template": "/v2?c={city_code}", "priority": 2},
        ])
        builder = UrlBuilder(profile)
        url = builder.build_search("101", "test", priority=2)
        assert "/v2?" in url

    def test_empty_templates_fallback(self):
        profile = _make_profile([])
        builder = UrlBuilder(profile)
        url = builder.build_search("101", "test")
        assert "city=101" in url
        assert "query=test" in url

    def test_get_all_search_urls(self):
        profile = _make_profile([
            {"template": "/v1?c={city_code}", "priority": 2},
            {"template": "/v2?c={city_code}", "priority": 1},
        ])
        builder = UrlBuilder(profile)
        urls = builder.get_all_search_urls("101", "test")
        assert len(urls) == 2
        # 应按 priority 排序: 1 在前
        assert urls[0][0] == 1
        assert urls[1][0] == 2

    def test_home_and_login_urls(self):
        profile = SiteProfile(
            navigation=NavigationConfig(
                home="https://example.com/home",
                login="https://example.com/login",
            ),
        )
        builder = UrlBuilder(profile)
        assert builder.get_home_url() == "https://example.com/home"
        assert builder.get_login_url() == "https://example.com/login"
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/test_url_builder.py -v`

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/shared/engine/url_builder.py src/tests/test_url_builder.py
git commit -m "feat(engine): add UrlBuilder with multi-template support"
```

---

## Task 4: DOM 读取器

**Files:**
- Create: `src/shared/engine/dom_reader.py`
- Test: `src/tests/test_dom_reader.py`

**目标:** 所有 CSS 选择器来自 Profile.dom 配置，不硬编码任何 selector。

- [ ] **Step 1: 实现 DomReader**

```python
# src/shared/engine/dom_reader.py
"""DOM 读取器 — 选择器全部来自 SiteProfile.dom 配置。
 
提供统一的卡片采集、解析、详情提取接口。
内部处理 fallback 链（多选择器依次尝试）。
"""
from __future__ import annotations

import re
from typing import Any

from shared.engine.profile import SiteProfile, DomConfig


class DomReader:
    """配置驱动的 DOM 读取器。"""

    def __init__(self, profile: SiteProfile):
        self.profile = profile
        self.dom: DomConfig = profile.dom

    async def collect_cards(self, page) -> list:
        """用 dom.list.card 选择器采集列表卡片。"""
        selector = self.dom.list.card
        if not selector:
            return []
        return await page.query_selector_all(selector)

    async def parse_card(self, card, page) -> dict[str, Any]:
        """用 dom.list.* 选择器解析单张卡片。"""
        cfg = self.dom.list

        title = await self._safe_text(card, cfg.title)
        company = await self._safe_text(card, cfg.company)
        salary = await self._safe_text(card, cfg.salary)
        tags = await self._safe_texts(card, cfg.tags)
        href = await self._safe_attr(card, cfg.title_link, "href")

        # 如果主链接选择器没命中，尝试备选
        if not href:
            href = await self._safe_attr(
                card, "a[href*='job_detail'], a[href*='job']", "href")

        # 补全相对路径
        if href and not href.startswith("http"):
            base = self.profile.navigation.home.rstrip("/")
            # 去掉 ?ka=... 部分
            base = base.split("?")[0]
            href = base + href

        # 提取 job_id
        boss_job_id = None
        if href:
            m = re.search(r'job_detail/([a-zA-Z0-9]+)', href)
            if not m:
                m = re.search(r'/job/([a-zA-Z0-9]+)', href)
            boss_job_id = m.group(1) if m else None

        return {
            "boss_job_id": boss_job_id,
            "title": title,
            "company": company,
            "salary": salary,
            "tags": tags,
            "location": "",
            "recruiter_active": "",
            "job_url": href,
        }

    async def scrape_detail(self, page, url: str) -> dict[str, str]:
        """用 dom.detail.* 选择器提取详情（fallback 链）。
        
        按配置中的选择器列表顺序尝试，第一个命中的有效结果即返回。
        """
        result = {"description": "", "company_info": "", "recruiter_active": ""}

        try:
            # 导航到详情页
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            result["description"] = await self._try_selectors(
                page, self.dom.detail.description, min_length=20)
            result["company_info"] = await self._try_selectors(
                page, self.dom.detail.company, min_length=10)
            result["recruiter_active"] = await self._try_selectors(
                page, self.dom.detail.recruiter_active, min_length=0)
        except Exception:
            pass

        return result

    async def detect_captcha(self, page) -> bool:
        """检测是否出现验证码（基于 dom.captcha 配置）。"""
        captcha_cfg = self.dom.captcha

        # 选择器检测
        for sel in captcha_cfg.indicators:
            try:
                if await page.query_selector(sel):
                    return True
            except Exception:
                continue

        # 关键词检测
        try:
            body_text = await page.inner_text("body")
            if any(kw in body_text for kw in captcha_cfg.keywords):
                return True
        except Exception:
            pass

        return False

    async def detect_login_state(self, page) -> bool:
        """检测登录状态（基于 dom.login 配置）。"""
        login_cfg = self.dom.login
        url_lower = page.url.lower()

        # 检查是否在登录页
        is_login_page = any(p in url_lower for p in login_cfg.page_auth_patterns)
        if is_login_page or "about:blank" in url_lower:
            return False

        try:
            body_text = await page.inner_text("body")

            # 负面关键词（未登录）
            has_neg = any(kw in body_text for kw in login_cfg.text_negative)
            # 正面关键词（已登录）
            has_pos = any(kw in body_text for kw in login_cfg.text_positive)

            if has_neg and not has_pos:
                return False

            # 用户菜单元素
            if login_cfg.user_menu:
                menu_el = await page.query_selector(login_cfg.user_menu)
                if menu_el:
                    return True
        except Exception:
            pass

        return len(url_lower) > 20

    # === 内部工具方法 ===

    async def _safe_text(self, element, selector: str) -> str:
        """安全地查询子元素的文本。"""
        if not selector:
            return ""
        try:
            el = await element.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _safe_texts(self, element, selector: str) -> list[str]:
        """安全地查询多个子元素的文本列表。"""
        if not selector:
            return []
        try:
            els = await element.query_selector_all(selector)
            return [(await el.inner_text()).strip() for el in els]
        except Exception:
            return []

    async def _safe_attr(self, element, selector: str, attr: str) -> str:
        """安全地查询子元素的属性值。"""
        if not selector:
            return ""
        try:
            el = await element.query_selector(selector)
            if el:
                val = await el.get_attribute(attr)
                return val or ""
        except Exception:
            pass
        return ""

    async def _try_selectors(self, page, selectors: list[str],
                               min_length: int = 0) -> str:
        """按顺序尝试多个选择器，返回第一个有效结果。"""
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=3000)
                if el:
                    text = (await el.inner_text()).strip()
                    if text and len(text) >= min_length:
                        return text
            except Exception:
                continue
        return ""
```

- [ ] **Step 2: 编写测试**

注意：DOM 相关测试需要 mock Page 对象（不需要真实浏览器）。

```python
# src/tests/test_dom_reader.py
"""DomReader 测试 — 使用 mock Page 对象。"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from shared.engine.profile import SiteProfile, DomConfig, DomListConfig, NavigationConfig
from shared.engine.dom_reader import DomReader


def _make_mock_element(text: str = "", attr_value: str = ""):
    """创建 mock DOM 元素。"""
    el = AsyncMock()
    el.inner_text = AsyncMock(return_value=text)
    el.get_attribute = AsyncMock(return_value=attr_value)
    el.query_selector = AsyncMock(return_value=None)
    el.query_selector_all = AsyncMock(return_value=[])
    return el


def _make_mock_page(url: str = "https://www.zhipin.com/job_detail/abc123"):
    """创建 mock Page 对象。"""
    page = AsyncMock()
    page.url = url
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.inner_text = AsyncMock(return_value="")
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock(return_value=None)
    return page


def _make_profile(dom_overrides: dict | None = None) -> tuple[SiteProfile, DomReader]:
    """创建带标准 DOM 配置的 Profile 和 Reader。"""
    dom_dict = {
        "list": {
            "card": "li.job-card",
            "title": ".job-title",
            "title_link": "a.title-link",
            "company": ".company",
            "salary": ".salary",
            "tags": ".tag",
        },
        "pagination": {"next_button": ".next"},
        "detail": {
            "description": [".desc", ".detail-desc"],
            "company": [".company-info"],
            "recruiter_active": [".active"],
        },
        "captcha": {
            "indicators": [".captcha"],
            "keywords": ["验证码"],
        },
        "login": {
            "user_menu": ".user-menu",
            "page_auth_patterns": ["/user/", "login"],
            "text_positive": ["欢迎"],
            "text_negative": ["登录"],
        },
    }
    if dom_overrides:
        dom_dict.update(dom_overrides)

    from shared.engine.profile import _dict_to_profile
    profile = _dict_to_profile({"meta": {"name": "test"}, "dom": dom_dict})
    reader = DomReader(profile)
    return profile, reader


class TestParseCard:
    @pytest.mark.asyncio
    async def test_parse_normal_card(self):
        _, reader = _make_profile()

        card = _make_mock_element()
        card.query_selector.side_effect = lambda sel: (
            _make_mock_element("普工操作工") if sel == ".job-title" else
            _make_mock_element("某某制造") if sel == ".company" else
            _make_mock_element("4K-6K") if sel == ".salary" else
            AsyncMock(return_value=None)
        )
        card.query_selector_all.side_effect = lambda sel: (
            [_make_mock_element("包吃住"), _make_mock_element("五险")] if sel == ".tag" else []
        )

        link_el = _make_mock_element(attr_value="/job_detail/abc123")
        card.query_selector.side_effect = lambda sel: (
            link_el if sel == "a.title-link" else
            _make_mock_element("普工操作工") if sel == ".job-title" else
            _make_mock_element("某某制造") if sel == ".company" else
            _make_mock_element("4K-6K") if sel == ".salary" else
            AsyncMock(return_value=None)
        )

        page = _make_mock_page()
        result = await reader.parse_card(card, page)

        assert result["title"] == "普工操作工"
        assert result["company"] == "某某制造"
        assert result["salary"] == "4K-6K"
        assert result["tags"] == ["包吃住", "五险"]
        assert result["boss_job_id"] == "abc123"
        assert "zhipin.com" in result["job_url"]

    @pytest.mark.asyncio
    async def test_parse_empty_card(self):
        _, reader = _make_profile()
        card = _make_mock_element()
        card.query_selector.return_value = None
        card.query_selector_all.return_value = []

        page = _make_mock_page()
        result = await reader.parse_card(card, page)

        assert result["title"] == ""
        assert result["company"] == ""
        assert result["boss_job_id"] is None


class TestCaptchaDetection:
    @pytest.mark.asyncio
    async def test_detect_by_selector(self):
        _, reader = _make_profile()
        page = _make_mock_page()

        # 模拟检测到验证码元素
        page.query_selector.side_effect = lambda sel: (
            MagicMock() if sel == ".captcha" else None
        )

        assert await reader.detect_captcha(page) is True

    @pytest.mark.asyncio
    async def test_no_captcha(self):
        _, reader = _make_profile()
        page = _make_mock_page()
        page.query_selector.return_value = None
        page.inner_text.return_value = "正常页面内容"

        assert await reader.detect_captcha(page) is False


class TestLoginDetection:
    @pytest.mark.asyncio
    async def test_logged_in_by_menu(self):
        _, reader = _make_profile()
        page = _make_mock_page(url="https://www.zhipin.com/web/chat")

        page.query_selector.side_effect = lambda sel: (
            MagicMock() if sel == ".user-menu" else None
        )
        page.inner_text.return_value = "页面内容"

        assert await reader.detect_login_state(page) is True

    @pytest.mark.asyncio
    async def test_not_logged_in_on_login_page(self):
        _, reader = _make_profile()
        page = _make_mock_page(url="https://www.zhipin.com/user/login")

        assert await reader.detect_login_state(page) is False
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/test_dom_reader.py -v`

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/shared/engine/dom_reader.py src/tests/test_dom_reader.py
git commit -m "feat(engine): add DomReader with config-driven selectors"
```

---

## Task 5: 过滤链

**Files:**
- Create: `src/shared/engine/filter_chain.py`
- Test: `src/tests/test_filter_chain.py`

**目标:** 解释执行 Profile.filters 规则列表，每条规则独立可插拔。

- [ ] **Step 1: 实现过滤链**

```python
# src/shared/engine/filter_chain.py
"""声明式过滤器 — 从 YAML 规则构建过滤链，每条规则独立可插拔。

内置规则类型:
- salary_threshold: 薪资下限过滤
- contains_any: 黑名单关键词匹配  
- inactive_days: 招聘者活跃度过滤

扩展方式: 实现 BaseFilter.check() 接口，在 RULE_TYPES 注册。
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from shared.engine.profile import SiteProfile, FilterRule
from shared.engine.adapter_protocol import DefaultAdapter


class BaseFilter(ABC):
    """过滤器基类 — 所有规则类型必须实现此接口。"""

    @abstractmethod
    def check(self, job: dict[str, Any], rule: FilterRule,
              profile: SiteProfile) -> tuple[bool, str]:
        """检查职位数据是否符合规则。
        
        Returns:
            (should_skip, reason) — True 表示应跳过该职位
        """
        ...


class SalaryThresholdFilter(BaseFilter):
    """薪资下限过滤器 — 薪资低于阈值则跳过。"""

    def check(self, job: dict, rule: FilterRule,
              profile: SiteProfile) -> tuple[bool, str]:
        adapter = DefaultAdapter()
        salary_min = adapter.parse_salary(job.get(rule.field, ""))
        threshold = profile.get_global(rule.config_key, 0)

        if salary_min is not None and salary_min < threshold:
            reason = rule.reason_template.format(
                value=job.get(rule.field, ""), threshold=threshold)
            return True, reason
        return False, ""


class ContainsAnyFilter(BaseFilter):
    """黑名单关键词过滤器 — 字段包含任一关键词则跳过。"""

    def check(self, job: dict, rule: FilterRule,
              profile: SiteProfile) -> tuple[bool, str]:
        field_val = job.get(rule.field, "")
        if not field_val:
            return False, ""

        blacklist = profile.get_global(rule.source, [])

        check_text = field_val.lower() if rule.case_insensitive else field_val
        for word in blacklist:
            w = word.lower() if rule.case_insensitive else word
            if w in check_text:
                reason = rule.reason_template.format(matched=word)
                return True, reason
        return False, ""


class InactiveDaysFilter(BaseFilter):
    """招聘者活跃度过滤器 — 超过最大未活跃天数则跳过。"""

    def check(self, job: dict, rule: FilterRule,
              profile: SiteProfile) -> tuple[bool, str]:
        adapter = DefaultAdapter()
        active_text = job.get(rule.field, "")
        inactive_days = adapter.parse_inactive_days(active_text)

        max_days = profile.get_global(rule.max_days_key, 7)

        if inactive_days is not None and inactive_days > max_days:
            reason = rule.reason_template.format(value=inactive_days)
            return True, reason
        return False, ""


class FilterChain:
    """有序过滤器链 — 规则来自 SiteProfile.filters 配置。
    
    按顺序执行所有规则，任一命中（返回 skip=True）即停止并返回原因。
    """

    # 内置规则类型注册表 — 扩展新类型只需在此注册
    _RULE_TYPES: dict[type[BaseFilter]] = {
        "salary_threshold": SalaryThresholdFilter,
        "contains_any": ContainsAnyFilter,
        "inactive_days": InactiveDaysFilter,
    }

    def __init__(self, rules: list[FilterRule], profile: SiteProfile):
        self.rules = rules
        self.profile = profile
        self._instances: list[tuple[FilterRule, BaseFilter]] = []

        for rule in rules:
            filter_cls = self._RULE_TYPES.get(rule.type)
            if filter_cls:
                self._instances.append((rule, filter_cls()))
            else:
                # 未知规则类型，记录警告但跳过
                import logging
                logging.getLogger("filter_chain").warning(
                    "未知过滤规则类型: %s (id=%s)", rule.type, rule.id)

    def evaluate(self, job: dict[str, Any]) -> tuple[bool, str]:
        """按顺序执行所有规则。
        
        Returns:
            (should_skip, reason) — True 表示应跳过该职位及原因
        """
        for rule, instance in self._instances:
            skip, reason = instance.check(job, rule, self.profile)
            if skip:
                return True, reason
        return False, ""

    @classmethod
    def register_rule_type(cls, name: str, filter_class: type[BaseFilter]):
        """注册新的规则类型。"""
        cls._RULE_TYPES[name] = filter_class
```

- [ ] **Step 2: 编写测试**

```python
# src/tests/test_filter_chain.py
"""FilterChain 测试。"""
import pytest
from shared.engine.profile import SiteProfile, FilterRule, _dict_to_profile
from shared.engine.filter_chain import (
    FilterChain, SalaryThresholdFilter, ContainsAnyFilter, InactiveDaysFilter,
)


def _make_profile(filters_yaml: list[dict]) -> SiteProfile:
    return _dict_to_profile({
        "meta": {"name": "test"},
        "filters": filters_yaml,
    })


class TestSalaryThresholdFilter:
    def test_below_threshold(self):
        profile = _make_profile([{
            "id": "sal", "type": "salary_threshold",
            "field": "salary", "config_key": "pre_filters.min_salary",
            "reason_template": "薪资 {value} 低于 {threshold}"
        }])
        profile._global_config = {"pre_filters": {"min_salary": 3000}}

        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"salary": "2K-3K"})
        assert skip is True
        assert "2000" in reason or "2K" in reason

    def test_above_threshold(self):
        profile = _make_profile([{
            "id": "sal", "type": "salary_threshold",
            "field": "salary", "config_key": "pre_filters.min_salary",
            "reason_template": "低薪"
        }])
        profile._global_config = {"pre_filters": {"min_salary": 3000}}

        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"salary": "5K-8K"})
        assert skip is False

    def test_no_salary_info(self):
        profile = _make_profile([{
            "id": "sal", "type": "salary_threshold",
            "field": "salary", "config_key": "x.y", "reason_template": "低"
        }])

        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"salary": ""})
        assert skip is False


class TestContainsAnyFilter:
    def test_match_blacklist_word(self):
        profile = _make_profile([{
            "id": "title", "type": "contains_any",
            "field": "title", "case_insensitive": True,
            "source": "pre_filters.title_blacklist",
            "reason_template": "标题含 '{matched}'"
        }])
        profile._global_config = {"pre_filters": {"title_blacklist": ["高级", "资深"]}}

        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"title": "高级Java工程师"})
        assert skip is True
        assert "高级" in reason

    def test_no_match(self):
        profile = _make_profile([{
            "id": "title", "type": "contains_any",
            "field": "title", "source": "x.blacklist",
            "reason_template": "命中"
        }])
        profile._global_config = {"x": {"blacklist": ["金融"]}}

        chain = FilterChain(profile.filters, profile)
        skip, _ = chain.evaluate({"title": "普工操作工"})
        assert skip is False

    def test_case_insensitive(self):
        profile = _make_profile([{
            "id": "co", "type": "contains_any",
            "field": "company", "case_insensitive": True,
            "source": "co.blacklist",
            "reason_template": "公司类型含 '{matched}'"
        }])
        profile._global_config = {"co": {"blacklist": ["保险"]}}

        chain = FilterChain(profile.filters, profile)
        skip, _ = chain.evaluate({"company": "XX人寿保险有限公司"})
        assert skip is True


class TestInactiveDaysFilter:
    def test_exceeds_max_days(self):
        profile = _make_profile([{
            "id": "active", "type": "inactive_days",
            "field": "recruiter_active",
            "max_days_key": "runtime.max_inactive_days",
            "reason_template": "已 {value} 天未活跃"
        }])
        profile._global_config = {"runtime": {"max_inactive_days": 7}}

        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"recruiter_active": "10天前活跃"})
        assert skip is True
        assert "10" in reason

    def test_within_limit(self):
        profile = _make_profile([{
            "id": "active", "type": "inactive_days",
            "field": "recruiter_active",
            "max_days_key": "runtime.max_inactive_days",
            "reason_template": "超期"
        }])
        profile._global_config = {"runtime": {"max_inactive_days": 7}}

        chain = FilterChain(profile.filters, profile)
        skip, _ = chain.evaluate({"recruiter_active": "3天前活跃"})
        assert skip is False


class TestChainOrdering:
    def test_first_matching_rule_wins(self):
        """多条规则时，第一条命中的生效。"""
        profile = _make_profile([
            {"id": "sal", "type": "salary_threshold",
             "field": "salary", "config_key": "x.sal", "reason_template": "低薪"},
            {"id": "title", "type": "contains_any",
             "field": "title", "source": "x.bl", "reason_template": "黑名单"},
        ])
        profile._global_config = {"x": {"sal": 99999, "bl": ["xx"]}}

        chain = FilterChain(profile.filters, profile)
        # 薪资不会触发（阈值为 99999），应该走到第二条
        skip, reason = chain.evaluate({"salary": "4K", "title": "xx工程师"})
        assert skip is True
        assert "黑名单" in reason or "xx" in reason

    def test_empty_rules_passes(self):
        profile = _make_profile([])
        chain = FilterChain(profile.filters, profile)
        skip, reason = chain.evaluate({"title": "anything"})
        assert skip is False
        assert reason == ""

    def test_unknown_rule_type_skipped(self):
        profile = _make_profile([{
            "id": "weird", "type": "nonexistent_type",
            "field": "x", "reason_template": "x"
        }])
        chain = FilterChain(profile.filters, profile)
        skip, _ = chain.evaluate({"x": "anything"})
        # 未知规则被跳过，不应阻止
        assert skip is False
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/test_filter_chain.py -v`

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/shared/engine/filter_chain.py src/tests/test_filter_chain.py
git commit -m "feat(engine): add FilterChain with pluggable rule types"
```

---

## Task 6: 报告生成器

**Files:**
- Create: `src/shared/engine/report_builder.py`
- Test: `src/tests/test_report_builder.py`

**目标:** 报告内容和评估维度完全由 Profile.report 驱动。

- [ ] **Step 1: 实现报告生成器**

```python
# src/shared/engine/report_builder.py
"""声明式报告生成器 — 维度来自 SiteProfile.report.dimensions。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.engine.profile import SiteProfile


class ReportBuilder:
    """动态报告生成器 — 内容和格式完全由配置决定。"""

    def __init__(self, profile: SiteProfile):
        self.profile = profile
        self.score_threshold = profile.report.score_threshold
        self.dimensions = profile.report.dimensions

    def generate(self, jobs: list[dict[str, Any]],
                 city: str | None = None,
                 top: int | None = None) -> str:
        """生成推荐报告。
        
        Args:
            jobs: 已分析的职位列表（需包含 match_score 等字段）
            city: 可选城市筛选
            top: 最大条数
            
        Returns:
            Markdown 格式的报告文本
        """
        # 筛选符合条件的职位
        filtered = [j for j in jobs
                    if j.get("match_score", 0) >= self.score_threshold]

        if city:
            filtered = [j for j in filtered if j.get("city") == city]

        if top:
            filtered = filtered[:top]

        if not filtered:
            return "暂无符合条件的推荐职位。"

        lines = [
            f"# {self.profile.meta.display_name} 求职推荐报告",
            f"生成时间: {datetime.now().isoformat()}",
            f"匹配分数 ≥ {self.score_threshold}",
            f"共 {len(filtered)} 条推荐职位",
            "",
        ]

        for i, j in enumerate(filtered, 1):
            lines.extend(self._format_job_entry(i, j))
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _format_job_entry(self, index: int, job: dict) -> list[str]:
        """格式化单个职位条目 — 维度名从配置动态读取。"""
        score = job.get("match_score", 0)
        lines = [
            f"### {index}. [{job.get('title', '')}]({job.get('job_url', '')}) "
            f"★{score}/10",
            f"**{job.get('company', '')}** | {job.get('salary', '')} "
            f"| {job.get('city', '')} | 活跃: {job.get('recruiter_active', '未知')}",
            "",
        ]

        # 福利维度行 — 从配置动态生成
        benefit_lines = []
        missing_labels = []
        for dim in self.dimensions:
            val = job.get(dim.key, 0)
            label = dim.label
            if val == 1:
                benefit_lines.append(f"✓ {label}")
            elif val == -1:
                benefit_lines.append(f"✗ {label}")
                missing_labels.append(label)
            else:
                benefit_lines.append(f"⚠ {label}未提及")
                missing_labels.append(label)

        lines.append("> " + "\n> ".join(benefit_lines))
        lines.append("")

        if missing_labels:
            missing_text = "、".join(missing_labels)
            lines.append(f"⚠ 缺失: {missing_text}，投递时可主动询问")
            lines.append("")

        if job.get("ai_reason"):
            lines.append(f"分析: {job['ai_reason']}")
            lines.append("")

        return lines
```

- [ ] **Step 2: 编写测试**

```python
# src/tests/test_report_builder.py
"""ReportBuilder 测试。"""
import pytest
from shared.engine.profile import SiteProfile, ReportConfig, ReportDimension, _dict_to_profile
from shared.engine.report_builder import ReportBuilder


def _make_report_profile(dimensions: list[dict] | None = None) -> ReportBuilder:
    dims = dimensions or [
        {"key": "five_insurance", "label": "五险一金"},
        {"key": "room_board", "label": "包食宿"},
    ]
    profile = _dict_to_profile({
        "meta": {"name": "zhipin", "display_name": "BOSS 直聘"},
        "report": {
            "score_threshold": 6,
            "dimensions": dims,
        },
    })
    return ReportBuilder(profile)


class TestGenerate:
    def test_basic_report(self):
        builder = _make_report_profile()
        jobs = [{
            "title": "普工", "company": "XX厂", "salary": "4K-6K",
            "city": "深圳", "match_score": 8,
            "five_insurance": 1, "room_board": -1,
            "job_url": "http://example.com/1",
            "recruiter_active": "今日活跃",
        }]
        report = builder.generate(jobs)

        assert "BOSS 直聘" in report
        assert "普工" in report
        assert "★8/10" in report
        assert "✓ 五险一金" in report
        assert "✗ 包食宿" in report
        assert "缺失: 包食宿" in report

    def test_below_threshold_filtered(self):
        builder = _make_report_profile()
        jobs = [{"title": "低分职", "match_score": 3}]
        report = builder.generate(jobs)

        assert "暂无" in report

    def test_empty_jobs(self):
        builder = _make_report_profile()
        report = builder.generate([])

        assert "暂无" in report

    def test_custom_dimensions(self):
        builder = _make_report_profile([{"key": "remote_ok", "label": "可远程"}])
        jobs = [{
            "title": "远程岗", "match_score": 7,
            "remote_ok": 1, "job_url": "http://x.com",
        }]
        report = builder.generate(jobs)

        assert "✓ 可远程" in report
        assert "五险一金" not in report  # 自定义维度替换了默认

    def test_top_limit(self):
        builder = _make_report_profile()
        jobs = [
            {"title": f"职位{i}", "match_score": 8,
             "five_insurance": 1, "room_board": 1,
             "job_url": f"http://x.com/{i}", "company": "C",
             "salary": "5K", "city": "深圳", "recruiter_active": "今日"}
            for i in range(5)
        ]
        report = builder.generate(jobs, top=2)

        assert "共 2 条" in report
        assert "职位0" in report
        assert "职位1" in report
        assert "职位2" not in report

    def test_city_filter(self):
        builder = _make_report_profile()
        jobs = [
            {"title": "深圳岗", "match_score": 8, "city": "深圳",
             "five_insurance": 1, "room_board": 1, "job_url": "http://x.com/1",
             "company": "C", "salary": "5K", "recruiter_active": "今日"},
            {"title": "广州岗", "match_score": 9, "city": "广州",
             "five_insurance": 1, "room_board": 1, "job_url": "http://x.com/2",
             "company": "C", "salary": "5K", "recruiter_active": "今日"},
        ]
        report = builder.generate(jobs, city="深圳")

        assert "深圳岗" in report
        assert "广州岗" not in report
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/test_report_builder.py -v`

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/shared/engine/report_builder.py src/tests/test_report_builder.py
git commit -m "feat(engine): add ReportBuilder with dynamic dimensions"
```

---

## Task 7: 主引擎 ScrapingEngine

**Files:**
- Create: `src/shared/engine/scraping_engine.py`
- Test: `src/tests/test_scraping_engine.py`

**目标:** 流程编排引擎，串联 UrlBuilder + DomReader + FilterChain + 存储层。

- [ ] **Step 1: 实现主引擎**

```python
# src/shared/engine/scraping_engine.py
"""通用爬取主引擎 — 读取 SiteProfile，按声明式流程执行。

这是唯一"知道怎么爬"的代码，但不包含任何业务逻辑。
所有行为参数来自 SiteProfile 配置。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from shared.engine.profile import SiteProfile
from shared.engine.url_builder import UrlBuilder
from shared.engine.dom_reader import DomReader
from shared.engine.filter_chain import FilterChain
from shared.engine.report_builder import ReportBuilder
from shared.engine.adapter_protocol import DefaultAdapter
from shared.delay import delay
from shared.logging_config import get_logger
from browser_agent.core.anti_detect import human_scroll, random_delay

logger = get_logger("engine")


class CityResult:
    """单城市搜索结果。"""

    def __init__(self, city: str, searched: int = 0, stored: int = 0,
                 skipped: int = 0, elapsed: float = 0):
        self.city = city
        self.searched = searched
        self.stored = stored
        self.skipped = skipped
        self.elapsed = elapsed

    def to_dict(self) -> dict:
        return {
            "searched": self.searched,
            "stored": self.stored,
            "skipped": self.skipped,
            "elapsed": self.elapsed,
        }


class ScrapingEngine:
    """通用爬取引擎 — 通过 SiteProfile 驱动全部行为。"""

    def __init__(self, profile: SiteProfile):
        self.profile = profile
        self.url_builder = UrlBuilder(profile)
        self.dom_reader = DomReader(profile)
        self.filter_chain = FilterChain(profile.filters, profile)
        self.report_builder = ReportBuilder(profile)
        self.adapter = DefaultAdapter()

    async def run(self, cities: list[str] | None = None,
                  keywords: list[str] | None = None,
                  max_detail: int | None = None,
                  headless: bool = False) -> dict[str, Any]:
        """主入口：导航 → 登录检测 → 逐城市搜索 → 返回结果。

        Args:
            cities: 目标城市列表，None 则从配置自动选取
            keywords: 搜索关键词列表
            max_detail: 每城最大入库数
            headless: 是否无头模式

        Returns:
            {city: CityResult.to_dict(), ...}
        """
        from modes.zhipin.storage import init_db, get_searched_cities
        from modes.zhipin.city_codes import get_city_code
        from playwright.async_api import async_playwright
        from browser_agent.core.anti_detect import STEALTH_SCRIPT, ANTI_REDIRECT_SCRIPT, build_browser_kwargs

        cfg_dict = self.profile._global_config or {}
        init_db()

        if max_detail is None:
            max_detail = cfg_dict.get("runtime", {}).get("max_detail_pages_per_city", 30)

        if cities is None:
            searched = get_searched_cities()
            all_cities = []
            for p in ["priority_1", "priority_2", "priority_3", "priority_4"]:
                for c in cfg_dict.get("cities", {}).get(p, []):
                    if c not in searched:
                        all_cities.append(c)
            cities_per_session = cfg_dict.get("runtime", {}).get("cities_per_session", 3)
            cities = all_cities[:cities_per_session]

        if not cities:
            return {"error": "没有需要搜索的城市"}

        result: dict[str, Any] = {}
        total_start = time.time()

        async with async_playwright() as p:
            kwargs = build_browser_kwargs(cfg_dict, headless)
            context = await p.chromium.launch_persistent_context(**kwargs)
            await context.add_init_script(STEALTH_SCRIPT)
            await context.add_init_script(ANTI_REDIRECT_SCRIPT)
            first_page = context.pages[0] if context.pages else await context.new_page()

            try:
                # 1. 导航首页
                await first_page.goto(
                    self.url_builder.get_home_url(),
                    wait_until="domcontentloaded"
                )
                await delay("login_wait")

                # 2. 登录检测
                if not await self._check_login(first_page):
                    logger.info("等待用户登录...")
                    await self._wait_for_login(first_page)

                # 3. 逐城市搜索
                for idx, city in enumerate(cities, 1):
                    logger.info("[%d/%d] %s 搜索中...", idx, len(cities), city)
                    stats = await self._search_city(
                        first_page, city, keywords, max_detail)
                    result[city] = stats.to_dict()
                    logger.info(
                        "[%d/%d] %s | 搜到 %d 条 | 入库 %d 条 | 耗时 %.0f秒",
                        idx, len(cities), city,
                        stats.searched, stats.stored, stats.elapsed)

            finally:
                await context.close()

        total_elapsed = time.time() - total_start
        total_stored = sum(r.get("stored", 0) for r in result.values() if isinstance(r, dict))
        total_searched = sum(r.get("searched", 0) for r in result.values() if isinstance(r, dict))

        logger.info(
            "搜索完成 | 总耗时 %.0f秒 | 共搜到 %d 条，入库 %d 条",
            total_elapsed, total_searched, total_stored)

        return result

    async def generate_report(self, *args, **kwargs) -> str:
        """委托给 ReportBuilder。"""
        from modes.zhipin.storage import get_jobs, JobQuery
        jobs = get_jobs(JobQuery(status="analyzed", exclude_ignored=True), *args, **kwargs)
        return self.report_builder.generate(jobs, *args, **kwargs)

    # === 内部方法 ===

    async def _check_login(self, page) -> bool:
        """检查当前页面登录状态。"""
        return await self.dom_reader.detect_login_state(page)

    async def _wait_for_login(self, page, timeout: int = 300) -> bool:
        """等待用户手动登录。"""
        logger.info("请在浏览器中登录...")
        try:
            async with asyncio.timeout(timeout):
                while True:
                    await delay("login_poll")
                    if await self._check_login(page):
                        logger.info("登录成功")
                        return True
        except asyncio.TimeoutError:
            logger.error("登录超时")
            return False

    async def _search_city(self, page, city: str,
                           keywords: list[str] | None,
                           max_detail: int) -> CityResult:
        """单城市完整搜索流程。"""
        from modes.zhipin.city_codes import get_city_code
        from modes.zhipin.keyword_strategy import get_initial_keyword, get_keywords_for_city
        from modes.zhipin.storage import insert_job, update_search_log

        t_start = time.time()
        city_stored = 0
        city_skipped = 0
        city_searched = 0

        update_search_log(city, "in_progress")

        city_code = get_city_code(city)
        if not city_code:
            logger.error("未知城市: %s", city)
            return CityResult(city, elapsed=time.time() - t_start)

        # 确定关键词
        if keywords is None:
            probe_kw = get_initial_keyword()
            search_kws = [probe_kw]
        else:
            search_kws = keywords

        for kw in search_kws:
            if city_stored >= max_detail:
                break

            # 构建搜索 URL 并导航
            search_urls = self.url_builder.get_all_search_urls(city_code, kw)
            navigated = False
            for _priority, url in search_urls:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await delay("page_stable")
                    if "about:blank" not in page.url:
                        navigated = True
                        break
                except Exception as e:
                    logger.debug("导航失败: %s", e)

            if not navigated:
                continue

            # 人为滚动
            await human_scroll(page)

            # 采集卡片
            cards = await self.dom_reader.collect_cards(page)
            city_searched += len(cards)

            for card in cards:
                if city_stored >= max_detail:
                    break

                job = await self.dom_reader.parse_card(card, page)
                job["city"] = city

                # 过滤
                skip, reason = self.filter_chain.evaluate(job)
                if skip:
                    city_skipped += 1
                    logger.debug("跳过 [%s]: %s", job.get("title", ""), reason)
                    continue

                # 入库
                if insert_job(job):
                    city_stored += 1

            await random_delay()

        elapsed = time.time() - t_start
        update_search_log(city, "done", city_stored)

        return CityResult(
            city=city,
            searched=city_searched,
            stored=city_stored,
            skipped=city_skipped,
            elapsed=elapsed,
        )
```

- [ ] **Step 2: 编写测试**

```python
# src/tests/test_scraping_engine.py
"""ScrapingEngine 集成测试 — 使用 mock 对象。"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared.engine.profile import SiteProfile, _dict_to_profile
from shared.engine.scraping_engine import ScrapingEngine, CityResult


def _make_engine(global_cfg: dict | None = None) -> ScrapingEngine:
    profile = _dict_to_profile({
        "meta": {"name": "zhipin", "display_name": "BOSS 直聘"},
        "navigation": {
            "home": "https://www.zhipin.com/?ka=header-home",
            "login": "https://www.zhipin.com/web/user/",
        },
        "urls": {"search": [{"template": "/job?c={city_code}&q={keyword}", "priority": 1}]},
        "dom": {
            "list": {"card": "li.card", "title": ".t", "title_link": "a.l",
                     "company": ".c", "salary": ".s", "tags": ".tag"},
            "pagination": {"next_button": ".next"},
            "detail": {"description": [".d"], "company": [".ci"], "recruiter_active": [".a"]},
            "captcha": {"indicators": [], "keywords": []},
            "login": {"user_menu": ".user", "page_auth_patterns": ["/user/"],
                      "text_positive": ["欢迎"], "text_negative": ["登录"]},
        },
        "filters": [],
        "report": {"score_threshold": 6, "dimensions": []},
    })
    if global_cfg:
        profile._global_config = global_cfg
    return ScrapingEngine(profile)


class TestEngineInit:
    def test_components_created(self):
        engine = _make_engine()
        assert engine.url_builder is not None
        assert engine.dom_reader is not None
        assert engine.filter_chain is not None
        assert engine.report_builder is not None

    def test_profile_passed_through(self):
        cfg = {"runtime": {"cities_per_session": 2}}
        engine = _make_engine(cfg)
        assert engine.profile._global_config is cfg


class TestCityResult:
    def test_to_dict(self):
        r = CityResult(city="深圳", searched=10, stored=5, skipped=3, elapsed=1.5)
        d = r.to_dict()
        assert d["city"] == "深圳"  # CityResult.to_dict 不含 city？需要确认
        assert d["searched"] == 10
        assert d["stored"] == 5
        assert d["skipped"] == 3
        assert d["elapsed"] == 1.5


class TestFilterIntegration:
    def test_filter_chain_works_in_engine(self):
        profile = _dict_to_profile({
            "meta": {"name": "t"},
            "filters": [{
                "id": "sal", "type": "salary_threshold",
                "field": "salary", "config_key": "x.min_sal",
                "reason_template": "低"
            }],
        })
        profile._global_config = {"x": {"min_sal": 5000}}
        engine = __import__("shared.engine.scraping_engine", fromlist=["ScrapingEngine"]).ScrapingEngine(profile)

        # 低薪职位应被过滤
        skip, _ = engine.filter_chain.evaluate({"salary": "3K-4K"})
        assert skip is True

        # 高薪职位应通过
        skip, _ = engine.filter_chain.evaluate({"salary": "6K-8K"})
        assert skip is False
```

- [ ] **Step 3: 运行测试**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/test_scraping_engine.py -v`

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add src/shared/engine/scraping_engine.py src/tests/test_scraping_engine.py
git commit -m "feat(engine): add ScrapingEngine main orchestrator"
```

---

## Task 8: 创建 zhipin.yaml 站点画像

**Files:**
- Create: `profiles/zhipin.yaml`
- Test: 验证 Profile 能正确加载

**目标:** 将现有 selectors.py、pre_filter.py、scraper.py 中的硬编码配置逆向提取为 YAML。

- [ ] **Step 1: 创建 BOSS 直聘站点画像**

```yaml
# profiles/zhipin.yaml
# BOSS 直聘站点画像 — 所有选择器、过滤规则、URL、报告维度集中声明于此。
# 修改此文件即可适应 BOSS 直聘页面改版或调整业务规则，无需改动 Python 代码。

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
    title: ".job-name, .job-title, [class*='job-name'], [class*='job-title']"
    title_link: "a.job-name, a.job-title, .job-name a, .job-title a"
    company: ".boss-name, .company-name, [class*='boss-name'], [class*='company-name']"
    salary: ".job-salary, .salary, [class*='salary']"
    tags: ".tag-list li, .job-tags li, .tags li, [class*='tag']"

  pagination:
    next_button: ".options-pages .next, .page-next, .page .next, .pagination-next, button.next"
    disabled_class_contains: "disabled"

  detail:
    description:
      - ".job-sec-text"
      - ".job-detail-section-text"
      - ".job-detail .text"
      - ".detail-section .job-detail-box"
      - ".job-detail-content"
      - "[class*='job-detail']"
      - "[class*='job-sec']"
      - "[class*='description']"
      - "[class*='detail-text']"
      - ".position-detail"
      - ".job-content"
      - ".description-content"
    company:
      - ".company-info"
      - ".detail-business-info"
      - ".company-info-box"
      - "[class*='company-info']"
      - "[class*='business']"
      - ".company-detail"
      - ".company-content"
    recruiter_active:
      - ".boss-active-time"
      - ".boss-name-time"
      - ".boss-online-tag"
      - ".boss-description"
      - "[class*='boss-active']"
      - "[class*='active-time']"
      - "[class*='boss-name']"
      - ".recruiter-info"
      - ".recruiter-active"
    panel_salary: >
      .job-detail-box .job-detail-salary,
      .detail-salary,
      [class*='salary'],
      .popup-salary

  captcha:
    indicators:
      - ".geetest_panel"
      - ".captcha-box"
      - ".verify-box"
      - ".nc_wrapper"
      - "iframe[src*='captcha']"
      - "iframe[src*='geetest']"
      - "[class*='captcha']"
      - ".sec-captcha"
      - ".security-verify"
      - ".verify-code"
    keywords:
      - "验证码"
      - "安全验证"
      - "滑块验证"
      - "请完成验证"
      - "请点击验证"
      - "安全校验"

  login:
    user_menu: ".nav-user-menu, .user-avatar, .header-user, .nav-user"
    page_auth_patterns:
      - "/user/"
      - "passport"
      - "login"
      - "/account/"
    text_positive:
      - "欢迎回来"
      - "我的"
      - "退出登录"
      - "个人中心"
    text_negative:
      - "登录"
      - "注册"
      - "扫码"
      - "验证码登录"
      - "密码登录"

filters:
  # ===== 过滤规则（有序列表，按顺序执行，任一命中即跳过）=====
  # 新增规则: 在此处添加一条即可，无需改代码
  # 调整顺序: 移动 YAML 行位置即可

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
    reason_template: "标题含 '{matched}'（门槛高于大专）"

  - id: company_blacklist
    type: contains_any
    field: company
    case_insensitive: true
    source: pre_filters.company_blacklist
    reason_template: "公司类型含 '{matched}'（大概率无固定作息）"

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

- [ ] **Step 2: 验证 Profile 加载正确性**

编写快速验证脚本：

```python
# 临时验证（运行后删除）
from shared.engine.profile import load_profile
from shared.config import get_config

cfg = get_config()
profile = load_profile("zhipin", global_config=cfg)

assert profile.meta.name == "zhipin"
assert "?ka=header-home" in profile.navigation.home
assert len(profile.urls.search) == 2
assert profile.dom.list.card != ""
assert len(profile.dom.detail.description) > 5
assert len(profile.filters) == 4
assert len(profile.report.dimensions) == 3

# 验证全局配置引用
assert profile.get_global("pre_filters.min_salary") == 3000
assert profile.get_global("runtime.max_inactive_days") == 7

print("✓ zhipin.yaml 加载验证通过")
print(f"  选择器: list.card={profile.dom.list.card[:30]}...")
print(f"  过滤规则: {len(profile.filters)} 条")
print(f"  报告维度: {[d.label for d in profile.report.dimensions]}")
```

Run: `cd d:\G\github\游览器agent ; python -c "上述验证代码"`

Expected: 输出 ✓ 并打印摘要信息

- [ ] **Step 3: Commit**

```bash
git add profiles/zhipin.yaml
git commit -m "feat(profiles): add BOSS直聘 site profile (zhipin.yaml)"
```

---

## Task 9: 入口集成 — 切换到新引擎

**Files:**
- Modify: `src/modes/zhipin/__init__.py`
- Test: 验证 CLI 入口正常工作

**目标:** 将 `modes/zhipin/__init__.py` 的入口转发到新引擎，保持对外 API 不变。

- [ ] **Step 1: 修改入口文件**

修改 `src/modes/zhipin/__init__.py`，在保留原有导出的同时增加新引擎入口：

```python
# 在文件顶部新增导入（条件导入，避免循环依赖）
def _get_engine():
    """延迟导入引擎，避免模块加载时的循环依赖。"""
    from shared.engine import ScrapingEngine, load_profile
    from shared.config import get_config
    profile = load_profile("zhipin", global_config=get_config())
    return ScrapingEngine(profile)
```

在 `browse` 命令分支中使用新引擎的 URL：

```python
# 原: await ctrl.navigate("https://www.zhipin.com/?ka=header-home")
# 改为:
engine = _get_engine()
await ctrl.navigate(engine.url_builder.get_home_url())
```

在 `search` 命令分支中使用新引擎：

```python
# 原: from modes.zhipin.scraper import search_jobs; result = search_jobs(...)
# 改为:
engine = _get_engine()
result = await engine.run(cities=args.city, keywords=args.keyword)
```

- [ ] **Step 2: 运行冒烟测试**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/ -v --ignore=src/tests/integration`

Expected: 全部 PASS（包括已有的 118 个测试 + 新增的引擎测试）

- [ ] **Step 3: Commit**

```bash
git add src/modes/zhipin/__init__.py
git commit -m "refactor(zhipin): switch entry point to declarative engine"
```

---

## Task 10: 清理废弃代码

**Files:**
- Deprecate: `src/modes/zhipin/selectors.py`
- Deprecate: `src/modes/zhipin/pre_filter.py`
- Slim: `src/modes/zhipin/scraper.py`

**目标:** 标记旧代码为 deprecated，精简 scraper.py 为兼容薄层。

- [ ] **Step 1: 给废弃文件加 deprecation 警告**

```python
# selectors.py 顶部添加
import warnings
warnings.warn(
    "selectors.py 已废弃，选择器已迁移至 profiles/zhipin.yaml 的 dom 段。",
    DeprecationWarning,
    stacklevel=2,
)
```

```python
# pre_filter.py 顶部添加
import warnings
warnings.warn(
    "pre_filter.py 已废弃，过滤规则已迁移至 profiles/zhipin.yaml 的 filters 段。",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 2: 精简 scraper.py**

将 scraper.py 中被引擎替代的核心函数标记为 deprecated：

```python
# scraper.py 中以下函数标记为 deprecated:
# - search_jobs() → 使用 ScrapingEngine.run()
# - should_skip_job() → 使用 FilterChain.evaluate()
# - _collect_list_page() → 使用 DomReader.collect_cards() + parse_card()
# - _scrape_detail() → 使用 DomReader.scrape_detail()
# - _detect_captcha() → 使用 DomReader.detect_captcha()
# - is_logged_in() → 使用 DomReader.detect_login_state()
```

保留但不建议使用的函数加 `@deprecated` 装饰器：

```python
import warnings
def deprecated(func):
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{func.__name__} 已废弃，请使用 ScrapingEngine / DomReader / FilterChain",
            DeprecationWarning,
            stacklevel=2,
        )
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper
```

- [ ] **Step 3: 最终测试验证**

Run: `cd d:\G\github\游览器agent ; python -m pytest src/tests/ -v`

Expected: 全部 PASS（可能有 deprecation warning，不算失败）

- [ ] **Step 4: Commit**

```bash
git add src/modes/zhipin/selectors.py src/modes/zhipin/pre_filter.py src/modes/zhipin/scraper.py
git commit -m "chore: deprecate hardcoded selectors and filters in favor of YAML profiles"
```

---

## 验收检查清单

实施完成后逐项确认：

- [ ] `profiles/zhipin.yaml` 包含当前全部选择器/过滤规则/URL/报告配置
- [ ] `ScrapingEngine.run()` 输出与原 `scraper.search_jobs()` 结果一致
- [ ] 新增过滤条件只需编辑 `zhipin.yaml` 的 `filters` 段（不改 Python）
- [ ] BOSS 直聘改版换选择器只需编辑 `zhipin.yaml` 的 `dom` 段（不改 Python）
- [ ] 报告加维度只需编辑 `zhipin.yaml` 的 `report.dimensions`（不改 Python）
- [ ] 所有现有测试通过（118+ 新增测试）
- [ ] 引擎核心代码 ≤ 200 行（scraping_engine.py）
- [ ] `selectors.py` 和 `pre_filter.py` 标记为 deprecated
