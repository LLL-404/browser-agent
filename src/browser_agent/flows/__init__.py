"""浏览器 Agent 预定义流程模块。

汇总所有平台的流程模板，供 FlowRegistry 加载使用。
"""

from __future__ import annotations

from browser_agent.flows.builtin import BUILTIN_FLOWS
from browser_agent.flows.qcc import QCC_FLOWS
from browser_agent.flows.zhipin import ZHIPIN_FLOWS

ALL_FLOWS = BUILTIN_FLOWS + ZHIPIN_FLOWS + QCC_FLOWS

__all__ = ["BUILTIN_FLOWS", "ZHIPIN_FLOWS", "QCC_FLOWS", "ALL_FLOWS"]
