from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.schemas import Case
from src.utils.jsonl import read_jsonl


DEFAULT_CASE_FIELDS = {
    "case_id": "case_id",
    "title": "title",
    "phenomenon": "phenomenon",
    "solution": "solution",
}


def load_cases(path: Path, case_fields: Dict[str, str] | None = None) -> List[Case]:
    fields = case_fields or DEFAULT_CASE_FIELDS
    records = load_raw_records(path)
    cases: List[Case] = []
    for record in records:
        case_id = normalize_text(get_configured_value(record, fields.get("case_id", "case_id")))
        if not case_id:
            continue
        cases.append(
            Case(
                case_id=case_id,
                title=normalize_text(get_configured_value(record, fields.get("title", "title"))),
                phenomenon=normalize_text(get_configured_value(record, fields.get("phenomenon", "phenomenon"))),
                solution=normalize_text(get_configured_value(record, fields.get("solution", "solution"))),
            )
        )
    return cases


def load_raw_records(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return read_jsonl(path)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            return expand_keyed_records(data)
    raise ValueError(f"Unsupported case file type: {path}")


def get_case(cases: List[Case], case_id: str) -> Case:
    for case in cases:
        if case.case_id == case_id:
            return case
    raise ValueError(f"case_id not found: {case_id}")


def expand_keyed_records(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            record = dict(value)
            record.setdefault("__key__", key)
            records.append(record)
        else:
            records.append({"__key__": key, "value": value})
    return records


def get_configured_value(record: Dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    if path == "__key__":
        return record.get("__key__")
    current: Any = record
    for part in str(path).split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()
