from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CaseRecord:
    case_id: str
    title: str
    phenomenon: Optional[str] = None
    solution: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DialogueTurn:
    role: str
    text: str


@dataclass
class DialogueRecord:
    dialogue_id: str
    case_id: Optional[str]
    turns: List[DialogueTurn]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseDialoguePair:
    case: CaseRecord
    dialogues: List[DialogueRecord]


@dataclass
class MiningStats:
    total_cases: int = 0
    total_dialogues: int = 0
    matched_cases: int = 0
    matched_dialogues: int = 0
    unmatched_cases: int = 0
    missing_case_id_dialogues: int = 0
    unknown_case_id_dialogues: int = 0


@dataclass
class CaseQuestionPattern:
    case_id: str
    surface_problem_patterns: List[str] = field(default_factory=list)
    initial_question_patterns: List[str] = field(default_factory=list)
    known_facts: List[str] = field(default_factory=list)
    hidden_facts: List[str] = field(default_factory=list)
    reveal_patterns: List[str] = field(default_factory=list)
    user_style_summary: str = ""
    common_missing_slots: List[str] = field(default_factory=list)
    difficulty_observations: List[str] = field(default_factory=list)
    simulation_suggestions: List[str] = field(default_factory=list)
    raw_ai_response: str = ""
    parse_error: Optional[str] = None


def to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_dict(val) for key, val in asdict(value).items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(val) for key, val in value.items()}
    return value

