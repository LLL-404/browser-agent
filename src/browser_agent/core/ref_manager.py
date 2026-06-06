"""@ref 元素引用系统 — 管理页面快照中的可交互元素引用编号。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.logging_config import get_logger

if TYPE_CHECKING:
    from browser_agent.core.perceiver import AnnotatedElement, PageSnapshot

logger = get_logger("ref_manager")


class RefManager:
    """维护页面快照中的 @ref 元素引用映射。

    职责：
    - 接收 PageSnapshot，按序为可交互元素分配 @1, @2, ... 引用编号
    - 通过 @ref 编号或语义类型字符串解析目标元素
    - 不负责 CSS 选择器的回退（由调用方处理）
    """

    def __init__(self) -> None:
        self._snapshot: PageSnapshot | None = None
        self._ref_map: dict[int, AnnotatedElement] = {}

    def update(self, snapshot: PageSnapshot) -> None:
        """更新快照，重新为所有可交互元素分配 @ref 编号（从 1 开始）。"""
        self._snapshot = snapshot
        self._ref_map.clear()
        # 从快照中提取可交互元素列表
        elements = getattr(snapshot, "interactive_elements", [])
        for i, element in enumerate(elements, start=1):
            self._ref_map[i] = element
        logger.debug("RefManager 已更新：%d 个可交互元素", len(self._ref_map))

    def resolve(self, target: str) -> AnnotatedElement | None:
        """解析目标字符串，返回对应的 AnnotatedElement。

        解析顺序：
        1. @ref 编号（如 "@3"）→ 按编号查找
        2. 语义类型字符串（如 "search_input"）→ 按 semantic_type 匹配
        3. 其他情况返回 None（CSS 选择器由调用方回退处理）
        """
        # @ref 编号解析
        if target.startswith("@"):
            try:
                ref_num = int(target[1:])
                return self._ref_map.get(ref_num)
            except ValueError:
                logger.warning("无效的 @ref 格式: %s", target)
                return None

        # 语义类型匹配：遍历快照元素查找匹配的 semantic_type
        if self._snapshot is not None:
            elements = getattr(self._snapshot, "interactive_elements", [])
            for element in elements:
                semantic_type = getattr(element, "semantic_type", "")
                if semantic_type == target:
                    return element

        return None

    def get_snapshot(self) -> PageSnapshot | None:
        """返回当前缓存的页面快照。"""
        return self._snapshot

    def clear(self) -> None:
        """重置快照和引用映射。"""
        self._snapshot = None
        self._ref_map.clear()
        logger.debug("RefManager 已重置")
