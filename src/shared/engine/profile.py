"""站点画像数据模型 — 从 YAML 声明式配置加载站点全部行为参数。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetaConfig:
    """站点元信息配置：名称、显示名称、版本号。"""
    name: str = ""
    display_name: str = ""
    version: int = 1


@dataclass
class NavigationConfig:
    """导航配置：首页和登录页 URL。"""
    home: str = ""
    login: str = ""


@dataclass
class UrlTemplate:
    """URL 模板：包含模板字符串和优先级。"""
    template: str = ""
    priority: int = 1


@dataclass
class UrlsConfig:
    """URL 配置：搜索模板列表。"""
    search: list[UrlTemplate] = field(default_factory=list)


@dataclass
class DomListConfig:
    """DOM 列表配置：卡片、标题、公司、薪资、标签等选择器。"""
    card: str = ""
    title: str = ""
    title_link: str = ""
    company: str = ""
    salary: str = ""
    tags: str = ""


@dataclass
class PaginationConfig:
    """分页配置：下一页按钮选择器和禁用样式类名。"""
    next_button: str = ""
    disabled_class_contains: str = "disabled"


@dataclass
class DetailSelectors:
    """详情页选择器配置：职位描述、公司、招聘者活跃度等选择器列表。"""
    description: list[str] = field(default_factory=list)
    company: list[str] = field(default_factory=list)
    recruiter_active: list[str] = field(default_factory=list)
    panel_salary: str = ""


@dataclass
class CaptchaConfig:
    """验证码检测配置：CSS 选择器指示器和关键词列表。"""
    indicators: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class LoginConfig:
    """登录状态检测配置：用户菜单选择器、认证页模式、正负面关键词。"""
    user_menu: str = ""
    page_auth_patterns: list[str] = field(default_factory=list)
    text_positive: list[str] = field(default_factory=list)
    text_negative: list[str] = field(default_factory=list)


@dataclass
class DomConfig:
    """DOM 完整配置：列表、分页、详情、验证码、登录等子配置。"""
    list: DomListConfig = field(default_factory=DomListConfig)
    pagination: PaginationConfig = field(default_factory=PaginationConfig)
    detail: DetailSelectors = field(default_factory=DetailSelectors)
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    login: LoginConfig = field(default_factory=LoginConfig)


@dataclass
class FilterRule:
    """过滤规则配置：字段、类型、匹配模式等参数。"""
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
    """报告维度配置：键名和标签。"""
    key: str = ""
    label: str = ""


@dataclass
class ReportConfig:
    """报告配置：评分阈值和维度列表。"""
    score_threshold: int = 6
    dimensions: list[ReportDimension] = field(default_factory=list)


@dataclass
class SiteProfile:
    """站点完整画像 — 一个 YAML 文件对应一个实例。"""
    meta: MetaConfig = field(default_factory=MetaConfig)
    navigation: NavigationConfig = field(default_factory=NavigationConfig)
    urls: UrlsConfig = field(default_factory=UrlsConfig)
    dom: DomConfig = field(default_factory=DomConfig)
    filters: list[FilterRule] = field(default_factory=list)
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
    """从 profiles/{name}.yaml 加载站点画像。"""
    import yaml  # pylint: disable=import-outside-toplevel

    base_dir = _get_base_dir()
    profile_path = os.path.join(base_dir, "profiles", f"{name}.yaml")
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"站点画像不存在: {profile_path}")
    with open(profile_path, encoding="utf-8") as f:
        raw: dict = yaml.safe_load(f) or {}
    profile = _dict_to_profile(raw)
    if global_config:
        profile._global_config = global_config  # pylint: disable=protected-access
    return profile


def _get_base_dir() -> str:
    """获取项目根目录。"""
    # __file__: src/shared/engine/profile.py
    # 需要向上4级到项目根：engine → shared → src → 项目根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _dict_to_profile(d: dict) -> SiteProfile:
    """将 YAML 字典递归转换为 SiteProfile 数据类。"""
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
