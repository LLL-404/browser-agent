"""测试 Camoufox 能否正常启动。"""
import asyncio
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.browser_controller import BrowserController

_CAMOUFOX_ERRORS = (Exception,)


async def main():
    ctrl = BrowserController()
    try:
        await ctrl.start(headless=False)
        print(f"引擎: {ctrl.engine}")
        print(f"浏览器已启动: {ctrl.engine == 'camoufox'}")
    except _CAMOUFOX_ERRORS as e:
        print(f"启动失败: {e}")


asyncio.run(main())