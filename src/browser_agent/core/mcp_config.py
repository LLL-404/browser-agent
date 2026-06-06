"""MCP 配置加载器 — 合并 JSON 配置文件 + CLI 参数。

CLI 参数优先级高于 JSON 配置文件。
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BrowserConfig:
    browser_name: str = "chromium"
    headless: bool = False
    user_data_dir: str = ""
    isolated: bool = False
    storage_state: str = ""
    viewport_width: int = 1280
    viewport_height: int = 720
    proxy_server: str = ""
    proxy_bypass: str = ""
    timeout_action: int = 5000
    timeout_navigation: int = 60000
    executable_path: str = ""


@dataclass
class ServerConfig:
    port: int = 0
    host: str = "localhost"
    allowed_hosts: list[str] = field(default_factory=lambda: ["localhost"])


@dataclass
class McpConfig:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    capabilities: list[str] = field(default_factory=lambda: ["core"])
    output_dir: str = ""
    console_level: str = "info"
    snapshot_mode: str = "full"
    allowed_origins: list[str] = field(default_factory=list)
    blocked_origins: list[str] = field(default_factory=list)
    config_path: str = ""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mcp-server", description="Playwright MCP Server")
    p.add_argument("--config", type=str, default="", help="JSON 配置文件路径")
    p.add_argument("--headless", action="store_true", help="无头模式")
    p.add_argument("--browser", type=str, default="chromium", choices=["chromium", "firefox", "webkit", "chrome", "msedge"], help="浏览器引擎")
    p.add_argument("--port", type=int, default=0, help="HTTP SSE 端口（0=禁用）")
    p.add_argument("--host", type=str, default="localhost", help="绑定主机")
    p.add_argument("--storage-state", type=str, default="", help="初始 storage_state 文件路径")
    p.add_argument("--user-data-dir", type=str, default="", help="用户数据目录路径")
    p.add_argument("--isolated", action="store_true", help="隔离模式，不持久化 profile")
    p.add_argument("--caps", type=str, default="core", help="启用能力: core,vision,pdf,devtools（逗号分隔）")
    p.add_argument("--output-dir", type=str, default="", help="输出文件目录")
    p.add_argument("--console-level", type=str, default="info", choices=["error", "warning", "info", "debug"], help="控制台消息级别")
    p.add_argument("--snapshot-mode", type=str, default="full", choices=["full", "none"], help="快照模式")
    p.add_argument("--viewport-size", type=str, default="", help="视口大小如 1280x720")
    p.add_argument("--proxy-server", type=str, default="", help="代理服务器地址")
    p.add_argument("--proxy-bypass", type=str, default="", help="绕过代理的域名列表")
    p.add_argument("--timeout-action", type=int, default=0, help="操作超时毫秒")
    p.add_argument("--timeout-navigation", type=int, default=0, help="导航超时毫秒")
    p.add_argument("--no-sandbox", action="store_true", help="禁用沙箱")
    p.add_argument("--executable-path", type=str, default="", help="浏览器可执行文件路径")
    return p.parse_args(argv)


def _load_json_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _merge_config(json_cfg: dict, args: argparse.Namespace) -> McpConfig:
    cfg = McpConfig()
    cfg.config_path = args.config

    # Browser section from JSON
    bc = cfg.browser
    browser_json = json_cfg.get("browser", {}) if json_cfg else {}
    bc.browser_name = args.browser if args.browser != "chromium" else browser_json.get("browserName", "chromium")
    bc.headless = args.headless or browser_json.get("launchOptions", {}).get("headless", False)

    # Viewport
    if args.viewport_size:
        parts = args.viewport_size.split("x")
        if len(parts) == 2:
            bc.viewport_width = int(parts[0])
            bc.viewport_height = int(parts[1])
    else:
        context_opts = browser_json.get("contextOptions", {})
        viewport = context_opts.get("viewport", {})
        bc.viewport_width = viewport.get("width", 1280)
        bc.viewport_height = viewport.get("height", 720)

    bc.user_data_dir = args.user_data_dir or browser_json.get("userDataDir", "")
    bc.isolated = args.isolated or browser_json.get("isolated", False)
    bc.storage_state = args.storage_state or ""
    bc.proxy_server = args.proxy_server or ""
    bc.proxy_bypass = args.proxy_bypass or ""
    bc.timeout_action = args.timeout_action or browser_json.get("launchOptions", {}).get("timeout", 5000)
    bc.timeout_navigation = args.timeout_navigation or 60000
    bc.executable_path = args.executable_path or browser_json.get("launchOptions", {}).get("executablePath", "")

    # Server section
    server_json = json_cfg.get("server", {}) if json_cfg else {}
    cfg.server.port = args.port or server_json.get("port", 0)
    cfg.server.host = args.host if args.host != "localhost" else server_json.get("host", "localhost")

    # Capabilities
    caps_str = args.caps
    if caps_str == "core":
        caps_json = json_cfg.get("capabilities", ["core"]) if json_cfg else ["core"]
        cfg.capabilities = caps_json if isinstance(caps_json, list) else [caps_json]
    else:
        cfg.capabilities = [c.strip() for c in caps_str.split(",")]

    # Other
    cfg.output_dir = args.output_dir or (json_cfg.get("outputDir", "") if json_cfg else "")
    cfg.console_level = args.console_level or (json_cfg.get("console", {}).get("level", "info") if json_cfg else "info")
    cfg.snapshot_mode = args.snapshot_mode or (json_cfg.get("snapshot", {}).get("mode", "full") if json_cfg else "full")

    # Network
    if json_cfg:
        network = json_cfg.get("network", {})
        cfg.allowed_origins = network.get("allowedOrigins", [])
        cfg.blocked_origins = network.get("blockedOrigins", [])

    return cfg


def load_config(argv: list[str] | None = None) -> McpConfig:
    args = _parse_args(argv)
    json_cfg = _load_json_config(args.config) if args.config else {}
    return _merge_config(json_cfg, args)


def config_to_browser_kwargs(cfg: McpConfig) -> dict[str, Any]:
    """Convert McpConfig to BrowserController-compatible kwargs."""
    kwargs = {
        "headless": cfg.browser.headless,
    }
    if cfg.browser.user_data_dir:
        kwargs["user_data_dir"] = cfg.browser.user_data_dir
    if cfg.browser.viewport_width and cfg.browser.viewport_height:
        kwargs["viewport"] = {"width": cfg.browser.viewport_width, "height": cfg.browser.viewport_height}
    if cfg.browser.proxy_server:
        kwargs["proxy"] = {"server": cfg.browser.proxy_server}
    return kwargs
