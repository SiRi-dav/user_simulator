from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .schemas import CaseGroundedDialogue, CaseSeed, DialogueTurn, NormalizedDialogue, Resolution


def read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc


def write_jsonl(records: Iterable[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_dialogues(path: Path) -> List[NormalizedDialogue]:
    dialogues: List[NormalizedDialogue] = []
    for obj in read_jsonl(path):
        turns = [
            DialogueTurn(
                role=t.get("role", ""),
                text=t.get("text", ""),
                turn_index=t.get("turn_index"),
                label=t.get("label"),
                metadata=t.get("metadata", {}),
            )
            for t in obj.get("turns", [])
        ]
        resolution_obj = obj.get("resolution", {}) or {}
        resolution = Resolution(
            case_id=resolution_obj.get("case_id"),
            title=resolution_obj.get("title"),
            success=resolution_obj.get("success"),
        )
        dialogues.append(
            NormalizedDialogue(
                dialogue_id=str(obj.get("dialogue_id", "")),
                turns=turns,
                resolution=resolution,
                metadata=obj.get("metadata", {}),
            )
        )
    return dialogues


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _join_text(value: Any) -> str:
    return "\n".join(_as_text_list(value))


def load_cases(path: Path) -> Dict[str, CaseSeed]:
    cases: Dict[str, CaseSeed] = {}
    for obj in read_jsonl(path):
        case_id = (
            obj.get("case_id")
            or obj.get("案例ID")
            or obj.get("caseId")
            or obj.get("id")
        )
        if not case_id:
            continue
        case_id = str(case_id).strip()
        raw_text = _as_text_list(obj.get("text") or obj.get("raw_text") or obj.get("内容"))
        title = str(
            obj.get("title")
            or obj.get("case_name")
            or obj.get("问题标题")
            or obj.get("标题")
            or ""
        ).strip()
        phenomenon = _join_text(
            obj.get("phenomenon")
            or obj.get("problem_phenomenon")
            or obj.get("问题现象")
            or obj.get("现象")
        )
        solution = _join_text(
            obj.get("solution")
            or obj.get("解决方案")
            or obj.get("answer")
            or obj.get("答案")
        )

        if not phenomenon and raw_text:
            phenomenon = "\n".join(raw_text[:3])
        if not solution and len(raw_text) > 3:
            solution = "\n".join(raw_text[3:])

        cases[case_id] = CaseSeed(
            case_id=case_id,
            title=title,
            phenomenon=phenomenon,
            solution=solution,
            raw_text=raw_text,
            metadata={
                key: value
                for key, value in obj.items()
                if key
                not in {
                    "case_id",
                    "案例ID",
                    "caseId",
                    "id",
                    "title",
                    "case_name",
                    "问题标题",
                    "标题",
                    "phenomenon",
                    "problem_phenomenon",
                    "问题现象",
                    "现象",
                    "solution",
                    "解决方案",
                    "answer",
                    "答案",
                    "text",
                    "raw_text",
                    "内容",
                }
            },
        )
    return cases


def attach_cases(
    dialogues: List[NormalizedDialogue],
    cases_by_id: Dict[str, CaseSeed],
) -> List[CaseGroundedDialogue]:
    grounded: List[CaseGroundedDialogue] = []
    for dialogue in dialogues:
        case_id: Optional[str] = dialogue.resolution.case_id
        if not case_id:
            continue
        case = cases_by_id.get(case_id)
        if case is None:
            continue
        grounded.append(CaseGroundedDialogue(case=case, dialogue=dialogue))
    return grounded
