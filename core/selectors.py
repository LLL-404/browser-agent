"""DOM 选择器集中管理模块，所有 CSS 选择器一处定义、全局复用。

BOSS 直聘改版时只需修改此文件即可适配。
"""

# === 列表页 ===
JOB_CARD = "li.job-card-box"
JOB_TITLE = ".job-name"
JOB_TITLE_LINK = "a.job-name"
COMPANY_NAME = ".boss-name"
JOB_SALARY = ".job-salary"
JOB_TAGS = ".tag-list li"

# === 列表页翻页 ===
NEXT_PAGE_BUTTONS = ".options-pages .next, .page-next, .page .next"

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
]

# === 详情页：公司信息 ===
DETAIL_COMPANY = [
    ".company-info",
    ".detail-business-info",
    ".company-info-box",
    "[class*='company-info']",
    "[class*='business']",
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
]

# === 详情面板（列表页右侧弹出） ===
DETAIL_PANEL_SALARY = (
    ".job-detail-box .job-detail-salary, "
    ".detail-salary, "
    "[class*='salary']"
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
]
CAPTCHA_KEYWORDS = ["验证码", "安全验证", "滑块验证", "请完成验证"]

# === 登录状态检测 ===
LOGIN_USER_MENU = ".nav-user-menu, .user-avatar"
LOGIN_PAGE_AUTH = ["/user/", "passport", "login"]
LOGIN_TEXT_POSITIVE = ["欢迎回来", "我的"]
LOGIN_TEXT_NEGATIVE = ["登录", "注册", "扫码"]

# === DOM 结构检测（browser_controller 用） ===
DOM_STRUCTURE_SELECTORS = [
    "li.job-card-box", ".job-name", ".boss-name",
    ".job-salary", ".company-info", ".job-sec-text",
    ".boss-active-time", ".geetest_panel",
    ".captcha-box", ".verify-box", ".nc_wrapper",
]
