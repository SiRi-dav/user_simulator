from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMClient(ABC):
    @abstractmethod
    def generate_text(self, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError

    def generate_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        raw = self.generate_text(messages)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}


class MockLLMClient(LLMClient):
    """Deterministic local fallback for development and tests."""

    def generate_text(self, messages: List[Dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        if "输出 JSON" in last or "JSON" in last:
            return "{}"
        if "改写" in last or "用户口吻" in last:
            return self._simple_user_utterance(last)
        return "我这边还是没解决，麻烦再帮我看一下。"

    @staticmethod
    def _simple_user_utterance(prompt: str) -> str:
        marker = "信息："
        if marker in prompt:
            info = prompt.split(marker, 1)[1].strip()
            info = info.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
            info = info.split("\n", 1)[0].strip()
            if info:
                return info
        return "我不太懂，就是现在用不了。"


class OpenAICompatibleClient(LLMClient):
    """Minimal OpenAI-compatible chat client using only Python stdlib."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        temperature: float = 0.2,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    def generate_text(self, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM connection error: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content", "")


def build_llm_client(
    provider: str = "mock",
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    api_key_env: str = "LLM_API_KEY",
    timeout: int = 60,
    temperature: float = 0.2,
) -> LLMClient:
    if provider == "mock":
        return MockLLMClient()
    if provider in {"openai", "openai-compatible"}:
        resolved_key = api_key or os.getenv(api_key_env, "")
        if not base_url:
            raise ValueError("--llm-base-url is required for openai-compatible provider")
        if not resolved_key:
            raise ValueError(f"LLM API key missing. Set {api_key_env} or pass --llm-api-key")
        if not model:
            raise ValueError("--llm-model is required for openai-compatible provider")
        return OpenAICompatibleClient(
            base_url=base_url,
            api_key=resolved_key,
            model=model,
            timeout=timeout,
            temperature=temperature,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")
