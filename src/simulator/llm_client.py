from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List


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

