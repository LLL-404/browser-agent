"""BOSS 直聘 DOM 选择器 — 已废弃，选择器已迁移至 profiles/zhipin.yaml 的 dom 段。

更新记录:
- 2026-06-04: 已废弃，请使用 shared.engine.DomReader + profiles/zhipin.yaml
- 2026-06-04: 更新为适配 BOSS 直聘新版页面结构
"""
import warnings

warnings.warn(
    "selectors.py 已废弃，选择器已迁移至 profiles/zhipin.yaml 的 dom 段。"
    "请使用 shared.engine.DomReader 替代。",
    DeprecationWarning,
    stacklevel=2,
)

# === 列表页 ===
JOB_CARD = "li.job-card-box, li.search-job-item, .job-list li"
JOB_TITLE = ".job-name, .job-title, [class*='job-name'], [class*='job-title']"
JOB_TITLE_LINK = "a.job-name, a.job-title, .job-name a, .job-title a"
COMPANY_NAME = ".boss-name, .company-name, [class*='boss-name'], [class*='company-name']"
JOB_SALARY = ".job-salary, .salary, [class*='salary']"
JOB_TAGS = ".tag-list li, .job-tags li, .tags li, [class*='tag']"

# === 列表页翻页 ===
NEXT_PAGE_BUTTONS = ".options-pages .next, .page-next, .page .next, .pagination-next, button.next"

# === 详情页：职位描述 ===
DETAIL_DESC = [
    ".job-sec-text",
    ".job-detail-section-text",
    ".job-detail .text",
    ".detail-section .job-detail-box",
    ".job-detail-content",
    "[class*='job-detail']",
    "[class*='job-sec']",
    "[class*='description']",
    "[class*='detail-text']",
    ".position-detail",
    ".job-content",
    ".description-content",
]

# === 详情页：公司信息 ===
DETAIL_COMPANY = [
    ".company-info",
    ".detail-business-info",
    ".company-info-box",
    "[class*='company-info']",
    "[class*='business']",
    ".company-detail",
    ".company-content",
]

# === 详情页：招聘者活跃时间 ===
DETAIL_ACTIVE = [
    ".boss-active-time",
    ".boss-name-time",
    ".boss-online-tag",
    ".boss-description",
    "[class*='boss-active']",
    "[class*='active-time']",
    "[class*='boss-name']",
    ".recruiter-info",
    ".recruiter-active",
]

# === 详情面板（列表页右侧弹出） ===
DETAIL_PANEL_SALARY = (
    ".job-detail-box .job-detail-salary, "
    ".detail-salary, "
    "[class*='salary'], "
    ".popup-salary"
)

# === 验证码检测 ===
CAPTCHA_INDICATORS = [
    ".geetest_panel",
    ".captcha-box",
    ".verify-box",
    ".nc_wrapper",
    "iframe[src*='captcha']",
    "iframe[src*='geetest']",
    "[class*='captcha']",
    ".sec-captcha",
    ".security-verify",
    ".verify-code",
]
CAPTCHA_KEYWORDS = ["验证码", "安全验证", "滑块验证", "请完成验证", "请点击验证", "安全校验"]

# === 登录状态检测 ===
LOGIN_USER_MENU = ".nav-user-menu, .user-avatar, .header-user, .nav-user"
LOGIN_PAGE_AUTH = ["/user/", "passport", "login", "/account/"]
LOGIN_TEXT_POSITIVE = ["欢迎回来", "我的", "退出登录", "个人中心"]
LOGIN_TEXT_NEGATIVE = ["登录", "注册", "扫码", "验证码登录", "密码登录"]

# === DOM 结构检测（browser_controller 用） ===
DOM_STRUCTURE_SELECTORS = [
    "li.job-card-box", ".job-name", ".boss-name",
    ".job-salary", ".company-info", ".job-sec-text",
    ".boss-active-time", ".geetest_panel",
    ".captcha-box", ".verify-box", ".nc_wrapper",
    "li.search-job-item", ".salary", ".company-name",
]

# === 搜索输入框 ===
SEARCH_INPUT = "input[name='query'], input[placeholder*='搜索'], .search-input"
SEARCH_BUTTON = "button.search-btn, .search-button, [type='submit']"

# === 城市选择 ===
CITY_SELECTOR = ".city-select, .city-picker, [data-city], .location"

# === 职位筛选 ===
FILTER_BOX = ".filter-box, .condition-box, .search-filters"
