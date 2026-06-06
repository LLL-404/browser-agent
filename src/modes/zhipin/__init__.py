"""BOSS 直聘模式 — 模式注册、MCP 工具定义、CLI 命令绑定。"""

from browser_agent.core.agent import BrowserAgent
from modes.zhipin.scraper import (
    analyze_jobs,
    generate_chat_prompt,
    generate_report,
    health_check,
    import_analysis,
    search_jobs,
)
from modes.zhipin.storage import JobQuery, get_job_by_id, get_jobs, get_stats, update_job_status

__all__ = [
    "search_jobs", "analyze_jobs", "import_analysis",
    "generate_report", "generate_chat_prompt", "health_check",
    "get_jobs", "get_job_by_id", "update_job_status", "get_stats", "JobQuery",
]


def get_mcp_tools():
    from mcp import types  # noqa: PLC0415
    return [
        types.Tool(name="search_jobs", description="在BOSS直聘搜索职位并存入数据库",
                   inputSchema={"type": "object", "properties": {
                       "cities": {"type": "array", "items": {"type": "string"}},
                       "keywords": {"type": "array", "items": {"type": "string"}},
                       "headless": {"type": "boolean"},
                   }}),
        types.Tool(name="list_jobs", description="查询职位列表（轻量，不含完整描述）",
                   inputSchema={"type": "object", "properties": {
                       "status": {"type": "string"}, "limit": {"type": "integer"},
                   }}),
        types.Tool(name="get_job_detail", description="读取单条职位完整信息",
                   inputSchema={"type": "object", "properties": {"job_id": {"type": "integer"}}}),
        types.Tool(name="analyze_jobs", description="获取待分析职位数据，AI分析后写回数据库",
                   inputSchema={"type": "object", "properties": {}}),
        types.Tool(name="boss_get_stats", description="获取求职数据统计概览",
                   inputSchema={"type": "object", "properties": {}}),
        types.Tool(name="update_status", description="更新职位状态追踪投递进展",
                   inputSchema={"type": "object", "properties": {
                       "job_id": {"type": "integer"}, "status": {"type": "string"},
                   }}),
        types.Tool(name="boss_generate_report", description="生成 BOSS 直聘推荐报告",
                   inputSchema={"type": "object", "properties": {}}),
        types.Tool(name="generate_chat_prompt", description="为指定职位生成招呼语 prompt",
                   inputSchema={"type": "object", "properties": {"job_id": {"type": "integer"}}}),
        types.Tool(name="filter_jobs", description="从全国搜索结果中按条件筛选、评分、排名",
                   inputSchema={"type": "object", "properties": {
                       "json_data": {"type": "string"}, "title_kw": {"type": "string"},
                       "min_salary": {"type": "number"}, "must_benefits": {"type": "array", "items": {"type": "string"}},
                   }}),
        types.Tool(name="health_check", description="检查 BOSS 直聘服务是否可用",
                   inputSchema={"type": "object", "properties": {}}),
    ]


async def handle_mcp_call(name: str, arguments: dict, agent: BrowserAgent) -> list | None:
    if name == "search_jobs":
        result = await search_jobs(arguments.get("cities"), arguments.get("keywords"),
                                    headless=arguments.get("headless", False))
    elif name == "list_jobs":
        jobs = get_jobs(JobQuery(status=arguments.get("status"), limit=arguments.get("limit", 50)))
        result = [{"id": j["id"], "title": j["title"], "company": j["company"],
                    "salary": j["salary"], "city": j["city"]} for j in jobs]
    elif name == "get_job_detail":
        result = get_job_by_id(arguments.get("job_id"))
    elif name == "analyze_jobs":
        result = await analyze_jobs()
    elif name == "boss_get_stats":
        result = get_stats()
    elif name == "update_status":
        update_job_status(arguments["job_id"], arguments["status"])
        result = {"ok": True}
    elif name == "boss_generate_report":
        result = await generate_report()
    elif name == "generate_chat_prompt":
        result = generate_chat_prompt(arguments.get("job_id"))
    elif name == "filter_jobs":
        from modes.zhipin.scraper import _filter_jobs_internal  # noqa: PLC0415
        result = _filter_jobs_internal(arguments.get("json_data", ""),
                                        arguments.get("title_kw", ""),
                                        arguments.get("min_salary", 0),
                                        arguments.get("must_benefits", []))
    elif name == "health_check":
        result = await health_check()
    else:
        return None
    from mcp import types  # noqa: PLC0415
    return [types.TextContent(type="text", text=str(result))]


def register_cli(subparsers):
    p = subparsers.add_parser("run", help="BOSS交互式搜索：一次登录，连续搜索")
    p.add_argument("--cities", nargs="*")
    p = subparsers.add_parser("search", help="命令行搜索")
    p.add_argument("keywords", nargs="*")
    p = subparsers.add_parser("analyze", help="AI 分析职位")
    p = subparsers.add_parser("report", help="生成推荐报告")
    p = subparsers.add_parser("chat", help="生成招呼语")
    p.add_argument("job_id", type=int)
    p = subparsers.add_parser("stats", help="BOSS数据统计")
    p = subparsers.add_parser("status", help="更新职位状态")
    p.add_argument("job_id", type=int)
    p.add_argument("new_status", type=str)
    p = subparsers.add_parser("serve", help="启动 MCP Server")
    p = subparsers.add_parser("browse", help="打开 BOSS 浏览器")
    p = subparsers.add_parser("import", help="导入 AI 分析结果")
    p.add_argument("file", type=str)


def _get_engine():
    """延迟导入引擎，避免循环依赖。"""
    from shared.config import get_config  # noqa: PLC0415
    from shared.engine import ScrapingEngine, load_profile  # noqa: PLC0415
    profile = load_profile("zhipin", global_config=get_config())
    return ScrapingEngine(profile)


async def run_cli(args) -> int:
    from shared.logging_config import setup_logging  # noqa: PLC0415
    setup_logging()
    if args.command == "run":
        from modes.zhipin.search_flow import main as run
        await run()
    elif args.command == "search":
        from modes.zhipin.scraper import search_jobs
        await search_jobs(keywords=args.keywords or None)
    elif args.command == "analyze":
        from modes.zhipin.scraper import analyze_jobs
        await analyze_jobs()
    elif args.command == "report":
        from modes.zhipin.scraper import generate_report
        await generate_report()
    elif args.command == "chat":
        from modes.zhipin.scraper import generate_chat_prompt
        print(generate_chat_prompt(args.job_id))
    elif args.command == "stats":
        import json  # noqa: PLC0415

        from modes.zhipin.storage import get_stats  # noqa: PLC0415
        print(json.dumps(get_stats(), ensure_ascii=False, indent=2))
    elif args.command == "status":
        from modes.zhipin.storage import update_job_status
        update_job_status(args.job_id, args.new_status)
        print("状态已更新")
    elif args.command == "serve":
        from browser_agent.mcp.server import main as mcp_main
        await mcp_main()
    elif args.command == "browse":
        from browser_agent.core.browser import BrowserController
        ctrl = BrowserController()
        await ctrl.launch(headless=False)
        engine = _get_engine()
        await ctrl.navigate(engine.url_builder.get_home_url())
        await ctrl.wait_for_login()
    elif args.command == "import":
        from modes.zhipin.exporter import import_from_analysis
        import_from_analysis(args.file)
    else:
        print(f"未知命令: {args.command}")
        return 1
    return 0
