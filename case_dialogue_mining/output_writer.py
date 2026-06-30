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
        initial = "；".join(pattern.initial_question_patterns[:3]) or "N/A"
        missing = "；".join(pattern.common_missing_slots[:3]) or "N/A"
        lines.append(f"- {pattern.case_id}: initial={initial}; missing_slots={missing}")
    lines.append("")
    return "\n".join(lines)

