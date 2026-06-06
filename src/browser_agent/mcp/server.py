"""通用 MCP 服务器 — 生命周期协调器。

职责：
- 工具注册（从 definitions.py 按 capabilities 过滤）
- 工具分发（通过 handlers.py 的 TOOL_HANDLERS）
- 模式发现（modes/ 目录下的业务模式）
- 服务器启动（stdio / SSE）
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
from pathlib import Path

# pylint: disable=import-error,no-name-in-module,import-self,no-member
import mcp.server.stdio
from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.server import InitializationOptions
from mcp.types import ServerCapabilities
# pylint: enable=import-error,no-name-in-module,import-self,no-member

from browser_agent.core.agent import BrowserAgent
from browser_agent.core.browser import BrowserController
from browser_agent.core.mcp_config import McpConfig, load_config
from browser_agent.mcp.definitions import (
    _CORE_TOOLS,
    _DEVTOOLS_TOOLS,
    _PDF_TOOLS,
    _VISION_TOOLS,
)
from browser_agent.mcp.handlers import TOOL_ALIASES, TOOL_HANDLERS
from browser_agent.mcp.validation import validate_args
from shared.error_handler import format_error_for_mcp
from shared.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger("mcp")

server = Server("browser-agent")
_mode_tools: list[types.Tool] = []
_mode_handlers: dict[str, callable] = {}
# pylint: disable=invalid-name
_agent: BrowserAgent | None = None
_agent_lock = asyncio.Lock()  # 单浏览器实例：SSE 多客户端时序列化所有操作
_server_config: McpConfig | None = None
# pylint: enable=invalid-name
_TOOL_EXECUTION_TIMEOUT = 300


# ── Mode discovery ──


def _discover_modes() -> list[str]:
    """发现 modes/ 目录下的业务模式模块。"""
    try:
        import modes  # pylint: disable=import-outside-toplevel
        return [name for _, name, _ in pkgutil.iter_modules(modes.__path__)]
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def register_mode_tools(mode_name: str):
    """注册指定模式的 MCP 工具和处理器。"""
    try:
        mod = importlib.import_module(f"modes.{mode_name}")
        if hasattr(mod, "get_mcp_tools"):
            tools = mod.get_mcp_tools()
            _mode_tools.extend(tools)
            logger.info("已注册 %d 个工具来自模式: %s", len(tools), mode_name)
        if hasattr(mod, "handle_mcp_call"):
            _mode_handlers[mode_name] = mod.handle_mcp_call
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("加载模式 %s 失败: %s", mode_name, e)


# ── Tool assembly ──


def _get_enabled_caps() -> list[str]:
    return _server_config.capabilities if _server_config else ["core"]


def _collect_all_tools() -> list[types.Tool]:
    caps = _get_enabled_caps()
    tools = list(_CORE_TOOLS) + _mode_tools
    if "vision" in caps:
        tools.extend(_VISION_TOOLS)
    if "pdf" in caps:
        tools.extend(_PDF_TOOLS)
    if "devtools" in caps:
        tools.extend(_DEVTOOLS_TOOLS)
    return tools


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """MCP 工具列表回调：返回所有已注册的工具定义。"""
    return _collect_all_tools()


# ── Agent lifecycle ──


def _get_agent() -> BrowserAgent:  # pylint: disable=global-statement
    global _agent  # pylint: disable=global-statement
    if _agent is None:
        bc = BrowserController()
        _agent = BrowserAgent(bc)
        _apply_startup_config()
    return _agent


def _apply_startup_config():
    """应用启动配置：加载 storage_state 和输出日志。"""
    cfg = _server_config
    if not cfg:
        return
    if cfg.browser.storage_state:
        import json  # pylint: disable=import-outside-toplevel
        path = Path(cfg.browser.storage_state)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cookies = data.get("cookies", [])
                if cookies:
                    _agent.ctrl.load_cookies(cookies)
                    logger.info(
                        "已从 %s 加载 %d 条 Cookie（启动时）",
                        cfg.browser.storage_state, len(cookies),
                    )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("加载 storage_state 失败: %s", e)
    if cfg.server.port:
        logger.info("SSE 模式: 端口 %d", cfg.server.port)


# ── Tool dispatch ──


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """MCP 工具调用回调：分发到对应 handler 并返回结果。"""
    try:
        # Resolve alias
        name = TOOL_ALIASES.get(name, name)

        # Validate arguments
        arguments = validate_args(name, arguments)

        # Inject config defaults for tools that need them
        if name == "browser_snapshot" and "mode" not in arguments:
            if _server_config and _server_config.snapshot_mode:
                arguments["mode"] = _server_config.snapshot_mode
        if name == "browser_screenshot_save" and "path" not in arguments:
            if _server_config and _server_config.output_dir:
                arguments["path"] = str(Path(_server_config.output_dir) / "screenshot.png")

        # Execute under lock with timeout
        async with _agent_lock:
            result = await asyncio.wait_for(
                _execute_tool(name, arguments),
                timeout=_TOOL_EXECUTION_TIMEOUT)

        return [types.TextContent(type="text", text=str(result))]
    except TimeoutError:
        logger.error("工具 %s 执行超时 (%ds)", name, _TOOL_EXECUTION_TIMEOUT)
        return [types.TextContent(type="text", text=str({
            "ok": False, "error": f"执行超时 ({_TOOL_EXECUTION_TIMEOUT}s)",
            "error_code": "EXECUTION_TIMEOUT",
        }))]
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("工具调用失败: %s", e, exc_info=True)
        formatted = format_error_for_mcp(e)
        return [types.TextContent(type="text", text=str(formatted))]


async def _execute_tool(name: str, arguments: dict) -> dict:
    """执行工具调用（在锁保护下）。"""
    agent = _get_agent()
    ctrl = agent.ctrl

    # Dispatch via handler registry
    handler = TOOL_HANDLERS.get(name)
    if handler:
        return await handler(agent, ctrl, arguments)

    # Try mode handlers
    for _mode_name, h in _mode_handlers.items():
        r = await h(name, arguments, agent)
        if r is not None:
            return r

    return {"ok": False, "error": f"未知工具: {name}", "error_code": "UNKNOWN_TOOL"}


# ── Main ──


async def main(argv: list[str] | None = None):  # pylint: disable=global-statement
    """MCP 服务器主入口：加载配置、注册模式、启动 stdio/SSE 服务。"""
    global _server_config  # pylint: disable=global-statement
    _server_config = load_config(argv)

    logger.info("MCP 服务器启动 (browser=%s, headless=%s, caps=%s)",
                _server_config.browser.browser_name,
                _server_config.browser.headless,
                _server_config.capabilities)

    for mode in _discover_modes():
        register_mode_tools(mode)

    if _server_config.server.port:
        # pylint: disable=import-outside-toplevel,import-error,no-name-in-module
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        from mcp.server.sse import SseServerTransport
        # pylint: enable=import-outside-toplevel,import-error,no-name-in-module

        sse = SseServerTransport("/messages")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send  # pylint: disable=protected-access
            ) as streams:
                await server.run(streams[0], streams[1], InitializationOptions(
                    server_name="browser-agent",
                    server_version="1.0.0",
                    capabilities=ServerCapabilities(),
                ))

        app = Starlette(routes=[
            Route("/mcp", endpoint=handle_sse),
            Mount("/messages", app=sse.handle_post_message),
        ])
        logger.info(
            "SSE 服务监听 %s:%d",
            _server_config.server.host, _server_config.server.port,
        )
        config = uvicorn.Config(
            app, host=_server_config.server.host,
            port=_server_config.server.port, log_level="info",
        )
        await uvicorn.Server(config).serve()
    else:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):  # pylint: disable=no-member
            await server.run(read_stream, write_stream, InitializationOptions(
                server_name="browser-agent",
                server_version="1.0.0",
                capabilities=ServerCapabilities(),
            ))


if __name__ == "__main__":
    asyncio.run(main())
