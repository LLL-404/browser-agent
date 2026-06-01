"""
通用浏览器自动化 — MCP Server
通过 Model Context Protocol 将浏览器自动化能力暴露给 IDE 内置 AI。
兼容 BOSS 直聘求职功能。
"""

import sys
import asyncio
import threading
import json
import re
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp.server.stdio
from mcp.server import Server
from mcp.server.lowlevel.server import InitializationOptions
from mcp import types

from core.logging_config import setup_logging, get_logger
from sites.zhipin import (
    search_jobs as _scraper_search_jobs,
    analyze_jobs, import_analysis,
    generate_report as _scraper_generate_report,
    generate_chat_prompt,
    get_jobs, get_job_by_id, update_job_status,
    get_stats as _scraper_get_stats, JobQuery,
)
from core.browser_controller import BrowserController
from core.agent import BrowserAgent
from core.storage import init_db
from core.profiler import generate_report as profiler_report, get_hot_functions

setup_logging(log_to_console=True, log_to_file=True, console_stream=sys.stderr)
logger = get_logger("mcp")

server = Server("browser-automation")

_GEN_ERRORS = (Exception,)

__all__ = ["server", "main", "handle_list_tools", "handle_call_tool"]


# ====== MCP Tool 注册 ======

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return _boss_tools() + _browser_tools() + _perf_tools()


def _boss_tools() -> list[types.Tool]:
    """BOSS 直聘专属工具（保留兼容）。"""
    return [
        types.Tool(
            name="search_jobs",
            description="在BOSS直聘搜索职位并存入数据库。",
            inputSchema={
                "type": "object",
                "properties": {
                    "cities": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "max_detail": {"type": "integer", "default": 30},
                },
            },
        ),
        types.Tool(
            name="list_jobs",
            description="查询职位列表（轻量，不含完整描述）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "city": {"type": "string"},
                    "min_score": {"type": "integer"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        ),
        types.Tool(
            name="get_job_detail",
            description="读取单条职位完整信息（含描述和公司信息）。",
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "integer"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="analyze_jobs",
            description="获取待分析职位数据，AI分析后写回数据库。",
            inputSchema={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "job_id": {"type": "integer"},
                                "five_insurance": {"type": "boolean"},
                                "room_board": {"type": "boolean"},
                                "regular_hours": {"type": "boolean"},
                                "overtime_risk": {"type": "string",
                                                  "enum": ["low", "mid", "high"]},
                                "diploma_ok": {"type": "boolean"},
                                "recruiter_active": {"type": "boolean"},
                                "match_score": {"type": "integer",
                                                "minimum": 0, "maximum": 10},
                                "reason": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["results"],
            },
        ),
        types.Tool(
            name="boss_get_stats",
            description="获取求职数据统计概览。",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="update_status",
            description="更新职位状态追踪投递进展。",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "status": {"type": "string",
                               "enum": ["applied", "interview", "offered",
                                        "rejected", "ignored"]},
                },
                "required": ["job_id", "status"],
            },
        ),
        types.Tool(
            name="boss_generate_report",
            description="生成 BOSS 直聘推荐报告（Markdown）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_score": {"type": "integer", "default": 6},
                    "city": {"type": "string"},
                    "top": {"type": "integer"},
                },
            },
        ),
        types.Tool(
            name="generate_chat_prompt",
            description="为指定职位生成招呼语 prompt。",
            inputSchema={
                "type": "object",
                "properties": {"job_id": {"type": "integer"}},
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="filter_jobs",
            description="从全国搜索结果(JSON)中按条件筛选、评分、排名。",
            inputSchema={
                "type": "object",
                "properties": {
                    "data_file": {
                        "type": "string",
                        "description": "搜索结果的 JSON 文件路径，如 data/nationwide_results.json",
                    },
                    "exclude_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标题排除词，如 [\"销售\", \"管培生\"]",
                    },
                    "exclude_edu": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除学历，如 [\"本科\", \"硕士\"]",
                    },
                    "exclude_exp": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "排除经验，如 [\"3-5年\"]",
                    },
                    "focus_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "重点关注词(加分)，如 [\"化工\", \"安全\", \"质检\"]",
                    },
                    "top_n": {
                        "type": "integer",
                        "default": 40,
                        "description": "返回前 N 条",
                    },
                },
            },
        ),
    ]


def _browser_tools() -> list[types.Tool]:
    """通用浏览器自动化工具。"""
    return [
        types.Tool(
            name="browser_open",
            description="启动浏览器并导航到指定URL。支持 session 名称以自动恢复登录状态。",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string",
                            "description": "目标URL，默认 about:blank"},
                    "headless": {"type": "boolean", "default": False},
                    "session": {"type": "string",
                                "description": "会话名称，用于自动恢复 cookies"},
                },
            },
        ),
        types.Tool(
            name="browser_close",
            description="关闭浏览器。",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="browser_navigate",
            description="导航到指定URL（清除 ref 缓存）。",
            inputSchema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        ),
        types.Tool(
            name="browser_click",
            description="点击页面元素。支持 @e1 ref、CSS选择器、文本内容，或语义定位(text/label/placeholder/role/testid)。",
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string",
                               "description": "CSS选择器、@e1 ref 或 语义定位值"},
                    "mode": {"type": "string",
                             "enum": ["selector", "text", "label",
                                      "placeholder", "role", "testid"],
                             "default": "selector",
                             "description": "定位方式"},
                },
                "required": ["target"],
            },
        ),
        types.Tool(
            name="browser_type_text",
            description="在输入框中输入文本（先清空后输入）。支持 @e1 ref、CSS选择器 或 语义定位(text/label/placeholder/role)。",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string",
                                 "description": "输入框的 CSS选择器、@e1 ref 或 语义定位值"},
                    "text": {"type": "string"},
                    "clear": {"type": "boolean", "default": True},
                    "locator": {"type": "string",
                                "enum": ["css", "text", "label",
                                         "placeholder", "role", "testid"],
                                "default": "css",
                                "description": "selector 参数的定位方式"},
                },
                "required": ["selector", "text"],
            },
        ),
        types.Tool(
            name="browser_press",
            description="模拟键盘按键（如 Enter、Tab、Escape）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "default": "Enter"},
                },
            },
        ),
        types.Tool(
            name="browser_scroll",
            description="滚动页面。正数向下，负数向上。",
            inputSchema={
                "type": "object",
                "properties": {
                    "delta": {"type": "integer", "default": 500},
                },
            },
        ),
        types.Tool(
            name="browser_select",
            description="选择下拉框选项。支持 @e1 ref 或 CSS选择器。",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["selector", "value"],
            },
        ),
        types.Tool(
            name="browser_wait",
            description="等待条件满足。可等待元素出现(selector) 或 指定毫秒(ms)。",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string",
                                 "description": "等待的 CSS选择器 或 @e1 ref"},
                    "timeout": {"type": "integer", "default": 10000},
                    "ms": {"type": "integer",
                           "description": "纯时间等待（毫秒），如 1500"},
                },
            },
        ),
        types.Tool(
            name="browser_snapshot",
            description="获取当前页面结构快照（可交互元素树 + DOM计数 + 文本摘要）。先用此工具获取 @e1、@e2 等 ref 编号，再用 click/type_text 操作。",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_length": {"type": "integer", "default": 3000},
                },
            },
        ),
        types.Tool(
            name="browser_text",
            description="获取页面纯文本。",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_len": {"type": "integer", "default": 3000},
                },
            },
        ),
        types.Tool(
            name="browser_html",
            description="获取页面HTML源码。",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_len": {"type": "integer", "default": 8000},
                },
            },
        ),
        types.Tool(
            name="browser_url",
            description="获取当前页面URL和标题。",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="browser_screenshot",
            description="截取当前页面截图（base64编码PNG），用于AI视觉分析。",
            inputSchema={
                "type": "object",
                "properties": {
                    "full_page": {"type": "boolean", "default": False},
                },
            },
        ),
        types.Tool(
            name="browser_extract",
            description="从页面提取数据。支持三种模式：list(批量提取元素属性)、table(从表格结构提取)、pages(翻页批量提取)。",
            inputSchema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["list", "table", "pages"],
                        "default": "list",
                    },
                    "selector": {"type": "string",
                                 "description": "行元素 CSS选择器"},
                    "fields": {"type": "array", "items": {"type": "string"},
                               "default": ["innerText"],
                               "description": "list模式: 属性名列表"},
                    "columns": {
                        "type": "object",
                        "description": "table/pages模式: {\"列名\": \"CSS子选择器\"} 映射",
                    },
                    "limit": {"type": "integer", "default": 20},
                    "page_count": {"type": "integer", "default": 3,
                                   "description": "pages模式: 翻页数"},
                    "next_btn": {"type": "string",
                                 "description": "pages模式: 下一页按钮CSS选择器"},
                },
                "required": ["selector"],
            },
        ),
        types.Tool(
            name="browser_execute_js",
            description="在页面中执行自定义JavaScript代码并返回结果。",
            inputSchema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        ),
        types.Tool(
            name="browser_session",
            description="管理浏览器会话（cookies + localStorage），用于保持登录状态。action: save=保存当前, load=恢复, list=列出所有。",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["save", "load", "list"],
                        "description": "操作类型",
                    },
                    "name": {"type": "string", "default": "default",
                             "description": "会话名称"},
                },
                "required": ["action"],
            },
        ),
    ]


def _perf_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_performance_stats",
            description="获取函数级性能统计数据。",
            inputSchema={
                "type": "object",
                "properties": {
                    "top_n": {"type": "integer", "default": 10},
                },
            },
        ),
        types.Tool(
            name="generate_performance_report",
            description="生成 Markdown 性能分析报告。",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ====== Tool 调用分发 ======

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    init_db()

    browser_handlers = {
        "browser_open": _h_browser_open,
        "browser_close": _h_browser_close,
        "browser_navigate": _h_browser_navigate,
        "browser_click": _h_browser_click,
        "browser_type_text": _h_browser_type_text,
        "browser_press": _h_browser_press,
        "browser_scroll": _h_browser_scroll,
        "browser_select": _h_browser_select,
        "browser_wait": _h_browser_wait,
        "browser_snapshot": _h_browser_snapshot,
        "browser_text": _h_browser_text,
        "browser_html": _h_browser_html,
        "browser_url": _h_browser_url,
        "browser_screenshot": _h_browser_screenshot,
        "browser_extract": _h_browser_extract,
        "browser_execute_js": _h_browser_execute_js,
        "browser_session": _h_browser_session,
    }

    boss_handlers = {
        "search_jobs": _h_boss_search_jobs,
        "list_jobs": _h_boss_list_jobs,
        "get_job_detail": _h_boss_get_job_detail,
        "analyze_jobs": _h_boss_analyze_jobs,
        "boss_get_stats": _h_boss_get_stats,
        "update_status": _h_boss_update_status,
        "boss_generate_report": _h_boss_generate_report,
        "generate_chat_prompt": _h_boss_generate_chat_prompt,
        "filter_jobs": _h_boss_filter_jobs,
    }

    perf_handlers = {
        "get_performance_stats": _h_get_performance_stats,
        "generate_performance_report": _h_generate_performance_report,
    }

    handler = browser_handlers.get(name) or boss_handlers.get(name) or perf_handlers.get(name)
    if handler:
        return await handler(arguments)

    return [types.TextContent(
        type="text",
        text=json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False))]


# ====== 浏览器管理器（线程安全单例） ======

class _BrowserManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._controller: BrowserController | None = None
        self._agent: BrowserAgent | None = None

    def get_agent(self) -> BrowserAgent:
        if self._agent is None:
            with self._lock:
                if self._agent is None:
                    if self._controller is None:
                        self._controller = BrowserController()
                    self._agent = BrowserAgent(self._controller)
                    logger.info("浏览器 Agent 已初始化")
        return self._agent

    async def cleanup(self) -> None:
        if self._controller is not None:
            try:
                if self._controller.is_running:
                    await self._controller.stop()
                logger.info("浏览器资源已释放")
            except (RuntimeError, OSError) as e:
                logger.warning("浏览器清理时出错: %s", e)
            finally:
                self._controller = None
                self._agent = None


_mgr = _BrowserManager()


def _get_agent() -> BrowserAgent:
    return _mgr.get_agent()


async def _cleanup_browser() -> None:
    await _mgr.cleanup()


def _ok(data: dict | str) -> list[types.TextContent]:
    if isinstance(data, str):
        return [types.TextContent(type="text", text=data)]
    return [types.TextContent(
        type="text", text=json.dumps(data, ensure_ascii=False))]


def _err(msg: str) -> list[types.TextContent]:
    return _ok({"error": msg})


# ====== 通用浏览器 Handler ======

async def _h_browser_open(args: dict) -> list[types.TextContent]:
    agent = _get_agent()
    try:
        result = await agent.open(
            headless=args.get("headless", False),
            url=args.get("url") or "about:blank")
        session_name = args.get("session")
        if session_name and result.get("ok"):
            loaded = await agent.load_session(session_name)
            if loaded.get("ok"):
                result["session_restored"] = session_name
        return _ok(result)
    except (RuntimeError, OSError, TimeoutError) as e:
        return _err(str(e))


async def _h_browser_close(_args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().close())


async def _h_browser_navigate(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().navigate(args["url"]))


async def _h_browser_click(args: dict) -> list[types.TextContent]:
    mode = args.get("mode", "selector")
    if mode in ("text", "label", "placeholder", "role", "testid"):
        return _ok(await _get_agent().find(
            target_type=mode, target=args["target"], action="click"))
    return _ok(await _get_agent().click(args["target"], mode=mode))


async def _h_browser_type_text(args: dict) -> list[types.TextContent]:
    locator = args.get("locator", "css")
    if locator in ("text", "label", "placeholder", "role", "testid"):
        return _ok(await _get_agent().find(
            target_type=locator, target=args["selector"],
            action="fill", value=args["text"]))
    return _ok(await _get_agent().type_text(
        args["selector"], args["text"], clear=args.get("clear", True)))


async def _h_browser_press(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().press(args.get("key", "Enter")))


async def _h_browser_scroll(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().scroll(args.get("delta", 500)))


async def _h_browser_select(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().select(args["selector"], args["value"]))


async def _h_browser_wait(args: dict) -> list[types.TextContent]:
    if "selector" in args and args["selector"]:
        return _ok(await _get_agent().wait(
            args["selector"], timeout=args.get("timeout", 10000)))
    return _ok(await _get_agent().wait_load(args.get("ms", 1500)))


async def _h_browser_snapshot(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().snapshot(args.get("max_length", 3000)))


async def _h_browser_text(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().text(args.get("max_len", 3000)))


async def _h_browser_html(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().html(args.get("max_len", 8000)))


async def _h_browser_url(_args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().url())


async def _h_browser_screenshot(args: dict) -> list[types.TextContent]:
    result = await _get_agent().screenshot(args.get("full_page", False))
    if result.get("ok"):
        return [types.TextContent(type="text", text=result["data_uri"])]
    return _err(result.get("error", "截图失败"))


async def _h_browser_extract(args: dict) -> list[types.TextContent]:
    mode = args.get("mode", "list")
    if mode == "table":
        return _ok(await _get_agent().extract_table(
            args["selector"], args.get("columns", {}),
            limit=args.get("limit", 30)))
    if mode == "pages":
        return _ok(await _get_agent().loop_extract(
            page_count=args.get("page_count", 3),
            row_selector=args["selector"],
            columns=args.get("columns", {}),
            next_btn=args.get("next_btn", "")))
    return _ok(await _get_agent().extract(
        args["selector"],
        fields=args.get("fields"),
        limit=args.get("limit", 20)))


async def _h_browser_execute_js(args: dict) -> list[types.TextContent]:
    return _ok(await _get_agent().execute_js(args["expression"]))


async def _h_browser_session(args: dict) -> list[types.TextContent]:
    action = args["action"]
    if action == "save":
        return _ok(await _get_agent().save_session(args.get("name", "default")))
    if action == "load":
        return _ok(await _get_agent().load_session(args.get("name", "default")))
    return _ok(await _get_agent().list_sessions())


# ====== BOSS 直聘 Handler ======

async def _h_boss_search_jobs(args: dict) -> list[types.TextContent]:
    result = await _scraper_search_jobs(
        cities=args.get("cities"),
        keywords=args.get("keywords"),
        max_detail=args.get("max_detail"),
    )
    return _ok(result)


async def _h_boss_list_jobs(args: dict) -> list[types.TextContent]:
    jobs = get_jobs(JobQuery(
        status=args.get("status"),
        city=args.get("city"),
        min_score=args.get("min_score"),
        limit=args.get("limit", 20),
    ))
    keep = {"id", "title", "company", "salary", "city", "tags", "status", "match_score"}
    light = [{k: v for k, v in j.items() if k in keep} for j in jobs]
    return _ok({"count": len(light), "jobs": light})


async def _h_boss_get_job_detail(args: dict) -> list[types.TextContent]:
    job = get_job_by_id(args["job_id"])
    if job:
        return _ok(job)
    return _err("职位不存在")


async def _h_boss_analyze_jobs(args: dict) -> list[types.TextContent]:
    if args.get("results"):
        success, fail = await import_analysis(args["results"])
        logger.info("分析结果导入: 成功 %d, 失败 %d", success, fail)
        return _ok({"success": success, "fail": fail})
    pending = await analyze_jobs()
    return _ok(pending)


async def _h_boss_get_stats(_args: dict) -> list[types.TextContent]:
    return _ok(_scraper_get_stats())


async def _h_boss_update_status(args: dict) -> list[types.TextContent]:
    update_job_status(args["job_id"], args["status"])
    return _ok({"ok": True, "job_id": args["job_id"], "status": args["status"]})


async def _h_boss_generate_report(args: dict) -> list[types.TextContent]:
    content = await _scraper_generate_report(
        min_score=args.get("min_score", 6),
        city=args.get("city"),
        top=args.get("top"),
    )
    return [types.TextContent(type="text", text=content)]


async def _h_boss_generate_chat_prompt(args: dict) -> list[types.TextContent]:
    prompt = await generate_chat_prompt(args["job_id"])
    if prompt:
        return [types.TextContent(type="text", text=prompt)]
    return _err("职位不存在")


async def _h_boss_filter_jobs(args: dict) -> list[types.TextContent]:
    data_file = Path(args.get("data_file", "data/nationwide_results.json"))
    if not data_file.is_file():
        return _err(f"文件不存在: {data_file}")

    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    except _GEN_ERRORS as exc:
        return _err(f"读取文件失败: {exc}")

    exclude_keywords = set(args.get("exclude_keywords", []))
    exclude_edu = set(args.get("exclude_edu", []))
    exclude_exp = set(args.get("exclude_exp", []))
    focus_keywords = args.get("focus_keywords", [])
    top_n = args.get("top_n", 40)

    EXCLUDE_SCHEDULE = {"倒班", "夜班", "两班倒", "三班倒", "早晚班"}
    GOOD_BENEFIT = {"五险一金", "五险", "公积金", "双休", "大小周",
                    "朝九晚五", "朝九晚六", "包吃", "包住", "住宿",
                    "食堂", "餐补", "班车", "补贴", "宿舍", "住房"}
    GOOD_SCHEDULE = {"双休", "大小周", "朝九晚五", "朝九晚六", "不加班", "长白班"}

    total_before = len(data)
    results = []

    for r in data:
        title = r.get("title", "")
        tags = r.get("tags", [])
        all_text = title + " " + " ".join(tags) + " " + r.get("self_text", "")

        if any(kw in title for kw in exclude_keywords):
            continue
        if any(kw in tags or kw in all_text for kw in exclude_edu):
            continue
        if any(kw in tags for kw in exclude_exp):
            continue
        if any(kw in all_text for kw in EXCLUDE_SCHEDULE):
            continue

        score = sum(2 for kw in focus_keywords if kw in title) if focus_keywords else 0
        if any(k in " ".join(tags) for k in ("应届", "校招", "经验不限", "实习生")):
            score += 3
        if "在校/应届" in " ".join(tags):
            score += 5
        score += sum(1 for kw in GOOD_BENEFIT if kw in all_text)
        score += sum(2 for kw in GOOD_SCHEDULE if kw in all_text)
        nums = re.findall(r"(\d+)-(\d+)", r.get("salary", ""))
        if nums:
            lo = int(nums[0][0])
            if lo >= 5:
                score += 2
            if lo >= 7:
                score += 2
        if "薪" in r.get("salary", ""):
            score += 1
        if "大专" in " ".join(tags):
            score += 3
        if "学历不限" in " ".join(tags):
            score += 1

        results.append({
            "score": score,
            "title": title,
            "company": r.get("company", ""),
            "city": r.get("city", ""),
            "salary": r.get("salary", ""),
            "tags": tags,
            "keyword": r.get("keyword", ""),
        })

    seen = set()
    unique = []
    for r in sorted(results, key=lambda x: x["score"], reverse=True):
        key = (r["title"], r["company"], r["city"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    pro = [r for r in unique
           if focus_keywords and any(kw in r["title"] for kw in focus_keywords)]
    top = (pro[:top_n] if pro else unique[:top_n])

    return _ok({
        "total_before": total_before,
        "total_after": len(unique),
        "profession_match": len(pro),
        "top": top,
    })


# ====== 性能监控 Handler ======

async def _h_get_performance_stats(args: dict) -> list[types.TextContent]:
    top_n = args.get("top_n", 10)
    hot_funcs = get_hot_functions(top_n)
    return _ok({"total_functions": len(hot_funcs), "hot_functions": hot_funcs})


async def _h_generate_performance_report(_args: dict) -> list[types.TextContent]:
    report = profiler_report()
    return [types.TextContent(type="text", text=report)]


# ====== 主入口 ======

async def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    init_db()
    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                InitializationOptions(
                    server_name="browser-automation",
                    server_version="3.0.0",
                    capabilities=types.ServerCapabilities(tools={}),
                ),
            )
    finally:
        await _cleanup_browser()


if __name__ == "__main__":
    asyncio.run(main())