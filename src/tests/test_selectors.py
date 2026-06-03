"""选择器有效性测试 — 验证 modes/zhipin/selectors.py 中所有 DOM 选择器。"""
import re

import pytest
from modes.zhipin.selectors import (
    JOB_CARD, JOB_TITLE, JOB_TITLE_LINK, COMPANY_NAME, JOB_SALARY, JOB_TAGS,
    NEXT_PAGE_BUTTONS,
    DETAIL_DESC, DETAIL_COMPANY, DETAIL_ACTIVE, DETAIL_PANEL_SALARY,
    CAPTCHA_INDICATORS, CAPTCHA_KEYWORDS,
    LOGIN_USER_MENU, LOGIN_PAGE_AUTH, LOGIN_TEXT_POSITIVE, LOGIN_TEXT_NEGATIVE,
    DOM_STRUCTURE_SELECTORS,
)

ALL_SELECTORS = {
    "JOB_CARD": JOB_CARD,
    "JOB_TITLE": JOB_TITLE,
    "JOB_TITLE_LINK": JOB_TITLE_LINK,
    "COMPANY_NAME": COMPANY_NAME,
    "JOB_SALARY": JOB_SALARY,
    "JOB_TAGS": JOB_TAGS,
    "NEXT_PAGE_BUTTONS": NEXT_PAGE_BUTTONS,
    "LOGIN_USER_MENU": LOGIN_USER_MENU,
}


def is_valid_css_selector(sel: str) -> bool:
    """Basic CSS selector syntax check."""
    if not isinstance(sel, str) or not sel.strip():
        return False
    if sel.startswith(".") or sel.startswith("#") or sel.startswith("[") or sel.startswith(":"):
        return True
    if re.match(r'^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)*', sel):
        return True
    return bool(re.search(r'[\.#\[\]:]', sel))


def check_list_selectors(name: str, selectors: list):
    for sel in selectors:
        assert isinstance(sel, str), f"{name} 包含非字符串: {sel}"
        assert sel.strip(), f"{name} 包含空字符串"
        valid = (
        sel.startswith(".") or sel.startswith("[") or sel.startswith("#")
        or sel.startswith("iframe") or ":" in sel
        or (sel[0].isalpha() and "." in sel)  # tag.class style
    )
    assert valid, f"{name} 选择器 '{sel}' 格式无效"


class TestSelectors:
    def test_job_card_selector(self):
        assert isinstance(JOB_CARD, str) and JOB_CARD.startswith("li")

    def test_job_title_selector(self):
        assert JOB_TITLE.startswith(".")

    def test_company_name_selector(self):
        assert COMPANY_NAME.startswith(".")

    def test_salary_selector(self):
        assert JOB_SALARY.startswith(".")

    def test_tags_selector(self):
        assert JOB_TAGS.startswith(".")

    def test_next_page_selector(self):
        assert NEXT_PAGE_BUTTONS.startswith(".")

    def test_detail_desc_selectors(self):
        check_list_selectors("DETAIL_DESC", DETAIL_DESC)

    def test_detail_company_selectors(self):
        check_list_selectors("DETAIL_COMPANY", DETAIL_COMPANY)

    def test_detail_active_selectors(self):
        check_list_selectors("DETAIL_ACTIVE", DETAIL_ACTIVE)

    def test_detail_panel_salary(self):
        assert isinstance(DETAIL_PANEL_SALARY, str)
        assert "salary" in DETAIL_PANEL_SALARY

    def test_captcha_indicators(self):
        check_list_selectors("CAPTCHA_INDICATORS", CAPTCHA_INDICATORS)

    def test_captcha_keywords(self):
        assert isinstance(CAPTCHA_KEYWORDS, list)
        for kw in CAPTCHA_KEYWORDS:
            assert isinstance(kw, str) and kw.strip(), f"空关键词: {kw}"

    def test_login_user_menu(self):
        assert LOGIN_USER_MENU.startswith(".")

    def test_login_page_auth(self):
        assert isinstance(LOGIN_PAGE_AUTH, list)

    def test_login_text_positive(self):
        assert isinstance(LOGIN_TEXT_POSITIVE, list)

    def test_login_text_negative(self):
        assert isinstance(LOGIN_TEXT_NEGATIVE, list)

    def test_dom_structure_selectors(self):
        check_list_selectors("DOM_STRUCTURE_SELECTORS", DOM_STRUCTURE_SELECTORS)
