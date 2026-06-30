from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from schemas import CaseRecord, DialogueRecord, DialogueTurn
from utils import first_non_empty, get_path, read_jsonl


def load_raw_records(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return read_jsonl(path)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [obj for obj in data if isinstance(obj, dict)]
        if isinstance(data, dict):
            for key in ("data", "records", "items"):
                if isinstance(data.get(key), list):
                    return [obj for obj in data[key] if isinstance(obj, dict)]
            return expand_keyed_records(data)
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    raise ValueError(f"Unsupported file type: {path}")


def load_cases(path: Path, case_fields: Dict[str, str]) -> List[CaseRecord]:
    records = load_raw_records(path)
    cases: List[CaseRecord] = []
    for obj in records:
        case_id = first_non_empty([get_configured_value(obj, case_fields.get("case_id"))])
        if not case_id:
            continue
        text_value = get_configured_value(obj, case_fields.get("phenomenon"))
        solution_value = get_configured_value(obj, case_fields.get("solution"))
        cases.append(
            CaseRecord(
                case_id=case_id,
                title=first_non_empty([get_configured_value(obj, case_fields.get("title"))]) or "",
                phenomenon=normalize_text_value(text_value),
                solution=normalize_text_value(solution_value),
                raw=obj,
            )
        )
    return cases


def load_dialogues(path: Path, dialogue_fields: Dict[str, Any]) -> List[DialogueRecord]:
    records = load_raw_records(path)
    dialogues: List[DialogueRecord] = []
    for index, obj in enumerate(records, 1):
        dialogue_id = first_non_empty([get_configured_value(obj, dialogue_fields.get("dialogue_id"))]) or f"dialogue_{index:06d}"
        case_id = extract_dialogue_case_id(obj, dialogue_fields)
        turns = extract_turns(obj, dialogue_fields)
        if not turns:
            continue
        dialogues.append(DialogueRecord(dialogue_id=dialogue_id, case_id=case_id, turns=turns, raw=obj))
    return dialogues


def extract_dialogue_case_id(obj: Dict[str, Any], dialogue_fields: Dict[str, Any]) -> str | None:
    candidates: List[Any] = [get_configured_value(obj, dialogue_fields.get("case_id"))]
    for path in dialogue_fields.get("metadata_case_id_paths", []) or []:
        candidates.append(get_configured_value(obj, path))
    for candidate in candidates:
        if isinstance(candidate, list):
            for item in candidate:
                text = str(item).strip()
                if text:
                    return text
        text = str(candidate).strip() if candidate is not None else ""
        if text:
            return text
    return None


def extract_turns(obj: Dict[str, Any], dialogue_fields: Dict[str, Any]) -> List[DialogueTurn]:
    turns_path = dialogue_fields.get("turns")
    role_key = dialogue_fields.get("role", "role")
    text_key = dialogue_fields.get("text", "text")
    raw_turns = get_configured_value(obj, turns_path)
    turns: List[DialogueTurn] = []

    if isinstance(raw_turns, list):
        if all(isinstance(item, str) for item in raw_turns):
            return parse_role_prefixed_lines(raw_turns)
        for item in raw_turns:
            if not isinstance(item, dict):
                continue
            role = first_non_empty([get_configured_value(item, role_key), item.get("speaker")]) or ""
            text = normalize_text_value(get_configured_value(item, text_key) or item.get("content"))
            if role and text:
                turns.append(DialogueTurn(role=normalize_role(role), text=text))
        return turns

    if isinstance(raw_turns, str):
        return parse_role_prefixed_lines(raw_turns.splitlines())

    # Fallback for flattened records: 用户问题1 / 客服回应1 / ...
    for turn_index in range(1, 100):
        user_text = first_non_empty(
            [
                obj.get(f"用户问题{turn_index}"),
                obj.get(f"用户提问{turn_index}"),
                obj.get(f"user_{turn_index}"),
            ]
        )
        agent_text = first_non_empty(
            [
                obj.get(f"客服回应{turn_index}"),
                obj.get(f"客服回答{turn_index}"),
                obj.get(f"agent_{turn_index}"),
            ]
        )
        if not user_text and not agent_text:
            if turn_index > 1:
                break
            continue
        if user_text:
            turns.append(DialogueTurn(role="user", text=user_text))
        if agent_text:
            turns.append(DialogueTurn(role="agent", text=agent_text))
    return turns


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


def get_configured_value(obj: Dict[str, Any], path: Any) -> Any:
    if not path:
        return None
    if path == "__key__":
        return obj.get("__key__")
    return get_path(obj, str(path))


def normalize_text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def parse_role_prefixed_lines(lines: List[str]) -> List[DialogueTurn]:
    turns: List[DialogueTurn] = []
    pattern = re.compile(r"^\s*(用户|客服|user|agent|assistant)\s*[:：]\s*(.*)$", re.IGNORECASE)
    current_role = ""
    current_text: List[str] = []

    def flush() -> None:
        nonlocal current_role, current_text
        text = "\n".join(current_text).strip()
        if current_role and text:
            turns.append(DialogueTurn(role=normalize_role(current_role), text=text))
        current_role = ""
        current_text = []

    for raw_line in lines:
        line = str(raw_line).strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            flush()
            current_role = match.group(1)
            current_text = [match.group(2).strip()]
        elif current_role:
            current_text.append(line)
    flush()
    return turns


def normalize_role(role: Any) -> str:
    text = str(role).strip().lower()
    if text in {"user", "用户", "customer", "客户"}:
        return "user"
    if text in {"agent", "assistant", "客服", "坐席"}:
        return "agent"
    return text
