from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

from .schemas import DialogueTurn, NormalizedDialogue, Resolution


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

