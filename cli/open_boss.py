"""打开 Camoufox 浏览器并导航到 BOSS直聘。"""
import asyncio
from core.browser_controller import BrowserController
from core.logging_config import setup_logging, get_logger

setup_logging(log_to_console=True, log_to_file=True)
logger = get_logger("open_boss")


async def main():
    ctrl = BrowserController()
    logger.info("HAS_CAMOUFOX: %s", ctrl.has_camoufox)
    ok = await ctrl.start(headless=False, use_camoufox=True)
    if not ok or not ctrl.engine:
        logger.error("浏览器启动失败")
        return
    logger.info("引擎: %s", ctrl.engine)
    await ctrl.navigate_to("https://www.zhipin.com/")
    await asyncio.sleep(2)
    title = await ctrl.get_page_title()
    text = await ctrl.get_page_text(500)
    logger.info("页面标题: %s", title)
    logger.info("页面文本: %s", text[:300])
    logger.info("浏览器已打开，按 Ctrl+C 关闭")
    try:
        while True:
            await asyncio.sleep(10)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await ctrl.stop()


asyncio.run(main())