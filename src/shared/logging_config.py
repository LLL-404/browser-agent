"""统一日志配置模块，提供标准 logging 支持 console + file 双输出。

日志级别可通过 config.yaml 的 logging.level 配置，默认 INFO。
日志文件默认写入 data/logs/，按天轮转。
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

_logger: logging.Logger | None = None


def _get_log_level(config: dict | None) -> int:
    if config is None:
        return logging.INFO
    level_name = config.get("logging", {}).get("level", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def setup_logging(config: dict | None = None,
                  log_to_console: bool = True,
                  log_to_file: bool = True,
                  console_stream=sys.stderr) -> logging.Logger:
    """初始化全局日志系统，返回 root logger。

    参数:
        config: 配置字典，从中读取 logging.level。
        log_to_console: 是否输出到控制台。
        log_to_file: 是否输出到文件（data/logs/）。
        console_stream: 控制台输出流，默认 stderr（避免污染 MCP stdio）。
    """
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("browser_agent")
    logger.setLevel(_get_log_level(config))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-5s %(name)s | %(message)s",
        datefmt="%m-%d %H:%M:%S",
    )

    # 控制台输出
    if log_to_console:
        ch = logging.StreamHandler(console_stream)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    # 文件输出（按天轮转）
    if log_to_file:
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        fh = logging.FileHandler(
            log_dir / f"scraper_{date_str}.log",
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    _logger = logger
    return logger


def get_logger(name: str = "") -> logging.Logger:
    """获取命名 logger，自动继承全局配置。

    参数:
        name: 模块/功能名称，如 "scraper"。

    返回:
        已配置的 Logger 实例。若未初始化则使用默认配置。
    """
    if _logger is None:
        setup_logging()
    full_name = f"browser_agent.{name}" if name else "browser_agent"
    return logging.getLogger(full_name)
