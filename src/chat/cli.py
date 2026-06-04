"""聊天 Agent CLI — 交互式 / 单次问答模式。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from shared.logging_config import get_logger, setup_logging

from chat.engine import ChatEngine
from chat.knowledge import KnowledgeBase
from chat.tone import get_default_tone, get_tone_names, get_tone_prompt, format_tone_help
from chat.tools import execute, format_tool_prompt

logger = get_logger("chat.cli")

_BANNER = """
╔══════════════════════════════════════════════╗
║    Chat Agent — 浏览器框架对话助手            ║
║                                               ║
║  /tone <预设>  切换语气                       ║
║  /load <路径>  加载知识文档                   ║
║  /sources      查看知识来源                   ║
║  /auto         切换自动确认模式               ║
║  /help         帮助                           ║
║  /exit         退出                           ║
╚══════════════════════════════════════════════╝
"""


class ChatCLI:
    def __init__(self, knowledge_dir: str | None = None, knowledge_db: str | None = None, tone: str | None = None):
        self.tone_name = tone or get_default_tone()
        tone_prompt = get_tone_prompt(self.tone_name)

        self.kb = KnowledgeBase()
        self.kb.auto_load()

        tool_prompt = format_tool_prompt()
        full_knowledge = self.kb.format_context()
        combined_context = f"{full_knowledge}\n\n{tool_prompt}" if full_knowledge else tool_prompt

        self.engine = ChatEngine(tone_prompt, combined_context)
        self.auto_confirm = False

    async def handle_message(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""

        if text == "/exit":
            return "__EXIT__"

        if text == "/help":
            return _BANNER.strip()

        if text == "/sources":
            return self.kb.source_summary

        if text.startswith("/tone "):
            name = text[6:].strip()
            names = get_tone_names()
            if name in names:
                self.tone_name = name
                self.engine.update_tone(get_tone_prompt(name))
                return f"语气已切换为: {name}"
            return f"未知语气: {name}。可用: {', '.join(names)}"

        if text.startswith("/load "):
            path = text[6:].strip()
            result = self.kb.load_file(path)
            self.engine.update_knowledge(self.kb.format_context())
            return result

        if text == "/auto":
            self.auto_confirm = not self.auto_confirm
            return f"自动确认模式: {'开启' if self.auto_confirm else '关闭'}"

        reply = await self.engine.chat(text)

        if reply.startswith("/tool "):
            cmd = reply[6:].strip()
            if self.auto_confirm:
                result = execute(cmd)
                return self._format_tool_result(cmd, result)
            return f"准备执行命令: {cmd}\n输入 y 确认执行，输入 n 取消，或输入其他内容回复。\n(可用 /auto 开启自动确认模式)"

        return reply

    @staticmethod
    def _format_tool_result(cmd: str, result: dict) -> str:
        lines = [f"执行命令: {cmd}", f"返回码: {result.get('returncode', -1)}"]
        if result.get("ok"):
            output = result.get("output", "")
            if output:
                lines.append(f"输出:\n{output[:3000]}")
            else:
                lines.append("(无输出)")
        else:
            lines.append(f"错误: {result.get('error', '未知错误')}")
        return "\n".join(lines)

    async def interactive_loop(self):
        print(_BANNER)
        print(f"当前语气: {self.tone_name}")
        print(f"已加载 {len(self.kb.sources)} 个知识来源")
        print()

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue

            reply = await self.handle_message(user_input)

            if reply == "__EXIT__":
                break

            print(f"\nAgent: {reply}\n")

            if reply.startswith("准备执行命令:"):
                confirm = input("确认? (y/n): ").strip().lower()
                if confirm == "y":
                    cmd = reply.split("\n", 1)[0].replace("准备执行命令: ", "")
                    result = execute(cmd)
                    print(f"\nAgent: {self._format_tool_result(cmd, result)}\n")

        print("再见！")

    async def single_query(self, query: str):
        reply = await self.engine.chat(query)
        print(reply)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="chat-agent — 浏览器框架对话助手")
    parser.add_argument("--knowledge-dir", help="知识文档目录路径")
    parser.add_argument("--knowledge-db", help="知识数据库路径")
    parser.add_argument("--tone", choices=get_tone_names(), default=None, help="语气预设")
    parser.add_argument("--query", "-q", help="单次问答模式：直接提问")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    return parser


def main():
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args()

    cli = ChatCLI(knowledge_dir=args.knowledge_dir, knowledge_db=args.knowledge_db, tone=args.tone)

    if args.query:
        asyncio.run(cli.single_query(args.query))
    else:
        asyncio.run(cli.interactive_loop())


if __name__ == "__main__":
    main()
