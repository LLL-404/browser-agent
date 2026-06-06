"""反检测模块，提供拟人化操作、浏览器指纹伪装和反重定向脚本。"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any

from shared.config import get_config
from shared.logging_config import get_logger

if TYPE_CHECKING:
    from browser_agent.core.executor import SpeedController
    from browser_agent.core.perceiver import PageSnapshot

logger = get_logger("anti_detect")

# 浏览器启动参数，供 scraper.py 和 browser_controller.py 共用
BROWSER_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-webgl",
    "--disable-canvas-aa",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1400,900",
    "--lang=zh-CN",
    "--accept-lang=zh-CN,zh,en-US,en",
]

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def build_browser_kwargs(cfg: dict, headless: bool = False) -> dict:
    """构建 Playwright 浏览器启动参数字典，含代理配置。"""
    kwargs = {
        "user_data_dir": "./browser_profile",
        "headless": headless,
        "viewport": {"width": 1400, "height": 900},
        "user_agent": BROWSER_USER_AGENT,
        "args": BROWSER_STEALTH_ARGS,
    }
    proxy_cfg = cfg.get("proxy", {})
    if proxy_cfg.get("enabled") and proxy_cfg.get("server"):
        proxy = {"server": proxy_cfg["server"]}
        if proxy_cfg.get("username"):
            proxy["username"] = proxy_cfg["username"]
            proxy["password"] = proxy_cfg.get("password", "")
        if proxy_cfg.get("bypass"):
            proxy["bypass"] = proxy_cfg["bypass"]
        kwargs["proxy"] = proxy
    return kwargs


async def random_delay(delay_range: tuple[int, int] | None = None):
    """随机等待指定范围秒数"""
    if delay_range is None:
        cfg = get_config()
        delay_range = tuple(cfg.get("runtime", {}).get("page_scroll_delay", [2, 5]))
    seconds = random.uniform(*delay_range)
    await asyncio.sleep(seconds)


async def human_scroll(page):
    """模拟人类分段滚动列表页"""
    for _ in range(random.randint(3, 6)):
        scroll_y = random.randint(300, 800)
        await page.evaluate(f"window.scrollBy(0, {scroll_y})")
        await asyncio.sleep(random.uniform(0.5, 1.5))


async def human_click(page, element):
    """拟人化点击：先缓慢移动鼠标再点击"""
    box = await element.bounding_box()
    if box:
        x = box["x"] + random.uniform(5, box["width"] - 5)
        y = box["y"] + random.uniform(5, box["height"] - 5)
        # 分步移动鼠标，模拟人类轨迹
        steps = random.randint(3, 6)
        current = await page.evaluate("() => ({x: window.mouseX || 0, y: window.mouseY || 0})")
        for i in range(1, steps + 1):
            t = i / steps
            mx = current.get("x", x) + (x - current.get("x", x)) * t + random.uniform(-3, 3)
            my = current.get("y", y) + (y - current.get("y", y)) * t + random.uniform(-3, 3)
            await page.mouse.move(mx, my)
            await asyncio.sleep(random.uniform(0.03, 0.08))
    await element.click()


def random_viewport() -> dict:
    """随机化窗口尺寸"""
    return {
        "width": random.randint(1200, 1600),
        "height": random.randint(800, 1000),
    }


ANTI_REDIRECT_SCRIPT = """
// 增强版反重定向脚本 — 拦截所有形式的 about:blank 跳转
(() => {
    const BLOCKED = ['about:blank', 'about:blank#/', 'about:blank#blocked', ''];
    const blocked = (url) => BLOCKED.some(b => url === b || (url || '').startsWith('about:blank') || (url || '').trim() === '');

    // 保存原始方法
    const _locDesc = Object.getOwnPropertyDescriptor(Location.prototype, 'href');
    const _origGet = _locDesc.get;
    const _origSet = _locDesc.set;

    if (_origSet) {
        Object.defineProperty(Location.prototype, 'href', {
            get: function() { return _origGet.call(this); },
            set: function(val) {
                if (blocked(val)) { console.log('[AB] blocked href=' + val); return; }
                _origSet.call(this, val);
            },
            configurable: true, enumerable: true
        });
    }

    const _assign = Location.prototype.assign;
    const _replace = Location.prototype.replace;
    Location.prototype.assign = function(url) { if (!blocked(url)) _assign.call(this, url); else console.log('[AB] blocked assign=' + url); };
    Location.prototype.replace = function(url) { if (!blocked(url)) _replace.call(this, url); else console.log('[AB] blocked replace=' + url); };
    
    const _open = window.open;
    window.open = function(url) { if (blocked(url)) return null; return _open.apply(this, arguments); };

    // 拦截 window.location 直接赋值
    let _currentURL = location.href;
    try {
        Object.defineProperty(window, 'location', {
            get: () => location,
            set: (url) => { if (!blocked(url)) location.href = url; }
        });
    } catch(e) {}

    // 隐藏自动化痕迹
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    if (window.chrome && window.chrome.runtime === undefined) {
        window.chrome = { runtime: {} };
    }
    const _permissions = navigator.permissions.query;
    navigator.permissions.query = function(params) {
        if (params.name === 'notifications') return Promise.resolve({ state: 'prompt' });
        return _permissions.call(this, params);
    };

    // 监控 URL 变化，防止被强制跳转
    let lastValidURL = location.href;
    const observer = new MutationObserver(() => {
        if (blocked(location.href) && !blocked(lastValidURL)) {
            console.log('[AB] detected forced redirect to', location.href, 'restoring to', lastValidURL);
            history.go(-1);
        } else if (!blocked(location.href)) {
            lastValidURL = location.href;
        }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });

    console.log('[AB] enhanced anti-detect initialized');
})();
"""


STEALTH_SCRIPT = """
// Comprehensive stealth injection (based on puppeteer-extra-plugin-stealth + MediaCrawler + XDriver)
(() => {
    // 1. Hide webdriver flag (already done in ANTI_REDIRECT_SCRIPT, but double-protect)
    try {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    } catch(e) {}

    // 2. Spoof plugins to look like a real Chrome browser
    try {
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' }
            ],
            configurable: true
        });
    } catch(e) {}

    // 3. Spoof languages to look like a real user
    try {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en'],
            configurable: true
        });
    } catch(e) {}

    // 4. Spoof platform
    try {
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
            configurable: true
        });
    } catch(e) {}

    // 5. Fix chrome.runtime for real Chrome detection
    try {
        window.chrome = window.chrome || {};
        window.chrome.runtime = window.chrome.runtime || {
            id: '',
            connect: () => ({ onDisconnect: { addListener: () => {} }, postMessage: () => {} }),
            sendMessage: () => {}
        };
    } catch(e) {}

    // 6. Spoof permissions (already done, double-protect)
    try {
        const origQuery = navigator.permissions.query;
        navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : origQuery(parameters)
        );
    } catch(e) {}

    // 7. Override navigator.hardwareConcurrency
    try {
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8,
            configurable: true
        });
    } catch(e) {}

    // 8. Override navigator.deviceMemory
    try {
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
            configurable: true
        });
    } catch(e) {}

    // 9. Fix navigator.connection
    try {
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: '4g',
                downlink: 10,
                rtt: 50,
                saveData: false
            }),
            configurable: true
        });
    } catch(e) {}

    // 10. WebRTC IP leak prevention
    try {
        const origRTCPeerConnection = window.RTCPeerConnection;
        if (origRTCPeerConnection) {
            window.RTCPeerConnection = function(config) {
                const pc = new origRTCPeerConnection({
                    ...config,
                    iceServers: [{ urls: 'stun:0.0.0.0' }]
                });
                const origCreateOffer = pc.createOffer;
                pc.createOffer = function(...args) {
                    return origCreateOffer.apply(this, args).then(offer => {
                        offer.sdp = offer.sdp.replace(/a=ice-pwd:.*\\r\\n/g, '');
                        return offer;
                    });
                };
                return pc;
            };
        }
    } catch(e) {}

    // 11. Canvas fingerprint noise injection
    try {
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const origToBlob = HTMLCanvasElement.prototype.toBlob;
        if (origToDataURL) {
            HTMLCanvasElement.prototype.toDataURL = function(...args) {
                const ctx = this.getContext('2d');
                if (ctx) {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] += (Math.random() - 0.5) * 0.5;
                        imageData.data[i + 1] += (Math.random() - 0.5) * 0.5;
                        imageData.data[i + 2] += (Math.random() - 0.5) * 0.5;
                    }
                    ctx.putImageData(imageData, 0, 0);
                }
                return origToDataURL.apply(this, args);
            };
        }
        if (origToBlob) {
            HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {
                const ctx = this.getContext('2d');
                if (ctx) {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] += (Math.random() - 0.5) * 0.5;
                        imageData.data[i + 1] += (Math.random() - 0.5) * 0.5;
                        imageData.data[i + 2] += (Math.random() - 0.5) * 0.5;
                    }
                    ctx.putImageData(imageData, 0, 0);
                }
                return origToBlob.apply(this, [callback, ...args]);
            };
        }
    } catch(e) {}

    // 12. AudioContext fingerprint noise
    try {
        const origCreateBufferSource = (AudioContext.prototype || OfflineAudioContext.prototype)?.createBufferSource;
        // Keep as-is; audio fingerprinting is less commonly checked on BOSS
    } catch(e) {}

    // 13. Spoof screen resolution (looks more realistic)
    try {
        window.screen = Object.assign({}, window.screen, {
            availWidth: 1920,
            availHeight: 1040,
            colorDepth: 24,
            pixelDepth: 24
        });
    } catch(e) {}

    // 14. Override timezone to Asia/Shanghai
    try {
        const origTZ = Intl.DateTimeFormat.prototype.resolvedOptions;
        Intl.DateTimeFormat.prototype.resolvedOptions = function() {
            const opts = origTZ.call(this);
            opts.timeZone = 'Asia/Shanghai';
            return opts;
        };
    } catch(e) {}

    // 15. Spoof IFrame contentWindow (some sites detect this)
    try {
        const origIFrameDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
        if (origIFrameDesc) {
            const origGet = origIFrameDesc.get;
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: function() {
                    const win = origGet.call(this);
                    if (win && win.navigator.webdriver !== undefined) {
                        Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
                    }
                    return win;
                }
            });
        }
    } catch(e) {}

    // 16. Remove automation-related properties from window
    try {
        delete window.cdc_adoQcoasnfdjfhc;
        delete window.webdriver;
    } catch(e) {}

    console.log('[STEALTH] comprehensive stealth initialized');
})();
"""


# ========================================================================
#  AntiDetectSystem — 反爬检测与响应
# ========================================================================

class AntiDetectSystem:
    """反爬检测与自适应响应系统，集成 SpeedController 调整速度模式。

    通过分析页面快照、请求日志、重定向计数等信号，评估当前风险等级（0-4），
    并根据风险等级自动调整 SpeedController 的运作模式。
    """

    _CAPTCHA_SEM_TYPE = "CAPTCHA"  # 验证码元素的语义类型标识

    def __init__(self, speed_controller: SpeedController) -> None:
        self._speed = speed_controller

    async def check(self, snapshot: PageSnapshot, logs: dict) -> int:
        """检测当前页面的反爬风险等级（0-4）。

        参数:
            snapshot: 页面感知快照。
            logs: 请求/重定向日志字典，可包含 failed_requests 和 redirect_count。

        返回:
            risk_level: 0=无风险，1=低风险，2=中风险，3=高风险，4=严重。
        """
        # 最高优先级：验证码或封禁文本 → level 3
        if snapshot.has_captcha:
            logger.warning("检测到验证码，风险等级 3")
            return 3
        if snapshot.has_block_text:
            logger.warning("检测到封禁文本，风险等级 3")
            return 3

        # 检查元素中是否有 CAPTCHA 语义类型 → level 2
        if any(
            getattr(e, "semantic_type", "") == self._CAPTCHA_SEM_TYPE
            for e in snapshot.elements
        ):
            logger.info("检测到 CAPTCHA 语义元素，风险等级 2")
            return 2

        # 检查 403 请求 → level 2
        failed_requests = logs.get("failed_requests", [])
        if isinstance(failed_requests, list):
            if any(
                isinstance(r, dict) and r.get("status") == 403
                for r in failed_requests
            ):
                logger.info("检测到 403 响应，风险等级 2")
                return 2

        # 检查重定向次数过多 → level 2
        redirect_count = logs.get("redirect_count", 0)
        if redirect_count > 3:
            logger.info("重定向次数 %d 超过阈值，风险等级 2", redirect_count)
            return 2

        return 0

    async def respond(self, risk_level: int) -> None:
        """根据风险等级调整 SpeedController 模式。

        参数:
            risk_level: 风险等级 0-4。
        """
        if risk_level == 0:
            self._speed.set_mode("TURBO")
            logger.debug("风险等级 0 → 切换为 TURBO 模式")
        elif risk_level == 1:
            self._speed.set_mode("NORMAL")
            logger.debug("风险等级 1 → 切换为 NORMAL 模式")
        elif risk_level == 2:
            self._speed.set_mode("NORMAL")
            # 额外延迟，给目标服务器喘息时间
            extra = random.uniform(2.0, 5.0)
            logger.info("风险等级 2 → NORMAL + 额外延迟 %.1fs", extra)
            await asyncio.sleep(extra)
        elif risk_level == 3:
            self._speed.set_mode("STEALTH")
            wait = random.uniform(5.0, 15.0)
            logger.warning("风险等级 3 → STEALTH + 等待 %.1fs", wait)
            await asyncio.sleep(wait)
        elif risk_level >= 4:
            self._speed.set_mode("STEALTH")
            logger.error("风险等级 %d → 暂停/停止", risk_level)


# ========================================================================
#  FingerprintManager — 浏览器指纹管理
# ========================================================================

class FingerprintManager:
    """浏览器指纹随机化管理器，生成 Camoufox 兼容的随机指纹选项。

    随机化范围包括：窗口尺寸、操作系统、屏幕参数、地理位置、时区、语言、
    WebGL vendor、字体列表等。
    """

    # 常见窗口预设尺寸
    WINDOW_PRESETS = [
        (1366, 768),
        (1440, 900),
        (1536, 864),
        (1600, 900),
        (1680, 1050),
        (1920, 1080),
        (1920, 1200),
        (2560, 1440),
    ]

    # 操作系统加权选择（Windows 为主）
    OS_WEIGHTED = ["windows"] * 14 + ["macos"] * 3 + ["linux"] * 1

    # 硬件并发数
    HARDWARE_CONCURRENCY = [4, 6, 8, 8, 8, 12, 16]

    # 设备内存
    DEVICE_MEMORY = [4, 8, 8, 8, 16]

    # 像素比例
    PIXEL_RATIOS = [1.0, 1.0, 1.25, 1.5, 1.5, 2.0]

    # 时区列表
    TIMEZONES = [
        "Asia/Shanghai",
        "Asia/Tokyo",
        "Asia/Seoul",
        "Asia/Singapore",
        "Asia/Hong_Kong",
    ]

    # 语言/地区
    LOCALES = [
        "zh-CN",
        "zh-TW",
        "en-US",
        "ja-JP",
    ]

    # WebGL 渲染器伪装
    WEBGL_VENDORS = [
        "Google Inc. (NVIDIA)",
        "Google Inc. (Intel)",
        "Google Inc. (AMD)",
        "Google Inc. (Qualcomm)",
    ]

    WEBGL_RENDERERS = [
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)",
        "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0)",
        "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0)",
    ]

    # 常见系统字体
    FONTS = [
        "Arial", "Times New Roman", "Courier New", "Verdana",
        "SimSun", "Microsoft YaHei", "NSimSun", "FangSong",
        "KaiTi", "SimHei", "DengXian", "YouYuan",
    ]

    @classmethod
    def generate_camoufox_opts(cls) -> dict[str, Any]:
        """生成 Camoufox 浏览器指纹随机选项。

        返回:
            包含 window、os、screen、viewport、geolocation、locale、
            timezone、platform、webgl、fonts 等字段的字典。
        """
        w, h = random.choice(cls.WINDOW_PRESETS)
        screen_w = w + random.randint(0, 400)
        screen_h = h + random.randint(20, 200)

        return {
            "window": (w, h),
            "os": [random.choice(cls.OS_WEIGHTED)],
            "screen": {
                "width": screen_w,
                "height": screen_h,
                "availWidth": screen_w,
                "availHeight": screen_h - random.randint(30, 60),
                "colorDepth": 24,
                "pixelDepth": 24,
            },
            "viewport": {
                "width": w,
                "height": h,
                "deviceScaleFactor": random.choice(cls.PIXEL_RATIOS),
            },
            "geolocation": {
                "latitude": round(random.uniform(20.0, 45.0), 4),
                "longitude": round(random.uniform(100.0, 130.0), 4),
                "accuracy": random.randint(20, 100),
            },
            "locale": random.choice(cls.LOCALES),
            "timezone": random.choice(cls.TIMEZONES),
            "platform": "Win32" if random.choice(cls.OS_WEIGHTED) == "windows" else "MacIntel",
            "hardware_concurrency": random.choice(cls.HARDWARE_CONCURRENCY),
            "device_memory": random.choice(cls.DEVICE_MEMORY),
            "webgl": {
                "vendor": random.choice(cls.WEBGL_VENDORS),
                "renderer": random.choice(cls.WEBGL_RENDERERS),
            },
            "fonts": random.sample(
                cls.FONTS,
                k=random.randint(5, min(len(cls.FONTS), 8)),
            ),
        }


# 兼容旧模块级函数：保留 generate_camoufox_opts 作为函数别名
# 方便还未迁移到 FingerprintManager 的代码继续使用
def generate_camoufox_opts() -> dict[str, Any]:
    """模块级便捷函数，委托给 FingerprintManager.generate_camoufox_opts。"""
    return FingerprintManager.generate_camoufox_opts()
