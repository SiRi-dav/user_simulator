from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from src.llm.llm_client import LLMClient
from src.utils.json_utils import extract_json_object


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        base_url: str = "",
        endpoint: str = "",
        api_key: str = "",
        model: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: int = 120,
        top_p: float | None = None,
        presence_penalty: float | None = None,
        top_k: int | None = None,
        enable_thinking: bool | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.top_p = top_p
        self.presence_penalty = presence_penalty
        self.top_k = top_k
        self.enable_thinking = enable_thinking

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "OpenAICompatibleClient":
        llm_config = config.get("llm", {})
        return cls(
            base_url=os.getenv("LLM_BASE_URL") or str(llm_config.get("base_url") or ""),
            endpoint=os.getenv("LLM_ENDPOINT") or str(llm_config.get("endpoint") or ""),
            api_key=os.getenv("LLM_API_KEY") or str(llm_config.get("api_key") or ""),
            model=os.getenv("LLM_MODEL") or str(llm_config.get("model") or ""),
            temperature=float(os.getenv("LLM_TEMPERATURE") or llm_config.get("temperature", 0.2)),
            max_tokens=int(llm_config.get("max_tokens", 4096)),
            timeout=int(llm_config.get("timeout", 120)),
            top_p=_optional_float(llm_config.get("top_p")),
            presence_penalty=_optional_float(llm_config.get("presence_penalty")),
            top_k=_optional_int(llm_config.get("top_k")),
            enable_thinking=_optional_bool(llm_config.get("enable_thinking")),
        )

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_name: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        if not (self.endpoint or self.base_url) or not self.model:
            raise RuntimeError("LLM endpoint/base_url/model is not configured. Edit config.yaml or set LLM_ENDPOINT/LLM_MODEL.")
        endpoint = self.endpoint or self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.presence_penalty is not None:
            payload["presence_penalty"] = self.presence_penalty
        if self.top_k is not None:
            payload["top_k"] = self.top_k
        if self.enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP error {exc.code}: {body}") from exc
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"LLM returned no choices for schema {schema_name}")
        content = (choices[0].get("message") or {}).get("content", "")
        return extract_json_object(content)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
