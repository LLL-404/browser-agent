"""QCC（企查查）流程模块。"""

from __future__ import annotations

from browser_agent.flows.qcc.flows import QCC_FLOWS
from browser_agent.flows.qcc.semantic_rules import QccSemanticRules

__all__ = ["QCC_FLOWS", "QccSemanticRules"]
