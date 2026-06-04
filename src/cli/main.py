#!/usr/bin/env python3
"""
浏览器 Agent 统一自动化命令行工具

Usage:
    zhipin-cli login              # 登录 BOSS 直聘
    zhipin-cli search [城市] [关键词]  # 搜索职位
    zhipin-cli report             # 生成推荐报告
    zhipin-cli check              # 健康检查
    zhipin-cli server             # 启动 MCP 服务器
    zhipin-cli help               # 显示帮助

完整功能：
    - 登录管理：自动检测并保存登录状态
    - 职位搜索：支持多城市、多关键词批量搜索
    - 报告生成：AI 分析职位并生成推荐报告
    - MCP 服务：启动浏览器自动化协议服务
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from modes.zhipin.scraper import search_jobs, generate_report, health_check
from modes.zhipin.storage import init_db, get_stats
from agent.mcp.server import main as start_server
from shared.logging_config import setup_logging, get_logger
from scripts.login.login_and_save import main as login_main
from scripts.login.login_checker import check_login_status
from scripts.browser.browser_cleaner import clear_browser_profile

setup_logging(log_to_console=True, log_to_file=True)
logger = get_logger("cli")


def run_async(func):
    """异步函数执行包装器，提供统一的异常处理"""
    def wrapper(*args, **kwargs):
        try:
            return asyncio.run(func(*args, **kwargs))
        except asyncio.CancelledError:
            logger.info("⏹ 异步任务被取消")
        except Exception as e:
            logger.error(f"❌ 异步任务执行失败: {e}", exc_info=True)
            raise
    return wrapper


def cmd_login(args):
    """登录命令"""
    logger.info("🔐 开始登录流程...")
    
    login_main()
    
    status = check_login_status()
    if status["logged_in"]:
        logger.info("✅ 登录成功！")
    else:
        logger.error("❌ 登录失败，请重试")


def cmd_search(args):
    """搜索命令"""
    logger.info(f"🔍 开始搜索职位...")
    logger.info(f"   城市: {args.cities}")
    logger.info(f"   关键词: {args.keywords}")
    
    init_db()
    
    result = run_async(search_jobs)(
        cities=args.cities,
        keywords=args.keywords,
        max_detail=args.max_detail,
        headless=args.headless,
        concurrent=args.concurrent
    )
    
    if "error" in result:
        logger.error(f"❌ 搜索失败: {result['error']}")
        return
    
    logger.info("📊 搜索结果汇总:")
    total_stored = 0
    for city, stats in result.items():
        if isinstance(stats, dict) and "stored" in stats:
            logger.info(f"   {city}: 搜到 {stats['searched']} 条，入库 {stats['stored']} 条")
            total_stored += stats["stored"]
    
    logger.info(f"✅ 搜索完成！共入库 {total_stored} 条职位")


def cmd_report(args):
    """生成报告命令"""
    logger.info("📝 生成求职推荐报告...")
    
    init_db()
    report = run_async(generate_report)(
        min_score=args.min_score,
        city=args.city,
        top=args.top
    )
    
    print("\n" + "=" * 80)
    print(report)
    print("=" * 80 + "\n")
    
    # 保存报告到文件
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"📄 报告已保存到: {output_path}")


def cmd_check(args):
    """健康检查命令"""
    logger.info("🔍 执行健康检查...")
    
    result = run_async(health_check)()
    
    print("\n" + "=" * 60)
    print("健康检查结果")
    print("=" * 60)
    print(f"整体状态: {'✅ 健康' if result['healthy'] else '❌ 异常'}")
    print("\n检查详情:")
    for check_name, check_result in result["checks"].items():
        status = "✅" if check_result.get("ok") else "❌"
        note = check_result.get("note", "")
        print(f"  {status} {check_name}: {note or '正常'}")
    
    if result["issues"]:
        print("\n发现问题:")
        for issue in result["issues"]:
            print(f"  ⚠️ {issue}")
    
    print("=" * 60 + "\n")


def cmd_server(args):
    """启动 MCP 服务器命令"""
    logger.info(f"🚀 启动 MCP 服务器...")
    logger.info(f"   端口: {args.port}")
    logger.info(f"   主机: {args.host}")
    logger.info(f"   无头模式: {args.headless}")
    
    # 设置环境变量传递配置
    import os
    if args.port:
        os.environ["MCP_PORT"] = str(args.port)
    if args.host:
        os.environ["MCP_HOST"] = args.host
    if args.headless:
        os.environ["MCP_HEADLESS"] = "true"
    if args.user_data_dir:
        os.environ["MCP_USER_DATA_DIR"] = args.user_data_dir
    
    run_async(start_server)()


def cmd_stats(args):
    """查看统计信息"""
    init_db()
    stats = get_stats()
    
    print("\n" + "=" * 60)
    print("数据库统计信息")
    print("=" * 60)
    print(f"职位总数: {stats.get('total_jobs', 0)}")
    print(f"未分析: {stats.get('new', 0)}")
    print(f"已分析: {stats.get('analyzed', 0)}")
    print(f"已投递: {stats.get('applied', 0)}")
    print(f"已推荐: {stats.get('recommended', 0)}")
    print(f"已搜索城市: {stats.get('searched_cities', 0)}")
    print(f"待搜索城市: {stats.get('total_cities_in_queue', 0)}")
    
    if stats.get('top_cities'):
        print("\n各城市职位分布:")
        for city, count in stats['top_cities'].items():
            print(f"  {city}: {count} 条")
    
    print("=" * 60 + "\n")


def cmd_clean(args):
    """清理命令"""
    logger.info("🧹 清理浏览器配置文件...")
    cleared = clear_browser_profile()
    
    if cleared:
        logger.info(f"✅ 已清理: {', '.join(cleared)}")
    else:
        logger.info("ℹ 没有需要清理的文件")


def main():
    parser = argparse.ArgumentParser(
        prog="zhipin-cli",
        description="BOSS 直聘自动化命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  zhipin-cli login                    # 登录 BOSS 直聘
  zhipin-cli search 深圳 广州 普工     # 在深圳、广州搜索普工职位
  zhipin-cli report --city 深圳       # 生成深圳地区的推荐报告
  zhipin-cli check                    # 检查系统状态
  zhipin-cli server --port 8080       # 启动 MCP 服务器
  zhipin-cli stats                    # 查看统计信息
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # login 命令
    subparsers.add_parser("login", help="登录 BOSS 直聘")
    
    # search 命令
    search_parser = subparsers.add_parser("search", help="搜索职位")
    search_parser.add_argument("cities", nargs="*", default=None, help="目标城市列表")
    search_parser.add_argument("keywords", nargs="*", default=None, help="搜索关键词列表")
    search_parser.add_argument("--max-detail", type=int, default=30, help="每城市最大详情页数")
    search_parser.add_argument("--headless", action="store_true", help="无头模式运行")
    search_parser.add_argument("--no-concurrent", action="store_false", dest="concurrent", help="禁用并发搜索")
    
    # report 命令
    report_parser = subparsers.add_parser("report", help="生成推荐报告")
    report_parser.add_argument("--min-score", type=int, default=6, help="最低匹配分数")
    report_parser.add_argument("--city", type=str, default=None, help="按城市筛选")
    report_parser.add_argument("--top", type=int, default=20, help="最多显示条数")
    report_parser.add_argument("--output", type=str, default=None, help="输出文件路径")
    
    # check 命令
    subparsers.add_parser("check", help="健康检查")
    
    # server 命令
    server_parser = subparsers.add_parser("server", help="启动 MCP 服务器")
    server_parser.add_argument("--port", type=int, default=8080, help="服务端口")
    server_parser.add_argument("--host", type=str, default="localhost", help="绑定主机")
    server_parser.add_argument("--headless", action="store_true", help="无头模式")
    server_parser.add_argument("--user-data-dir", type=str, default="", help="用户数据目录")
    
    # stats 命令
    subparsers.add_parser("stats", help="查看统计信息")
    
    # clean 命令
    subparsers.add_parser("clean", help="清理浏览器缓存")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    commands = {
        "login": cmd_login,
        "search": cmd_search,
        "report": cmd_report,
        "check": cmd_check,
        "server": cmd_server,
        "stats": cmd_stats,
        "clean": cmd_clean,
    }
    
    cmd = commands.get(args.command)
    if cmd:
        try:
            cmd(args)
        except KeyboardInterrupt:
            logger.info("⏹ 用户中断")
        except Exception as e:
            logger.error(f"❌ 命令执行失败: {e}", exc_info=True)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()