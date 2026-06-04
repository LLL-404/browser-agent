"""直接测试 Camoufox 浏览器控制器"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import asyncio
from agent.core.browser import BrowserController


async def test():
    print("=" * 50)
    print("测试 Camoufox BrowserController")
    print("=" * 50)
    
    ctrl = BrowserController()
    
    print(f"引擎: {ctrl.engine}")
    print(f"正在运行: {ctrl.is_running}")
    
    print("\n启动浏览器...")
    page = await ctrl.start(headless=False)
    print(f"启动结果: page={page is not None}")
    print(f"引擎: {ctrl.engine}")
    
    print("\n导航到 BOSS直聘...")
    result = await ctrl.navigate_to("https://www.zhipin.com/?ka=header-home")
    print(f"导航结果: {result}")
    
    print("\n获取页面内容...")
    text = await ctrl.get_page_text(max_len=1000)
    if text.startswith("错误"):
        print(f"失败: {text}")
    else:
        print(f"页面内容 ({len(text)} chars):")
        print(text[:500])
    
    print("\n反检测状态...")
    status = await ctrl.get_detection_status()
    for k, v in status.items():
        print(f"  {k}: {v}")
    
    print("\n等待3秒后关闭...")
    await asyncio.sleep(3)
    await ctrl.stop()
    print("测试完成!")


if __name__ == "__main__":
    asyncio.run(test())
