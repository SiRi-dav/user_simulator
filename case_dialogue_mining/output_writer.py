from __future__ import annotations
from pathlib import Path
from typing import Dict, List

from schemas import CaseDialoguePair, CaseQuestionPattern, MiningStats, to_dict
from utils import write_jsonl


def write_outputs(
    pairs: List[CaseDialoguePair],
    patterns: List[CaseQuestionPattern],
    errors: List[Dict],
    stats: MiningStats,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_pair_summary(pairs, output_dir / "case_dialogue_pairs.jsonl")
    write_jsonl([to_dict(pattern) for pattern in patterns], output_dir / "question_patterns.jsonl")
    write_jsonl(errors, output_dir / "analysis_errors.jsonl")
    (output_dir / "question_patterns.readable.md").write_text(
        build_readable_patterns_report(patterns),
        encoding="utf-8",
    )
    (output_dir / "summary_report.md").write_text(
        build_summary_report(pairs, patterns, stats),
        encoding="utf-8",
    )


def write_pair_summary(pairs: List[CaseDialoguePair], path: Path) -> None:
    records = []
    for pair in pairs:
        records.append(
            {
                "case_id": pair.case.case_id,
                "case_title": pair.case.title,
                "dialogue_count": len(pair.dialogues),
                "dialogue_ids": [dialogue.dialogue_id for dialogue in pair.dialogues],
            }
        )
    write_jsonl(records, path)


def build_summary_report(
    pairs: List[CaseDialoguePair],
    patterns: List[CaseQuestionPattern],
    stats: MiningStats,
) -> str:
    avg = stats.matched_dialogues / stats.matched_cases if stats.matched_cases else 0
    lines = [
        "# Case-Dialogue Pair Mining Report",
        "",
        "## Basic Statistics",
        f"- Total cases: {stats.total_cases}",
        f"- Total dialogues: {stats.total_dialogues}",
        f"- Matched cases: {stats.matched_cases}",
        f"- Matched dialogues: {stats.matched_dialogues}",
        f"- Average dialogues per case: {avg:.2f}",
        f"- Unmatched cases: {stats.unmatched_cases}",
        f"- Dialogues missing case_id: {stats.missing_case_id_dialogues}",
        f"- Dialogues with unknown case_id: {stats.unknown_case_id_dialogues}",
        "",
        "## Top Cases by Dialogue Count",
    ]
    for pair in sorted(pairs, key=lambda item: len(item.dialogues), reverse=True)[:20]:
        lines.append(f"- {pair.case.case_id} | {pair.case.title} | dialogues: {len(pair.dialogues)}")

    lines.extend(["", "## Common User Question Patterns"])
    for pattern in patterns[:20]:
        if pattern.parse_error:
            lines.append(f"- {pattern.case_id}: analysis failed ({pattern.parse_error})")
            continue
        behavior = pattern.behavior_model
        plan = pattern.simulation_plan
        understanding = pattern.case_understanding
        initial = compact_list(get_str_list(behavior, "initial_question_patterns"), 2)
        missing = compact_list(get_str_list(behavior, "common_missing_slots"), 2)
        style = compact_list(get_str_list(behavior, "expression_style_patterns"), 2)
        lines.append(f"### {pattern.case_id}")
        if understanding.get("case_to_question_summary"):
            lines.append(f"- case to question: {understanding.get('case_to_question_summary')}")
        lines.append(f"- initial patterns: {initial}")
        lines.append(f"- missing slots: {missing}")
        lines.append(f"- expression style: {style}")
        focus = compact_list(get_str_list(plan, "evaluation_focus"), 2)
        lines.append(f"- evaluation focus: {focus}")
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def build_readable_patterns_report(patterns: List[CaseQuestionPattern]) -> str:
    lines = [
        "# Question Pattern Review",
        "",
        "This file is generated from question_patterns.jsonl for human review.",
        "",
    ]
    for index, pattern in enumerate(patterns, start=1):
        lines.append(f"## {index}. {pattern.case_id}")
        if pattern.parse_error:
            lines.append(f"- parse error: {pattern.parse_error}")
            lines.append("")
            continue

        add_dict_overview(lines, "Case Understanding", pattern.case_understanding)
        add_dialogue_level_section(lines, get_dict_list(pattern.behavior_model, "dialogue_level_patterns"))
        add_dict_overview(lines, "Behavior Model", pattern.behavior_model, skip_keys={"dialogue_level_patterns"})
        add_dict_overview(lines, "Simulation Plan", pattern.simulation_plan)
    return "\n".join(lines)


def add_section(lines: List[str], title: str, values: List[str]) -> None:
    if not values:
        return
    lines.append(f"### {title}")
    for value in values:
        lines.append(f"- {value}")
    lines.append("")


def add_dict_section(lines: List[str], title: str, values: List[Dict]) -> None:
    if not values:
        return
    lines.append(f"### {title}")
    for value in values:
        parts = [f"{key}: {item}" for key, item in value.items() if item not in (None, "")]
        lines.append(f"- {'; '.join(parts)}")
    lines.append("")


def add_dict_overview(lines: List[str], title: str, value: Dict, skip_keys: set[str] | None = None) -> None:
    if not value:
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


def add_dialogue_level_section(lines: List[str], values: List[Dict]) -> None:
    if not values:
        return
    lines.append("### Dialogue Level Patterns")
    for index, value in enumerate(values, start=1):
        dialogue_id = value.get("dialogue_id") or f"dialogue_{index}"
        lines.append(f"#### {index}. {dialogue_id}")
        scalar_fields = [
            ("surface_problem", "surface_problem"),
            ("initial_question", "initial_question"),
            ("expression_style", "expression_style"),
        ]
        for key, label in scalar_fields:
            item = value.get(key)
            if item:
                lines.append(f"- {label}: {item}")
        list_fields = [
            ("known_facts", "known_facts"),
            ("hidden_facts", "hidden_facts"),
            ("missing_slots", "missing_slots"),
            ("reveal_path", "reveal_path"),
            ("evidence", "evidence"),
        ]
        for key, label in list_fields:
            items = value.get(key)
            if isinstance(items, list) and items:
                lines.append(f"- {label}: {format_list_items(items)}")
        lines.append("")


def compact_list(values: List[str], limit: int) -> str:
    if not values:
        return "N/A"
    return "；".join(values[:limit])


def get_str_list(record: Dict, key: str) -> List[str]:
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def get_dict_list(record: Dict, key: str) -> List[Dict]:
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def format_list_items(items: List) -> str:
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
