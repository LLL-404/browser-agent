"""对话引擎 — LLM API 调用 + 多轮对话管理 + 知识注入 + 工具调用。"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from shared.config import get_config
from shared.logging_config import get_logger
from shared.retry import retry_async

logger = get_logger("chat.engine")

_PROVIDER_MAP = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "agnes": "https://apihub.agnes-ai.com/v1",
}


@dataclass
class ChatConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    max_tokens: int = 2048
    temperature: float = 0.7
    max_history: int = 20


def _load_chat_config() -> ChatConfig:
    cfg = get_config().get("chat", {})
    api_cfg = cfg.get("api", {})
    context_cfg = cfg.get("context", {})

    provider = api_cfg.get("provider", "deepseek")
    raw_key = api_cfg.get("api_key", "")

    api_key = raw_key
    if raw_key.startswith("${") and raw_key.endswith("}"):
        env_var = raw_key[2:-1]
        api_key = os.environ.get(env_var, "")

    base_url = api_cfg.get("base_url", "") or _PROVIDER_MAP.get(provider, "https://api.deepseek.com/v1")

    return ChatConfig(
        provider=provider,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=api_cfg.get("model", "deepseek-chat"),
        max_tokens=api_cfg.get("max_tokens", 2048),
        temperature=api_cfg.get("temperature", 0.7),
        max_history=context_cfg.get("max_history", 20),
    )


def _build_system_prompt(tone_system_prompt: str, knowledge_context: str = "") -> str:
    parts = [
        tone_system_prompt,
        "",
        "## 可用信息",
        knowledge_context if knowledge_context else "当前没有加载任何知识库。请告知用户可以先加载知识来源。",
        "",
        "## 工具调用",
        "当用户的需求可以通过执行 CLI 命令满足时，你应该生成工具调用。",
        "工具调用格式：`/tool <命令>`",
        "示例：用户问\"统计一下岗位数据\" → 你应该回复 `/tool python -m browser_agent.cli.main --mode zhipin stats`",
        "",
        "注意：/tool 命令需要用户确认后才能执行。",
        "如果命令可能产生破坏性影响，请提醒用户注意。",
    ]
    return "\n".join(parts)


class ChatEngine:
    """对话引擎：管理多轮对话、调用 LLM API、注入知识和工具能力。"""

    def __init__(self, tone_system_prompt: str, knowledge_context: str = ""):
        self.config = _load_chat_config()
        self.system_prompt = _build_system_prompt(tone_system_prompt, knowledge_context)
        _log_key = f"{self.config.provider}/{self.config.model}"
        _mask = self.config.api_key[:8] + "..." if self.config.api_key else "未设置"
        logger.info("ChatEngine 初始化: %s, key=%s", _log_key, _mask)
        self.history: list[dict[str, str]] = []
        self.tone_system_prompt = tone_system_prompt
        self.knowledge_context = knowledge_context

    def update_knowledge(self, context: str) -> None:
        self.knowledge_context = context
        self.system_prompt = _build_system_prompt(self.tone_system_prompt, context)

    def update_tone(self, tone_prompt: str) -> None:
        self.tone_system_prompt = tone_prompt
        self.system_prompt = _build_system_prompt(tone_prompt, self.knowledge_context)

    def _trim_history(self) -> None:
        max_h = self.config.max_history
        if len(self.history) > max_h:
            excess = len(self.history) - max_h
            self.history = self.history[excess:]

    def _build_messages(self, user_input: str) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_input})
        return messages

    async def _call_api(self, messages: list[dict[str, str]]) -> str:
        if not self.config.api_key:
            return "【API 密钥未配置】请在 config.yaml 的 chat.api.api_key 中设置 API Key（支持环境变量 ${VAR_NAME}）。"

        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": False,
        }

        async def _do_request():
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

        try:
            return await retry_async(_do_request, max_retries=2)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                return "【认证失败】API Key 无效或已过期，请检查配置。"
            if status == 429:
                return "【请求过于频繁】API 限流，请稍后再试。"
            return f"【API 错误 {status}】{e}"
        except httpx.TimeoutException:
            return "【请求超时】API 响应超时，请检查网络连接或稍后再试。"
        except Exception as e:
            logger.error("API 调用异常: %s", e)
            return f"【请求失败】{e}"

    async def chat(self, user_input: str) -> str:
        """处理用户输入，返回回复。

        返回可能包含 /tool <cmd> 格式的工具调用标记。
        """
        messages = self._build_messages(user_input)
        reply = await self._call_api(messages)

        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})
        self._trim_history()

        return reply

    def clear_history(self) -> None:
        self.history.clear()
