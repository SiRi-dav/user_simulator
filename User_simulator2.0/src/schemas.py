from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Case(BaseModel):
    case_id: str
    title: str
    phenomenon: str
    solution: str


class RetrievalQuery(BaseModel):
    query_type: str
    query: str
    reason: str


class RelatedCaseSelection(BaseModel):
    case_id: str
    relation_type: str
    reason: str


class KnowledgeSpace(BaseModel):
    target_case: Case
    related_cases: List[Case]
    retrieval_queries: List[RetrievalQuery]


class Point(BaseModel):
    point_id: str
    source_case_id: str
    content: str
    source_field: str
    source_quote: str
    point_type: str
    grounding_type: str
    trigger: List[str]
    visibility: str
    leakage_risk: str
    reason: str


class PointVerificationResult(BaseModel):
    verified_points: List[Point]
    dropped_points: List[Point]
    warnings: List[str]


class Relation(BaseModel):
    from_point_id: str
    to_point_id: str
    relation_type: str
    reason: str


class Roadmap(BaseModel):
    target_case_id: str
    surface_problem: str
    opening_intent: str
    user_facing_points: List[Point]
    diagnostic_points: List[Point]
    solution_points: List[Point]
    external_points: List[Point]
    relations: List[Relation]
    target_route: List[str]
    external_routes: List[List[str]]
    forbidden_content: List[str]


class DialogueState(BaseModel):
    turn_count: int = 0
    exposed_point_ids: List[str] = Field(default_factory=list)
    rejected_external_point_ids: List[str] = Field(default_factory=list)
    action_request_count: int = 0
    how_to_check_count: int = 0
    max_how_to_check: int = 1
    solution_status: str = "not_solved"
    should_stop: bool = False
    stop_reason: Optional[str] = None


class AssistantAct(BaseModel):
    assistant_act: str
    request_summary: str
    confidence: float
    reason: str


class BlindUserInstruction(BaseModel):
    user_intent: str
    allowed_content: str
    forbidden_content: List[str]
    tone: str
    should_stop: bool = False


class KnowledgeDecision(BaseModel):
    assistant_act: str
    matched_scope: str
    matched_point_id: Optional[str]
    decision: str
    instruction: BlindUserInstruction
    state_update: Dict[str, Any]
    reason: str


class SimulationTurnLog(BaseModel):
    turn: int
    assistant_text: str
    assistant_act: AssistantAct
    knowledge_decision: KnowledgeDecision
    user_reply: str
    state: DialogueState


def model_to_dict(value: Any) -> Any:
    if isinstance(value, BaseModel):
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value.dict()
    if isinstance(value, list):
        return [model_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: model_to_dict(item) for key, item in value.items()}
    return value
