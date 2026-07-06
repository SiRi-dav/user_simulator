from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from src.data_loader import expand_keyed_records, get_configured_value, load_raw_records, normalize_text
from src.schemas import DialogueTurn, HistoricalDialogue


DEFAULT_DIALOGUE_FIELDS = {
    "dialogue_id": "dialogue_id",
    "case_id": "case_id",
    "final_case_id": "final_case_id",
    "resolved": "resolved",
    "turns": "turns",
    "speaker": "speaker",
    "text": "text",
}


def load_dialogues(path: Path, dialogue_fields: Dict[str, Any] | None = None) -> List[HistoricalDialogue]:
    fields = dialogue_fields or DEFAULT_DIALOGUE_FIELDS
    records = load_raw_dialogue_records(path)
    dialogues: List[HistoricalDialogue] = []
    for index, record in enumerate(records, 1):
        dialogue_id = normalize_text(get_configured_value(record, fields.get("dialogue_id"))) or f"dialogue_{index:06d}"
        turns = extract_turns(record, fields)
        if not turns:
            continue
        dialogues.append(
            HistoricalDialogue(
                dialogue_id=dialogue_id,
                case_id=optional_text(get_configured_value(record, fields.get("case_id"))),
                final_case_id=optional_text(get_configured_value(record, fields.get("final_case_id"))),
                resolved=optional_bool(get_configured_value(record, fields.get("resolved"))),
                turns=turns,
            )
        )
    return dialogues


def load_raw_dialogue_records(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return load_raw_records(path)
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("data", "records", "items", "dialogues"):
                if isinstance(data.get(key), list):
                    return [item for item in data[key] if isinstance(item, dict)]
            return expand_keyed_records(data)
    raise ValueError(f"Unsupported dialogue file type: {path}")


def extract_turns(record: Dict[str, Any], fields: Dict[str, Any]) -> List[DialogueTurn]:
    raw_turns = get_configured_value(record, fields.get("turns", "turns"))
    speaker_key = str(fields.get("speaker", "speaker"))
    text_key = str(fields.get("text", "text"))
    if isinstance(raw_turns, list):
        if all(isinstance(item, str) for item in raw_turns):
            return parse_role_prefixed_lines(raw_turns)
        turns: List[DialogueTurn] = []
        for item in raw_turns:
            if not isinstance(item, dict):
                continue
            speaker = normalize_speaker(get_configured_value(item, speaker_key) or item.get("role"))
            text = normalize_text(get_configured_value(item, text_key) or item.get("content"))
            if speaker and text:
                turns.append(DialogueTurn(speaker=speaker, text=text))
        return turns
    if isinstance(raw_turns, str):
        return parse_role_prefixed_lines(raw_turns.splitlines())
    return parse_flattened_turns(record)


def parse_role_prefixed_lines(lines: List[str]) -> List[DialogueTurn]:
    turns: List[DialogueTurn] = []
    pattern = re.compile(r"^\s*(用户|客服|user|agent|assistant)\s*[:：]\s*(.*)$", re.IGNORECASE)
    current_speaker = ""
    current_text: List[str] = []

    def flush() -> None:
        nonlocal current_speaker, current_text
        text = "\n".join(current_text).strip()
        speaker = normalize_speaker(current_speaker)
        if speaker and text:
            turns.append(DialogueTurn(speaker=speaker, text=text))
        current_speaker = ""
        current_text = []

    for raw_line in lines:
        line = str(raw_line).strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            flush()
            current_speaker = match.group(1)
            current_text = [match.group(2).strip()]
        elif current_speaker:
            current_text.append(line)
    flush()
    return turns


def parse_flattened_turns(record: Dict[str, Any]) -> List[DialogueTurn]:
    turns: List[DialogueTurn] = []
    for turn_index in range(1, 100):
        user_text = first_non_empty(record.get(f"用户问题{turn_index}"), record.get(f"用户提问{turn_index}"), record.get(f"user_{turn_index}"))
        assistant_text = first_non_empty(record.get(f"客服回应{turn_index}"), record.get(f"客服回答{turn_index}"), record.get(f"agent_{turn_index}"))
        if not user_text and not assistant_text:
            if turn_index > 1:
                break
            continue
        if user_text:
            turns.append(DialogueTurn(speaker="user", text=normalize_text(user_text)))
        if assistant_text:
            turns.append(DialogueTurn(speaker="assistant", text=normalize_text(assistant_text)))
    return turns


def normalize_speaker(value: Any) -> str:
    text = normalize_text(value).lower()
    if text in {"user", "用户", "customer", "客户"}:
        return "user"
    if text in {"assistant", "agent", "客服", "坐席"}:
        return "assistant"
    return text


def optional_text(value: Any) -> str | None:
    text = normalize_text(value)
    return text or None


def optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "resolved", "已解决"}


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if normalize_text(value):
            return value
    return None
