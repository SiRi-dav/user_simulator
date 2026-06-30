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
        initial = compact_list(pattern.initial_question_patterns, 2)
        missing = compact_list(pattern.common_missing_slots, 2)
        style = pattern.user_style_summary or "N/A"
        lines.append(f"### {pattern.case_id}")
        if pattern.case_to_question_summary:
            lines.append(f"- case to question: {pattern.case_to_question_summary}")
        lines.append(f"- initial patterns: {initial}")
        lines.append(f"- missing slots: {missing}")
        lines.append(f"- user style: {style}")
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

        add_section(lines, "Surface Problem Patterns", pattern.surface_problem_patterns)
        add_section(lines, "Initial Question Patterns", pattern.initial_question_patterns)
        add_section(lines, "Known Facts", pattern.known_facts)
        add_section(lines, "Hidden Facts", pattern.hidden_facts)
        add_section(lines, "Reveal Patterns", pattern.reveal_patterns)
        add_section(lines, "Observed From Dialogue", pattern.observed_from_dialogue)
        add_section(lines, "Inferred From Case", pattern.inferred_from_case)
        add_section(lines, "Uncertain Points", pattern.uncertain_points)
        add_section(lines, "Common Missing Slots", pattern.common_missing_slots)
        add_section(lines, "Opening Question Templates", pattern.opening_question_templates)
        add_dict_section(lines, "Slot Reveal Plan", pattern.slot_reveal_plan)
        add_dict_section(lines, "Simulator Actions", pattern.simulator_actions)
        add_section(lines, "Difficulty Observations", pattern.difficulty_observations)
        add_section(lines, "Simulation Suggestions", pattern.simulation_suggestions)
        add_section(lines, "Evaluation Focus", pattern.evaluation_focus)
        if pattern.case_to_question_summary:
            lines.append("### Case To Question Summary")
            lines.append(pattern.case_to_question_summary)
            lines.append("")
        if pattern.user_style_summary:
            lines.append("### User Style Summary")
            lines.append(pattern.user_style_summary)
            lines.append("")
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


def compact_list(values: List[str], limit: int) -> str:
    if not values:
        return "N/A"
    return "；".join(values[:limit])
