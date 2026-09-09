# app/providers/llm.py
"""生成模型适配层（LLM Provider）。

- OllamaLLM：经 ``/api/chat`` 支持流式（SSE）与一次性补全（生产默认）。
- FakeLLM：离线/测试用确定性补全。
业务层只依赖协议，替换后端不改动 QA/改写逻辑。
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import LLMUnavailable

logger = logging.getLogger(__name__)

ChatMessage = dict[str, str]  # {"role": "user|system|assistant", "content": "..."}


class LLMProvider(Protocol):
    model: str

    def complete(self, messages: list[ChatMessage], temperature: float = 0.2) -> str: ...

    def stream(self, messages: list[ChatMessage], temperature: float = 0.2) -> Iterator[str]: ...

    def health(self) -> dict: ...


class OllamaLLM:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_s
        self.temperature = settings.llm_temperature
        self.num_ctx = settings.llm_num_ctx

    def _payload(self, messages: list[ChatMessage], temperature: float, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }

    def complete(self, messages: list[ChatMessage], temperature: float | None = None) -> str:
        temp = self.temperature if temperature is None else temperature
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/api/chat",
                    json=self._payload(messages, temp, False),
                )
                resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama 生成调用失败: %s", exc)
            raise LLMUnavailable(f"生成服务不可用: {exc}") from exc

    def stream(self, messages: list[ChatMessage], temperature: float | None = None) -> Iterator[str]:
        temp = self.temperature if temperature is None else temperature
        try:
            with httpx.Client(timeout=self.timeout) as client, client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=self._payload(messages, temp, True),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = obj.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if obj.get("done"):
                        break
        except LLMUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama 流式生成失败: %s", exc)
            raise LLMUnavailable(f"生成服务不可用: {exc}") from exc

    def health(self) -> dict:
        try:
            with httpx.Client(timeout=3) as client:
                r = client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "model": self.model, "available": models}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "error": str(exc)}


class FakeLLM:
    """离线确定性生成：仅用于测试与无模型环境的链路验证。"""

    def __init__(self, model: str = "fake-llm") -> None:
        self.model = model

    def _render(self, messages: list[ChatMessage]) -> str:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"[FakeLLM] 依据检索材料作答。问题：{user[:40]}"

    def complete(self, messages: list[ChatMessage], temperature: float | None = None) -> str:
        return self._render(messages)

    def stream(self, messages: list[ChatMessage], temperature: float | None = None) -> Iterator[str]:
        text = self._render(messages)
        for i in range(0, len(text), 8):
            yield text[i : i + 8]

    def health(self) -> dict:
        return {"ok": True, "model": self.model, "available": [self.model]}
