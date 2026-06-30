from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict


class LocalAIClient(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class MockLocalAIClient(LocalAIClient):
    def generate(self, prompt: str) -> str:
        payload = _extract_payload(prompt)
        case = payload.get("case", {}) if isinstance(payload, dict) else {}
        case_id = str(case.get("case_id") or "")
        user_lines = _extract_user_lines(payload)
        first_questions = [line.strip() for line in user_lines[:3] if line.strip()]
        hidden = [line.strip() for line in user_lines[1:5] if line.strip()]
        result = {
            "case_id": case_id,
            "surface_problem_patterns": first_questions[:3],
            "initial_question_patterns": first_questions[:3],
            "known_facts": first_questions[:1],
            "hidden_facts": hidden,
            "reveal_patterns": ["用户通常先描述表面问题，被追问后补充编号、环境、地点或操作细节。"],
            "user_style_summary": "用户表达偏口语化，通常不会主动提供完整排障信息。",
            "common_missing_slots": ["具体系统/页面", "错误码或编号", "操作环境", "期望结果"],
            "difficulty_observations": ["初始问题信息密度较低，需要客服有效追问。"],
            "simulation_suggestions": ["先生成简短开场，再根据客服追问逐步透露隐藏事实。"],
        }
        return json.dumps(result, ensure_ascii=False)


class OpenAICompatibleLocalAIClient(LocalAIClient):
    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: int = 60,
    ):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是企业客服数据分析专家，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Local AI HTTP error {exc.code}: {body}") from exc
        choices = data.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content", "")


def build_local_ai_client(config: Dict[str, Any]) -> LocalAIClient:
    provider = config.get("provider", "mock")
    if provider == "mock":
        return MockLocalAIClient()
    if provider == "openai-compatible":
        api_key_env = config.get("api_key_env", "LOCAL_AI_API_KEY")
        return OpenAICompatibleLocalAIClient(
            endpoint=config["endpoint"],
            model=config["model"],
            api_key=os.getenv(api_key_env, ""),
            temperature=float(config.get("temperature", 0.2)),
            max_tokens=int(config.get("max_tokens", 2048)),
            timeout=int(config.get("timeout", 60)),
        )
    raise ValueError(f"Unsupported local_ai provider: {provider}")


def _extract_payload(prompt: str) -> Dict[str, Any]:
    marker = "输入数据："
    start = prompt.find(marker)
    if start >= 0:
        text = prompt[start + len(marker) :].strip()
    else:
        text = prompt
    left = text.find("{")
    right = text.rfind("}")
    if left < 0 or right < left:
        return {}
    try:
        return json.loads(text[left : right + 1])
    except json.JSONDecodeError:
        return {}


def _extract_user_lines(payload: Dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for dialogue in payload.get("dialogues", []) if isinstance(payload, dict) else []:
        for line in str(dialogue).splitlines():
            if line.startswith("用户:") or line.startswith("用户："):
                lines.append(line.split(":", 1)[-1].split("：", 1)[-1].strip())
    return lines
