"""共享搜索引擎模块 — **已废弃 (deprecated)**。

警告：此模块已被新架构替代，不再维护。
新架构使用 browser_agent.core.decider (DecisionEngine + FlowRegistry) 替代此模块的功能。

保留此模块仅为向后兼容，将在后续版本中移除。
"""

import warnings

from shared.engine.adapter_protocol import DefaultAdapter
from shared.engine.dom_reader import DomReader
from shared.engine.filter_chain import FilterChain
from shared.engine.profile import SiteProfile, load_profile
from shared.engine.report_builder import ReportBuilder
from shared.engine.url_builder import UrlBuilder

warnings.warn(
    "shared.engine 已废弃，请使用 browser_agent.core.decider (DecisionEngine + FlowRegistry) 替代。"
    " 此模块将在后续版本中移除。",
    DeprecationWarning,
    stacklevel=2,
)

# ScrapingEngine 依赖较重（playwright 等），延迟导入避免循环依赖
def get_engine(profile=None):
    """延迟创建引擎实例。"""
    if profile is None:
        from shared.config import get_config  # pylint: disable=import-outside-toplevel
        profile = load_profile("zhipin", global_config=get_config())
    from shared.engine.scraping_engine import ScrapingEngine  # pylint: disable=import-outside-toplevel
    return ScrapingEngine(profile)

__all__ = [
    "SiteProfile", "load_profile",
    "UrlBuilder", "DomReader", "FilterChain", "ReportBuilder", "DefaultAdapter",
    "get_engine",
]
