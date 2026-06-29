from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class Role(str, Enum):
    USER = "user"
    AGENT = "agent"


class FailureType(str, Enum):
    SUCCESS = "success"
    RETRIEVAL_FAIL = "retrieval_fail"
    SELECTION_FAIL = "selection_fail"
    CLARIFICATION_FAIL = "clarification_fail"
    OVER_CLARIFICATION = "over_clarification"
    ANSWER_FAIL = "answer_fail"
    USER_GAVE_UP = "user_gave_up"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class DialogueTurn:
    role: str
    text: str
    turn_index: Optional[int] = None
    label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Resolution:
    case_id: Optional[str] = None
    title: Optional[str] = None
    success: Optional[bool] = None


@dataclass
class NormalizedDialogue:
    dialogue_id: str
    turns: List[DialogueTurn]
    resolution: Resolution = field(default_factory=Resolution)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseSeed:
    case_id: str
    title: str = ""
    phenomenon: str = ""
    solution: str = ""
    raw_text: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseGroundedDialogue:
    case: CaseSeed
    dialogue: NormalizedDialogue


@dataclass
class UserPersona:
    tech_level: str = "medium"
    patience: str = "medium"
    cooperation: str = "medium"
    style: str = "concise"
    emotion: str = "neutral"


@dataclass
class RevealSchedule:
    initial: List[str] = field(default_factory=list)
    on_clarification: List[str] = field(default_factory=list)
    deep_followup: List[str] = field(default_factory=list)


@dataclass
class UserGoalSeed:
    dialogue_id: str
    target_case_id: Optional[str]
    target_title: Optional[str]
    user_goal: str
    known_facts: List[str]
    hidden_facts: List[str]
    reveal_schedule: RevealSchedule
    persona: UserPersona
    noise: List[str] = field(default_factory=list)
    source_turns: List[DialogueTurn] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DifficultyConfig:
    info_density: int = 3
    precision: int = 3
    noise: int = 2
    cooperation: int = 2
    consistency: int = 1
    emotion: int = 2

    @classmethod
    def easy(cls) -> "DifficultyConfig":
        return cls(info_density=1, precision=1, noise=1, cooperation=1, consistency=1, emotion=1)

    @classmethod
    def medium(cls) -> "DifficultyConfig":
        return cls()

    @classmethod
    def hard(cls) -> "DifficultyConfig":
        return cls(info_density=4, precision=4, noise=4, cooperation=4, consistency=3, emotion=4)


@dataclass
class UserState:
    turn_id: int = 0
    revealed_facts: List[str] = field(default_factory=list)
    pending_initial: List[str] = field(default_factory=list)
    pending_clarification: List[str] = field(default_factory=list)
    pending_deep: List[str] = field(default_factory=list)
    patience: int = 6
    repeated_clarifications: int = 0
    should_end: bool = False
    end_reason: Optional[str] = None


@dataclass
class UserStep:
    turn_id: int
    utterance: str
    should_end: bool
    end_reason: Optional[str]
    state: UserState


@dataclass
class AgentStep:
    response: str
    recommended_case_id: Optional[str] = None
    action: str = "respond"
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulationResult:
    dialogue_id: str
    target_case_id: Optional[str]
    difficulty: DifficultyConfig
    turns: List[Dict[str, Any]]
    metrics: Dict[str, Any]


def to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {k: to_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [to_dict(v) for v in value]
    if isinstance(value, dict):
        return {k: to_dict(v) for k, v in value.items()}
    if isinstance(value, Enum):
        return value.value
    return value
