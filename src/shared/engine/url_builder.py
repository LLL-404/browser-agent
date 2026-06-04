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
        base = self.profile.navigation.home.rstrip("/")
        templates = self.urls.search
        if not templates:
            return f"{base}/web/search?city={city_code}&query={keyword}"
        sorted_templates = sorted(templates, key=lambda t: t.priority)
        if priority is not None:
            matched = [t for t in sorted_templates if t.priority == priority]
            tmpl = matched[0].template if matched else sorted_templates[0].template
        else:
            tmpl = sorted_templates[0].template
        url = base + tmpl.format(city_code=city_code, keyword=keyword)
        return url

    def get_home_url(self) -> str:
        return self.profile.navigation.home

    def get_login_url(self) -> str:
        return self.profile.navigation.login

    def get_all_search_urls(self, city_code: str,
                             keyword: str) -> list[tuple[int, str]]:
        base = self.profile.navigation.home.rstrip("/")
        results = []
        for tmpl in sorted(self.urls.search, key=lambda t: t.priority):
            full_url = base + tmpl.template.format(
                city_code=city_code, keyword=keyword)
            results.append((tmpl.priority, full_url))
        return results
