"""MCP 工具定义 — 所有 Tool schema 集中在此，不包含业务逻辑。"""
from __future__ import annotations

from mcp import types

_CORE_TOOLS = [
    types.Tool(
        name="browser_open",
        description="启动浏览器并导航到指定URL",
        inputSchema={"type": "object", "properties": {
            "url": {"type": "string", "description": "导航目标 URL（默认 about:blank）"},
            "headless": {"type": "boolean", "description": "是否无头模式"},
        }},
    ),
    types.Tool(
        name="browser_close",
        description="关闭浏览器并释放所有资源",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="browser_navigate",
        description="导航到指定 URL",
        inputSchema={"type": "object", "properties": {
            "url": {"type": "string", "description": "目标 URL"},
        }},
    ),
    types.Tool(
        name="browser_navigate_back",
        description="返回到上一页",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="browser_resize",
        description="调整浏览器窗口大小",
        inputSchema={"type": "object", "properties": {
            "width": {"type": "number", "description": "窗口宽度"},
            "height": {"type": "number", "description": "窗口高度"},
        }},
    ),
    types.Tool(
        name="browser_click",
        description="点击页面元素，支持 @e1 ref 或 CSS selector",
        inputSchema={"type": "object", "properties": {
            "ref": {"type": "string", "description": "元素引用，如 @e1"},
            "selector": {"type": "string", "description": "CSS 选择器"},
        }},
    ),
    types.Tool(
        name="browser_type",
        description="在输入框中输入文本",
        inputSchema={"type": "object", "properties": {
            "selector": {"type": "string", "description": "CSS 选择器或 @e1 ref"},
            "text": {"type": "string", "description": "要输入的文本"},
            "clear": {"type": "boolean", "description": "是否先清空已有内容"},
        }},
    ),
    types.Tool(
        name="browser_hover",
        description="悬停在页面元素上",
        inputSchema={"type": "object", "properties": {
            "selector": {"type": "string", "description": "CSS 选择器"},
        }},
    ),
    types.Tool(
        name="browser_select_option",
        description="选择下拉框选项",
        inputSchema={"type": "object", "properties": {
            "selector": {"type": "string", "description": "CSS 选择器"},
            "value": {"type": "string", "description": "选项值"},
        }},
    ),
    types.Tool(
        name="browser_fill_form",
        description="批量填充表单字段",
        inputSchema={"type": "object", "properties": {
            "fields": {
                "type": "array",
                "description": "要填充的字段列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string", "description": "元素引用或 CSS 选择器"},
                        "value": {"type": "string", "description": "要填充的值"},
                        "type": {"type": "string", "description": "字段类型: text/checkbox/select"},
                    },
                },
            },
        }},
    ),
    types.Tool(
        name="browser_file_upload",
        description="上传一个或多个文件",
        inputSchema={"type": "object", "properties": {
            "selector": {"type": "string", "description": "文件输入框的 CSS 选择器"},
            "paths": {
                "type": "array", "items": {"type": "string"},
                "description": "文件绝对路径列表",
            },
        }},
    ),
    types.Tool(
        name="browser_press_key",
        description="模拟键盘按键，如 Enter、Tab、ArrowDown",
        inputSchema={"type": "object", "properties": {
            "key": {"type": "string", "description": "按键名称"},
        }},
    ),
    types.Tool(
        name="browser_snapshot",
        description="获取页面结构快照（可交互元素树 + DOM 摘要 + 无障碍树）",
        inputSchema={"type": "object", "properties": {
            "max_elements": {"type": "number", "description": "最大可交互元素数"},
            "mode": {"type": "string", "enum": ["auto", "dom", "accessibility"],
                     "description": "快照模式: auto/dom/accessibility"},
        }},
    ),
    types.Tool(
        name="browser_take_screenshot",
        description="截取当前页面截图，返回 base64 编码 PNG",
        inputSchema={"type": "object", "properties": {
            "full_page": {"type": "boolean", "description": "是否截取整个页面"},
        }},
    ),
    types.Tool(
        name="browser_text",
        description="获取页面的纯文本内容",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="browser_html",
        description="获取页面 HTML 源码",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="browser_url",
        description="获取当前页面 URL 和标题",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="browser_scroll",
        description="滚动页面",
        inputSchema={"type": "object", "properties": {
            "delta_x": {"type": "number", "description": "水平滚动像素"},
            "delta_y": {"type": "number", "description": "垂直滚动像素"},
        }},
    ),
    types.Tool(
        name="browser_wait_navigation",
        description="等待页面导航完成",
        inputSchema={"type": "object", "properties": {
            "timeout": {"type": "number", "description": "超时毫秒"},
        }},
    ),
    types.Tool(
        name="browser_wait_selector",
        description="等待指定 CSS 选择器的元素出现",
        inputSchema={"type": "object", "properties": {
            "selector": {"type": "string", "description": "CSS 选择器"},
            "timeout": {"type": "number", "description": "超时毫秒"},
        }},
    ),
    types.Tool(
        name="browser_handle_dialog",
        description="处理页面弹窗（alert/confirm/prompt）",
        inputSchema={"type": "object", "properties": {
            "accept": {"type": "boolean", "description": "是否接受（确定/是）"},
            "prompt_text": {"type": "string", "description": "prompt 对话框的输入文本"},
        }},
    ),
    types.Tool(
        name="browser_evaluate",
        description="在页面上执行 JavaScript 表达式并返回结果",
        inputSchema={"type": "object", "properties": {
            "expression": {"type": "string", "description": "JavaScript 表达式"},
            "filename": {"type": "string", "description": "保存结果到文件的路径（可选）"},
        }},
    ),
    types.Tool(
        name="browser_cookie_list",
        description="获取当前页面的所有 Cookie",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="browser_cookie_get",
        description="按名称获取指定 Cookie",
        inputSchema={"type": "object", "properties": {
            "name": {"type": "string", "description": "Cookie 名称"},
        }},
    ),
    types.Tool(
        name="browser_cookie_set",
        description="设置一个 Cookie",
        inputSchema={"type": "object", "properties": {
            "name": {"type": "string", "description": "Cookie 名称"},
            "value": {"type": "string", "description": "Cookie 值"},
            "url": {"type": "string", "description": "Cookie 作用域 URL"},
            "domain": {"type": "string", "description": "Cookie 作用域域名"},
            "path": {"type": "string", "description": "Cookie 路径"},
        }},
    ),
    types.Tool(
        name="browser_storage_state",
        description="导出当前浏览器会话状态（Cookies+Storage）到文件",
        inputSchema={"type": "object", "properties": {
            "save_path": {"type": "string", "description": "保存路径如 sessions/tyc_storage_state.json"},
        }},
    ),
    types.Tool(
        name="browser_storage_state_set",
        description="从文件加载会话状态到当前浏览器",
        inputSchema={"type": "object", "properties": {
            "load_path": {"type": "string", "description": "storage_state 文件路径"},
        }},
    ),
    types.Tool(
        name="browser_localstorage_get",
        description="获取当前页面的 localStorage 内容",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="browser_localstorage_set",
        description="设置 localStorage 键值对",
        inputSchema={"type": "object", "properties": {
            "key": {"type": "string", "description": "localStorage 键"},
            "value": {"type": "string", "description": "localStorage 值"},
        }},
    ),
    types.Tool(
        name="browser_console_messages",
        description="获取浏览器控制台消息",
        inputSchema={"type": "object", "properties": {
            "level": {
                "type": "string",
                "description": "消息级别: error/warning/info/debug",
                "enum": ["error", "warning", "info", "debug"],
            },
        }},
    ),
    types.Tool(
        name="browser_network_requests",
        description="列出页面网络请求",
        inputSchema={"type": "object", "properties": {
            "static": {"type": "boolean", "description": "是否包含静态资源请求"},
        }},
    ),
]

_VISION_TOOLS = [
    types.Tool(
        name="browser_click_coordinate",
        description="在指定屏幕坐标处点击",
        inputSchema={"type": "object", "properties": {
            "x": {"type": "number", "description": "X 坐标"},
            "y": {"type": "number", "description": "Y 坐标"},
            "button": {"type": "string", "description": "鼠标按钮: left/right/middle"},
        }},
    ),
    types.Tool(
        name="browser_drag_coordinate",
        description="从起点坐标拖拽到终点坐标",
        inputSchema={"type": "object", "properties": {
            "start_x": {"type": "number"}, "start_y": {"type": "number"},
            "end_x": {"type": "number"}, "end_y": {"type": "number"},
        }},
    ),
    types.Tool(
        name="browser_hover_coordinate",
        description="在指定坐标处悬停鼠标",
        inputSchema={"type": "object", "properties": {
            "x": {"type": "number"}, "y": {"type": "number"},
        }},
    ),
    types.Tool(
        name="browser_screenshot_save",
        description="截图并保存到 output_dir",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "保存路径"},
            "full_page": {"type": "boolean"},
        }},
    ),
]

_PDF_TOOLS = [
    types.Tool(
        name="browser_pdf_save",
        description="将当前页面保存为 PDF",
        inputSchema={"type": "object", "properties": {
            "path": {"type": "string", "description": "PDF 保存路径"},
        }},
    ),
]

_DEVTOOLS_TOOLS = [
    types.Tool(name="devtools_capture_profiling",
               description="开始捕获性能分析",
               inputSchema={"type": "object", "properties": {}}),
    types.Tool(name="devtools_collect_garbage",
               description="触发垃圾回收",
               inputSchema={"type": "object", "properties": {}}),
    types.Tool(name="devtools_enable_device_emulation",
               description="启用设备模拟",
               inputSchema={"type": "object", "properties": {
                   "width": {"type": "number"}, "height": {"type": "number"},
                   "device_scale_factor": {"type": "number"},
               }}),
    types.Tool(name="devtools_reset_device_emulation",
               description="重置设备模拟",
               inputSchema={"type": "object", "properties": {}}),
    types.Tool(name="devtools_send_command",
               description="发送 CDP 命令",
               inputSchema={"type": "object", "properties": {
                   "cmd": {"type": "string"},
                   "params": {"type": "object"},
               }}),
    types.Tool(name="devtools_set_location",
               description="设置地理位置",
               inputSchema={"type": "object", "properties": {
                   "latitude": {"type": "number"},
                   "longitude": {"type": "number"},
               }}),
]
