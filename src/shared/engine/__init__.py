"""通用爬取引擎 — 配置驱动，不含业务逻辑。"""

from shared.engine.profile import SiteProfile, load_profile
from shared.engine.url_builder import UrlBuilder
from shared.engine.dom_reader import DomReader
from shared.engine.filter_chain import FilterChain
from shared.engine.report_builder import ReportBuilder
from shared.engine.adapter_protocol import DefaultAdapter

# ScrapingEngine 依赖较重（playwright 等），延迟导入避免循环依赖
def get_engine(profile=None):
    """延迟创建引擎实例。"""
    if profile is None:
        from shared.config import get_config
        profile = load_profile("zhipin", global_config=get_config())
    from shared.engine.scraping_engine import ScrapingEngine
    return ScrapingEngine(profile)

__all__ = [
    "SiteProfile", "load_profile",
    "UrlBuilder", "DomReader", "FilterChain", "ReportBuilder", "DefaultAdapter",
    "get_engine",
]
