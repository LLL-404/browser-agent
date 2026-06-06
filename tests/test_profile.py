"""SiteProfile 数据模型与 YAML 加载器测试。"""
from __future__ import annotations

import os
import tempfile

import pytest

from shared.engine.profile import (
    DomConfig,
    MetaConfig,
    NavigationConfig,
    ReportConfig,
    SiteProfile,
    UrlsConfig,
    load_profile,
)

# ── 辅助：在临时 profiles/ 目录中创建 YAML 并加载 ────────────────────────

def _load_yaml_text(yaml_text: str, name: str = "test_site") -> SiteProfile:
    """将 YAML 文本写入临时 profiles/ 目录并加载为 SiteProfile。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        profiles_dir = os.path.join(tmpdir, "profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        profile_path = os.path.join(profiles_dir, f"{name}.yaml")
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(yaml_text)

        # 劫持 _get_base_dir 使其返回 tmpdir
        import shared.engine.profile as mod
        original = mod._get_base_dir
        mod._get_base_dir = lambda: tmpdir
        try:
            return load_profile(name)
        finally:
            mod._get_base_dir = original


# ── 测试：最小化 YAML 加载 ───────────────────────────────────────────────

class TestLoadMinimalProfile:
    """最小化 YAML 应正确加载，未指定字段使用默认值。"""

    def test_minimal_meta(self):
        profile = _load_yaml_text("meta:\n  name: zhipin\n")
        assert profile.meta.name == "zhipin"
        assert profile.meta.display_name == ""
        assert profile.meta.version == 1

    def test_minimal_defaults(self):
        profile = _load_yaml_text("")
        assert profile.meta.name == ""
        assert profile.navigation.home == ""
        assert profile.urls.search == []
        assert profile.dom.list.card == ""
        assert profile.filters == []
        assert profile.report.score_threshold == 6


# ── 测试：完整 YAML 所有字段解析 ──────────────────────────────────────────

_FULL_YAML = """
meta:
  name: boss_zhipin
  display_name: "BOSS直聘"
  version: 2
navigation:
  home: https://www.zhipin.com
  login: https://www.zhipin.com/login
urls:
  search:
    - template: "https://www.zhipin.com/web/geek/job?query={keyword}&city={city}"
      priority: 1
    - template: "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
      priority: 2
dom:
  list:
    card: .job-card-box
    title: .job-name
    title_link: .job-card-box a
    company: .company-name a
    salary: .salary
    tags: .tag-list li
  pagination:
    next_button: .ui-icon-arrow-right
    disabled_class_contains: disabled
  detail:
    description:
      - .job-sec-text
      - .job-detail-content
    company:
      - .company-info a
    recruiter_active:
      - .recruiter-status
    panel_salary: .detail-salary
  captcha:
    indicators:
      - .verify-img
      - "#captcha-modal"
    keywords:
      - 验证码
      - 滑动验证
  login:
    user_menu: .user-menu
    page_auth_patterns:
      - /login
      - /passport
    text_positive:
      - 已登录
      - 欢迎
    text_negative:
      - 请登录
      - 立即登录
filters:
  - id: min_salary
    type: range
    field: salary
    case_insensitive: true
    config_key: pre_filters.min_salary
    source: listing
    max_days_key: ""
    reason_template: "薪资低于 {threshold}，已过滤"
  - id: max_posted_days
    type: age
    field: posted_at
    case_insensitive: false
    config_key: pre_filters.max_posted_days
    source: listing
    max_days_key: pre_filters.max_posted_days
    reason_template: "发布超过 {max_days} 天，已过滤"
report:
  score_threshold: 7
  dimensions:
    - key: salary_match
      label: 薪资匹配度
    - key: company_size
      label: 公司规模
"""


class TestFullProfileAllFields:
    """完整 YAML 所有字段应被正确解析到对应数据类。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.profile = _load_yaml_text(_FULL_YAML)

    def test_meta_fields(self):
        assert self.profile.meta.name == "boss_zhipin"
        assert self.profile.meta.display_name == "BOSS直聘"
        assert self.profile.meta.version == 2

    def test_navigation_fields(self):
        assert self.profile.navigation.home == "https://www.zhipin.com"
        assert self.profile.navigation.login == "https://www.zhipin.com/login"

    def test_urls_search_templates(self):
        assert len(self.profile.urls.search) == 2
        assert self.profile.urls.search[0].template == "https://www.zhipin.com/web/geek/job?query={keyword}&city={city}"
        assert self.profile.urls.search[0].priority == 1
        assert self.profile.urls.search[1].priority == 2

    def test_dom_list_config(self):
        lst = self.profile.dom.list
        assert lst.card == ".job-card-box"
        assert lst.title == ".job-name"
        assert lst.title_link == ".job-card-box a"
        assert lst.company == ".company-name a"
        assert lst.salary == ".salary"
        assert lst.tags == ".tag-list li"

    def test_dom_pagination(self):
        pag = self.profile.dom.pagination
        assert pag.next_button == ".ui-icon-arrow-right"
        assert pag.disabled_class_contains == "disabled"

    def test_dom_detail(self):
        detail = self.profile.dom.detail
        assert detail.description == [".job-sec-text", ".job-detail-content"]
        assert detail.company == [".company-info a"]
        assert detail.recruiter_active == [".recruiter-status"]
        assert detail.panel_salary == ".detail-salary"

    def test_dom_captcha(self):
        captcha = self.profile.dom.captcha
        assert captcha.indicators == [".verify-img", "#captcha-modal"]
        assert captcha.keywords == ["验证码", "滑动验证"]

    def test_dom_login(self):
        login_cfg = self.profile.dom.login
        assert login_cfg.user_menu == ".user-menu"
        assert login_cfg.page_auth_patterns == ["/login", "/passport"]
        assert login_cfg.text_positive == ["已登录", "欢迎"]
        assert login_cfg.text_negative == ["请登录", "立即登录"]

    def test_filters(self):
        assert len(self.profile.filters) == 2
        f0 = self.profile.filters[0]
        assert f0.id == "min_salary"
        assert f0.type == "range"
        assert f0.field == "salary"
        assert f0.case_insensitive is True
        assert f0.config_key == "pre_filters.min_salary"
        assert f0.source == "listing"
        assert f0.reason_template == "薪资低于 {threshold}，已过滤"

        f1 = self.profile.filters[1]
        assert f1.id == "max_posted_days"
        assert f1.type == "age"

    def test_report_config(self):
        assert self.profile.report.score_threshold == 7
        assert len(self.profile.report.dimensions) == 2
        assert self.profile.report.dimensions[0].key == "salary_match"
        assert self.profile.report.dimensions[0].label == "薪资匹配度"
        assert self.profile.report.dimensions[1].key == "company_size"


# ── 测试：get_global 点分路径访问 ─────────────────────────────────────────

class TestGetGlobalConfigRef:
    """get_global(dot_path) 应支持点分路径读取嵌套配置。"""

    def test_simple_key(self):
        profile = SiteProfile(_global_config={"min_salary": 8000})
        assert profile.get_global("min_salary") == 8000

    def test_nested_dot_path(self):
        profile = SiteProfile(_global_config={
            "pre_filters": {"min_salary": 8000, "max_posted_days": 30}
        })
        assert profile.get_global("pre_filters.min_salary") == 8000
        assert profile.get_global("pre_filters.max_posted_days") == 30

    def test_missing_key_returns_default(self):
        profile = SiteProfile(_global_config={"a": 1})
        assert profile.get_global("nonexistent") is None
        assert profile.get_global("nonexistent", 42) == 42

    def test_partial_path_returns_default(self):
        profile = SiteProfile(_global_config={"a": {"b": 1}})
        # "a.b" 存在但 "a.c" 不存在时应返回默认值
        assert profile.get_global("a.nonexistent") is None

    def test_empty_global_config(self):
        profile = SiteProfile()
        assert profile.get_global("anything") is None
        assert profile.get_global("anything", "fallback") == "fallback"

    def test_none_value_returns_default(self):
        """字典中值为 None 时应返回 default 而非 None。"""
        profile = SiteProfile(_global_config={"key": None})
        assert profile.get_global("key", "fallback") == "fallback"


# ── 测试：空 YAML 返回默认值不报错 ───────────────────────────────────────

class TestEmptyYamlReturnsDefaults:
    """空或仅有注释的 YAML 不应抛异常，所有字段使用默认值。"""

    def test_completely_empty(self):
        profile = _load_yaml_text("")
        assert isinstance(profile, SiteProfile)
        assert profile.meta == MetaConfig()
        assert profile.navigation == NavigationConfig()
        assert profile.urls == UrlsConfig()
        assert profile.dom == DomConfig()
        assert profile.filters == []
        assert profile.report == ReportConfig()

    def test_only_comments(self):
        profile = _load_yaml_text("# 这是一行注释\n# 另一行注释\n")
        assert isinstance(profile, SiteProfile)
        assert profile.meta.name == ""

    def test_null_yaml(self):
        """YAML safe_load(None) 返回 None，应等价于空字典。"""
        profile = _load_yaml_text("~")
        assert isinstance(profile, SiteProfile)


# ── 测试：文件不存在时抛出明确错误 ───────────────────────────────────────

class TestFileNotFound:
    def test_nonexistent_profile_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import shared.engine.profile as mod
            original = mod._get_base_dir
            mod._get_base_dir = lambda: tmpdir
            try:
                with pytest.raises(FileNotFoundError, match="站点画像不存在"):
                    load_profile("nonexistent_site")
            finally:
                mod._get_base_dir = original
