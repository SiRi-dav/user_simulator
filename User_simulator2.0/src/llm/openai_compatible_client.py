from __future__ import annotations

import os
import time
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
        response_format_json: bool = False,
    ):
        self.base_url = normalize_base_url(base_url=base_url, endpoint=endpoint)
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.top_p = top_p
        self.presence_penalty = presence_penalty
        self.top_k = top_k
        self.enable_thinking = enable_thinking
        self.response_format_json = response_format_json

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
            response_format_json=_optional_bool(llm_config.get("response_format_json")) or False,
        )

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_name: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        if not self.base_url or not self.model:
            raise RuntimeError("LLM base_url/model is not configured. Edit config.yaml or set LLM_BASE_URL/LLM_MODEL.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Missing dependency: openai. Install it with `pip install openai`.") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        request_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.response_format_json:
            request_kwargs["response_format"] = {"type": "json_object"}
        if self.top_p is not None:
            request_kwargs["top_p"] = self.top_p
        if self.presence_penalty is not None:
            request_kwargs["presence_penalty"] = self.presence_penalty
        extra_body: Dict[str, Any] = {}
        if self.top_k is not None:
            extra_body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            extra_body["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        if extra_body:
            request_kwargs["extra_body"] = extra_body

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                completion = client.chat.completions.create(**request_kwargs)
                break
            except Exception as exc:  # pragma: no cover - depends on remote LLM service behavior.
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        else:  # pragma: no cover - defensive only.
            raise RuntimeError(f"LLM request failed for schema {schema_name}") from last_error
        choices = completion.choices or []
        if not choices or choices[0].message is None:
            raise RuntimeError(f"LLM returned no choices for schema {schema_name}")
        content = choices[0].message.content or ""
        return extract_json_object(content)


def normalize_base_url(base_url: str = "", endpoint: str = "") -> str:
    value = (base_url or endpoint or "").strip().rstrip("/")
    suffix = "/chat/completions"
    if value.endswith(suffix):
        value = value[: -len(suffix)]
    return value


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
