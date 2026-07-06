from __future__ import annotations

import json
from typing import Any, Dict, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def extract_json_object(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    left = raw.find("{")
    right = raw.rfind("}")
    if left < 0 or right < left:
        raise ValueError(f"LLM output does not contain a JSON object: {text[:300]}")
    value = json.loads(raw[left : right + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM output JSON is not an object")
    return value


def parse_model(model: Type[T], payload: Dict[str, Any]) -> T:
    if hasattr(model, "model_validate"):
        return model.model_validate(payload)
    return model.parse_obj(payload)


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
