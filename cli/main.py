"""求职助手 CLI 入口：支持命令行搜索和交互式搜索两种模式。"""

import asyncio
import argparse
import json
import time
from pathlib import Path

from core.logging_config import setup_logging, get_logger
from core.scraper import (
    search_jobs, analyze_jobs,
    generate_report, generate_chat_prompt,
)
from core.storage import init_db, get_jobs, count_jobs_by_status, update_job_status, JobQuery
from core.exporter import export_for_analysis, import_from_analysis
from core.agent import BrowserAgent

setup_logging()
logger = get_logger("main")


def cmd_search(args):
    result = asyncio.run(search_jobs(
        cities=args.cities.split(",") if args.cities else None,
        keywords=args.keywords.split(",") if args.keywords else None,
        max_detail=args.max_detail,
        headless=args.headless,
    ))
    if result.get("error"):
        print("\n[✗] " + result["error"])


def cmd_analyze(args):
    jobs = asyncio.run(analyze_jobs())
    if not jobs:
        print("没有待分析职位")
        return
    filepath = export_for_analysis(jobs, args.out)
    print(f"已导出 {len(jobs)} 条职位到 {filepath}")
    print(f"请将文件发送给 AI 进行分析，然后运行 analyze --import {filepath}")


def cmd_import(args):
    count = import_from_analysis(args.file)
    print(f"导入了 {count} 条分析结果")


def cmd_report(args):
    report = asyncio.run(generate_report(
        min_score=args.min_score,
        city=args.city,
        top=args.top))
    out = Path(args.out)
    out.write_text(report, encoding="utf-8")
    print(f"报告已保存到 {out}")


def cmd_chat(args):
    prompt = asyncio.run(generate_chat_prompt(args.job_id))
    if prompt:
        print(prompt)
    else:
        print(f"未找到职位 ID: {args.job_id}")


def cmd_status(args):
    update_job_status(args.job_id, args.status)
    print(f"职位 {args.job_id} 状态已更新为: {args.status}")


def cmd_stats(_args):
    counts = count_jobs_by_status()
    total = sum(counts.values())

    print(f"\n{'=' * 40}")
    print(f"  数据库概览：共 {total} 条职位")
    print(f"{'=' * 40}")
    for status, count in sorted(counts.items()):
        label = {"new": "🆕 新抓取", "analyzed": "📊 已分析",
                 "applied": "📤 已投递", "ignored": "🗑 已忽略"}.get(status, status)
        print(f"  {label}: {count}")

    if total > 0:
        print("\n" + "=" * 40)
        print("  最近搜索的城市:")
        from core.storage import get_recent_logs
        logs = get_recent_logs(10)
        for l in logs:
            print(f"    {l[0]} → {l[1]}条 (最后搜索: {l[2]})")

    print()


async def _interactive_session(_cities_str: str, _keywords_str: str, max_detail: int):
    """交互式搜索会话：一次登录，多次搜索。"""
    from playwright.async_api import async_playwright
    from core.anti_detect import ANTI_REDIRECT_SCRIPT, STEALTH_SCRIPT, build_browser_kwargs
    from core.config import get_config
    from core.scraper import (
        _ensure_login, _search_one_city,
        _goto_search, _collect_list_page, _process_job_entry,
    )

    cfg = get_config()

    print("\n" + "=" * 55)
    print("  🔍 BOSS 直聘求职助手 — 交互式模式")
    print("=" * 55)

    async with async_playwright() as p:
        kwargs = build_browser_kwargs(cfg, headless=False)
        context = await p.chromium.launch_persistent_context(**kwargs)
        await context.add_init_script(STEALTH_SCRIPT)
        await context.add_init_script(ANTI_REDIRECT_SCRIPT)
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            if not await _ensure_login(page):
                print("登录失败，退出")
                return

            print("  ✅ 浏览器就绪，已登录\n")
            print("  支持的命令:")
            print("    s <城市> <关键词>    — 搜索（如: s 深圳 普工）")
            print("    regions <数量>       — 按优先级自动搜索多个城市")
            print("    stats                — 查看统计")
            print("    view <N>             — 查看最近 N 条职位")
            print("    report [城市]        — 生成推荐报告")
            print("    help                 — 显示帮助")
            print("    q / quit             — 退出")
            print()

            while True:
                try:
                    raw = input("求职助手> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n  再见！")
                    break

                if not raw:
                    continue

                parts = raw.split()
                cmd = parts[0].lower()

                if cmd in ("q", "quit", "exit"):
                    print("  再见！")
                    break

                elif cmd == "help":
                    print("  命令列表:")
                    print("    s <城市1,城市2,...> <关键词1,关键词2,...>")
                    print("        例: s 深圳,广州 普工,操作工")
                    print("    regions <数量>    — 自动搜索 N 个高优先级城市")
                    print("    stats            — 查看数据库统计")
                    print("    view <N>         — 查看最近 N 条职位")
                    print("    report [城市]    — 导出推荐报告")

                elif cmd == "s":
                    if len(parts) < 3:
                        print("  用法: s <城市> <关键词>")
                        print("  例: s 深圳,广州 普工")
                        continue
                    search_cities = [c.strip() for c in parts[1].split(",")]
                    search_kws = [k.strip() for k in parts[2].split(",")]
                    max_d = int(parts[3]) if len(parts) > 3 else (max_detail or 30)

                    total_start = time.time()
                    total_stored = 0
                    for idx, city in enumerate(search_cities, 1):
                        print(f"\n  📌 [{idx}/{len(search_cities)}] {city}")
                        stats = await _search_one_city(page, city, search_kws, max_d)
                        stored = stats["stored"]
                        total_stored += stored
                        msg = (f"     搜到 {stats['searched']} 条 | "
                               f"入库 {stored} 条 | "
                               f"耗时 {stats['elapsed']:.0f}秒")
                        if stored > 0:
                            print(f"     ✅ {msg}")
                        elif stats['searched'] > 0:
                            print(f"     ⚠ {msg}（全部重复）")
                        else:
                            print(f"     ❌ {msg}")

                    elapsed = time.time() - total_start
                    print(f"\n  🎯 搜索完成: 入库 {total_stored} 条 | 总耗时 {elapsed:.0f}秒")

                elif cmd == "regions":
                    count = int(parts[1]) if len(parts) > 1 else 3
                    searched = set()
                    try:
                        from core.storage import get_searched_cities
                        searched = get_searched_cities()
                    except (ImportError, KeyError):
                        pass

                    all_cities = []
                    for p in ["priority_1", "priority_2", "priority_3", "priority_4"]:
                        for c in cfg.get("cities", {}).get(p, []):
                            if c not in searched:
                                all_cities.append(c)
                    auto_cities = all_cities[:count]

                    if not auto_cities:
                        print("  所有城市已搜索完毕！")
                        continue

                    print(f"  将自动搜索: {', '.join(auto_cities)}")

                    total_start = time.time()
                    total_stored = 0
                    for idx, city in enumerate(auto_cities, 1):
                        print(f"\n  📌 [{idx}/{len(auto_cities)}] {city}")
                        stats = await _search_one_city(page, city, None, max_detail or 30)
                        total_stored += stats["stored"]
                        msg = (f"     搜到 {stats['searched']} 条 | "
                               f"入库 {stats['stored']} 条 | "
                               f"耗时 {stats['elapsed']:.0f}秒")
                        if stats['stored'] > 0:
                            print(f"     ✅ {msg}")
                        elif stats['searched'] > 0:
                            print(f"     ⚠ {msg}（全部重复）")
                        else:
                            print(f"     ❌ {msg}")

                    elapsed = time.time() - total_start
                    print(f"\n  🎯 搜索完成: 入库 {total_stored} 条 | 总耗时 {elapsed:.0f}秒")

                elif cmd == "stats":
                    counts = count_jobs_by_status()
                    total = sum(counts.values())
                    print(f"\n  📊 数据库概览: 共 {total} 条")
                    for status, count in sorted(counts.items()):
                        label = {"new": "  🆕 新抓取", "analyzed": "  📊 已分析",
                                 "applied": "  📤 已投递", "ignored": "  🗑 已忽略"}.get(status, f"  {status}")
                        print(f"{label}: {count}")

                elif cmd == "view":
                    limit = int(parts[1]) if len(parts) > 1 else 10
                    jobs = get_jobs(JobQuery(limit=limit))
                    if not jobs:
                        print("  暂无数据")
                        continue
                    print(f"\n  最近 {min(limit, len(jobs))} 条职位:")
                    print(f"  {'ID':<6} {'标题':<25} {'公司':<16} {'薪资':<12} {'城市'}")
                    print(f"  {'-'*6} {'-'*25} {'-'*16} {'-'*12} {'-'*6}")
                    for j in jobs:
                        bid = j.get("id", "")
                        title = (j.get("title") or "")[:24]
                        company = (j.get("company") or "")[:15]
                        salary = (j.get("salary") or "")[:11]
                        city = j.get("city", "")
                        print(f"  {str(bid):<6} {title:<25} {company:<16} {salary:<12} {city}")

                elif cmd == "report":
                    city = parts[1] if len(parts) > 1 else None
                    rpt = await generate_report(min_score=0, city=city)
                    out = Path(f"report_{city or 'all'}.md")
                    out.write_text(rpt, encoding="utf-8")
                    print(f"  报告已保存到 {out}")

                else:
                    print(f"  未知命令: {cmd}，输入 help 查看帮助")

        finally:
            await context.close()


def cmd_run(args):
    asyncio.run(_interactive_session(
        args.cities or "", args.keywords or "", args.max_detail or 30))


def cmd_serve(_args):
    """启动 MCP Server（通用浏览器自动化 + BOSS 直聘）。"""
    from mcp_server import main as mcp_main
    print("启动通用浏览器自动化 MCP Server...")
    print("请将 MCP 配置添加到 IDE 中。")
    print("支持的工具: browser_* (通用浏览器) + search_jobs 等 (BOSS 直聘)")
    asyncio.run(mcp_main())


async def _browse_session(url: str | None):
    """通用浏览器浏览会话。"""
    agent = BrowserAgent()
    try:
        result = await agent.open(headless=False, url=url or "about:blank")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("\n浏览器已打开。按 Enter 关闭...")
        input()
    finally:
        await agent.close()


def cmd_browse(args):
    asyncio.run(_browse_session(args.url))


def main():
    parser = argparse.ArgumentParser(
        description="通用浏览器自动化助手（支持 BOSS 直聘求职）")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="BOSS交互式搜索（推荐）：一次登录，连续搜索")
    p_run.add_argument("--cities", help="初始搜索城市（可后续修改），逗号分隔")
    p_run.add_argument("--keywords", help="初始搜索关键词（可后续修改），逗号分隔")
    p_run.add_argument("--max-detail", type=int, help="每城市最大入库数")

    p_search = sub.add_parser("search", help="命令行搜索")
    p_search.add_argument("--cities", help="城市，逗号分隔")
    p_search.add_argument("--keywords", help="关键词，逗号分隔")
    p_search.add_argument("--max-detail", type=int, help="每城市最大入库数")
    p_search.add_argument("--headless", action="store_true", help="无头模式")

    p_analyze = sub.add_parser("analyze", help="AI 分析职位")
    p_analyze.add_argument("--out", help="输出文件路径")

    p_import = sub.add_parser("import", help="导入 AI 分析结果")
    p_import.add_argument("file", help="分析结果文件")

    p_report = sub.add_parser("report", help="生成推荐报告")
    p_report.add_argument("--min-score", type=int, default=6, help="最低匹配分数")
    p_report.add_argument("--city", help="筛选城市")
    p_report.add_argument("--top", type=int, help="最大条目数")
    p_report.add_argument("--out", default="report.md", help="输出文件")

    p_chat = sub.add_parser("chat", help="生成招呼语")
    p_chat.add_argument("job_id", type=int, help="职位数据库 ID")

    p_status = sub.add_parser("status", help="更新职位状态")
    p_status.add_argument("job_id", type=int, help="职位 ID")
    p_status.add_argument("status", help="新状态")

    sub.add_parser("stats", help="BOSS数据统计")

    sub.add_parser("serve", help="启动 MCP Server（通用浏览器 + BOSS）")

    sub.add_parser("browse", help="通用浏览器浏览模式").add_argument(
        "--url", help="初始 URL，默认空白页面")

    args = parser.parse_args()

    if not args.command:
        from mcp_server import main as mcp_main
        print("启动通用浏览器自动化 MCP Server...")
        print("支持的工具: browser_* (通用浏览器) + search_jobs 等 (BOSS 直聘)")
        asyncio.run(mcp_main())
        return

    handlers = {
        "run": cmd_run,
        "search": cmd_search,
        "analyze": cmd_analyze,
        "import": cmd_import,
        "report": cmd_report,
        "chat": cmd_chat,
        "status": cmd_status,
        "stats": cmd_stats,
        "serve": cmd_serve,
        "browse": cmd_browse,
    }
    handler = handlers.get(args.command)
    if handler:
        init_db()
        handler(args)
    else:
        parser.print_help()
        print("\n常用命令:")
        print("  serve        → 启动 MCP Server（推荐，通过 IDE AI 使用）")
        print("  run          → BOSS 交互式搜索")
        print("  browse       → 通用浏览器浏览")


if __name__ == "__main__":
    main()
