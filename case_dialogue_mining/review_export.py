from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\- ]{6,}\d)(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://\S+")
LONG_ID_RE = re.compile(r"(?<![A-Za-z0-9])\d{6,}(?![A-Za-z0-9])")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export readable and masked review files from question_patterns.jsonl.")
    parser.add_argument("--input", default="outputs/question_patterns.jsonl", help="Path to question_patterns.jsonl")
    parser.add_argument("--output", default="outputs/question_patterns.review.md", help="Path to markdown output")
    parser.add_argument("--jsonl-output", default="outputs/question_patterns.review.masked.jsonl", help="Path to masked jsonl output")
    parser.add_argument("--limit", type=int, default=30, help="Maximum records to export. Use 0 for all records.")
    parser.add_argument("--keep-raw", action="store_true", help="Keep raw_ai_response in the masked jsonl output")
    args = parser.parse_args()

    records = read_jsonl(Path(args.input))
    if args.limit > 0:
        records = records[: args.limit]

    masked_records = [mask_record(record, keep_raw=args.keep_raw) for record in records]
    write_jsonl(masked_records, Path(args.jsonl_output))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(build_markdown(masked_records), encoding="utf-8")

    print(f"Loaded records: {len(records)}")
    print(f"Markdown written to: {args.output}")
    print(f"Masked JSONL written to: {args.jsonl_output}")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(records: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def mask_record(record: Dict[str, Any], keep_raw: bool) -> Dict[str, Any]:
    masked = {}
    for key, value in record.items():
        if key == "raw_ai_response" and not keep_raw:
            continue
        masked[key] = mask_value(value)
    return masked


def mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    if isinstance(value, dict):
        return {key: mask_value(item) for key, item in value.items()}
    return value


def mask_text(text: str) -> str:
    text = URL_RE.sub("[URL]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[NUMBER]", text)
    text = LONG_ID_RE.sub("[NUMBER]", text)
    return text


def build_markdown(records: List[Dict[str, Any]]) -> str:
    lines = ["# Question Pattern Review", ""]
    for index, record in enumerate(records, start=1):
        lines.append(f"## {index}. {record.get('case_id', 'UNKNOWN')}")
        append_dict_overview(lines, "Case Understanding", record.get("case_understanding", {}))
        behavior = record.get("behavior_model", {})
        if isinstance(behavior, dict):
            append_dialogue_level_patterns(lines, behavior.get("dialogue_level_patterns", []))
        append_dict_overview(lines, "Behavior Model", behavior, skip_keys={"dialogue_level_patterns"})
        append_dict_overview(lines, "Simulation Plan", record.get("simulation_plan", {}))
    return "\n".join(lines)


def append_list(lines: List[str], title: str, values: List[str]) -> None:
    if not values:
        return
    lines.append(f"### {title}")
    for value in values:
        lines.append(f"- {value}")
    lines.append("")


def append_dict_list(lines: List[str], title: str, values: List[Dict[str, Any]]) -> None:
    if not values:
        return
    lines.append(f"### {title}")
    for value in values:
        if not isinstance(value, dict):
            continue
        parts = [f"{key}: {item}" for key, item in value.items() if item not in (None, "")]
        lines.append(f"- {'; '.join(parts)}")
    lines.append("")


def append_dict_overview(
    lines: List[str],
    title: str,
    value: Dict[str, Any],
    skip_keys: set[str] | None = None,
) -> None:
    if not isinstance(value, dict) or not value:
        return
    skip_keys = skip_keys or set()
    lines.append(f"### {title}")
    for key, item in value.items():
        if key in skip_keys or item in (None, "", []):
            continue
        if isinstance(item, list):
            compact = "；".join(str(part) for part in item[:6])
            if len(item) > 6:
                compact += "；..."
            lines.append(f"- {key}: {compact}")
        elif isinstance(item, dict):
            compact = "；".join(f"{sub_key}: {sub_value}" for sub_key, sub_value in item.items() if sub_value)
            lines.append(f"- {key}: {compact}")
        else:
            lines.append(f"- {key}: {item}")
    lines.append("")


def append_dialogue_level_patterns(lines: List[str], values: List[Dict[str, Any]]) -> None:
    if not values:
        return
    lines.append("### Dialogue Level Patterns")
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            continue
        dialogue_id = value.get("dialogue_id") or f"dialogue_{index}"
        lines.append(f"#### {index}. {dialogue_id}")
        for key in ("surface_problem", "initial_question", "expression_style"):
            item = value.get(key)
            if item:
                lines.append(f"- {key}: {item}")
        for key in ("known_facts", "hidden_facts", "missing_slots", "reveal_path", "evidence"):
            items = value.get(key)
            if isinstance(items, list) and items:
                lines.append(f"- {key}: {format_list_items(items)}")
        lines.append("")


def format_list_items(items: List[Any]) -> str:
    parts = []
    for item in items:
        if isinstance(item, dict):
            condition = item.get("condition")
            reveal = item.get("reveal")
            phrase = item.get("example_user_phrase")
            compact = " / ".join(str(part) for part in (condition, reveal, phrase) if part)
            parts.append(compact or str(item))
        else:
            parts.append(str(item))
    return "；".join(parts)


if __name__ == "__main__":
    main()
