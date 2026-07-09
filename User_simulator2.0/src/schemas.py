from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Case(BaseModel):
    case_id: str
    title: str
    phenomenon: str
    solution: str


class DialogueTurn(BaseModel):
    speaker: str
    text: str


class HistoricalDialogue(BaseModel):
    dialogue_id: str
    case_id: Optional[str] = None
    final_case_id: Optional[str] = None
    resolved: Optional[bool] = None
    turns: List[DialogueTurn]


class RetrievalQuery(BaseModel):
    query_type: str
    query: str
    reason: str


class RelatedCaseSelection(BaseModel):
    case_id: str
    relation_type: str
    reason: str
    surface_score: float = 0.0
    diagnostic_score: float = 0.0
    solution_score: float = 0.0
    confusion_score: float = 0.0
    overall_score: float = 0.0


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


class RuntimePoint(BaseModel):
    point_id: str
    content: str
    point_type: str
    trigger: List[str] = Field(default_factory=list)
    visibility: str


class RuntimeRelation(BaseModel):
    from_point_id: str
    to_point_id: str
    relation_type: str


class RuntimeRoadmap(BaseModel):
    target_case_id: str
    surface_problem: str
    opening_intent: str
    user_facing_points: List[RuntimePoint]
    diagnostic_points: List[RuntimePoint]
    solution_points: List[RuntimePoint]
    external_points: List[RuntimePoint]
    relations: List[RuntimeRelation]
    target_route: List[str]
    external_routes: List[List[str]]
    forbidden_content: List[str]


class BlindUserCaseView(BaseModel):
    case_id: str
    surface_problem: str
    opening_intent: str
    user_facing_points: List[Point]


class BlindUserRuntimeView(BaseModel):
    case_id: str
    surface_problem: str
    opening_intent: str
    user_visible_facts: List[str] = Field(default_factory=list)


class KnowledgeRoadmapArtifact(BaseModel):
    case_id: str
    title: str = ""
    roadmap: RuntimeRoadmap


class CaseAnalysisDebugArtifact(BaseModel):
    case_id: str
    target_case: Case
    retrieval_queries: List[RetrievalQuery]
    related_cases: List[Case]
    verified_points: List[Point]
    dropped_points: List[Point]
    warnings: List[str]
    relations: List[Relation]
    roadmap: Roadmap


class DialogueState(BaseModel):
    turn_count: int = 0
    exposed_point_ids: List[str] = Field(default_factory=list)
    rejected_external_point_ids: List[str] = Field(default_factory=list)
    action_request_count: int = 0
    how_to_check_count: int = 0
    max_how_to_check: int = 1
    pending_action_result: bool = False
    last_action_summary: Optional[str] = None
    pending_action_solution_match: Optional[str] = None
    pending_action_result_facts: List[str] = Field(default_factory=list)
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


class KnowledgeAssessment(BaseModel):
    assistant_act: str
    matched_scope: str
    matched_point_ids: List[str] = Field(default_factory=list)
    allowed_facts: List[str] = Field(default_factory=list)
    unknown_requested_facts: List[str] = Field(default_factory=list)
    forbidden_content: List[str] = Field(default_factory=list)
    solution_match: str = "none"
    progress_status: str = "new_progress"
    no_more_user_info: bool = False
    state_update: Dict[str, Any] = Field(default_factory=dict)
    reason: str


class BlindUserAction(BaseModel):
    user_action: str
    reply: str
    state_update: Dict[str, Any] = Field(default_factory=dict)
    reason: str


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
    knowledge_assessment: KnowledgeAssessment
    user_action: BlindUserAction
    user_reply: str
    state: DialogueState


class EmployeePersona(BaseModel):
    persona_id: str
    persona_name: str
    description: str
    technical_literacy: str
    patience_level: str
    clarity_level: str
    cooperation_level: str
    typical_opening_style: List[str]
    information_release_style: str
    action_request_behavior: str
    offtrack_reaction_style: str
    solution_acceptance_style: str
    evidence_dialogue_ids: List[str]
    reason: str


class UserBehaviorEvent(BaseModel):
    dialogue_id: str
    turn_index: int
    assistant_act: str
    user_behavior: str
    user_text: str
    assistant_text: str
    released_information_type: Optional[str]
    behavior_reason: str

    @field_validator("assistant_act", "user_behavior", "user_text", "assistant_text", "behavior_reason", mode="before")
    @classmethod
    def none_to_empty_string(cls, value: Any) -> Any:
        if value is None:
            return ""
        return value


class BehaviorTaxonomy(BaseModel):
    behavior_name: str
    definition: str
    trigger_assistant_acts: List[str]
    typical_user_response_patterns: List[str]
    persona_sensitivity: Dict[str, str]
    simulator_policy_hint: str
    decision_rules: List[str] = Field(default_factory=list)
    prohibited_behaviors: List[str] = Field(default_factory=list)
    state_transitions: Dict[str, str] = Field(default_factory=dict)


class DialogueBehaviorSummary(BaseModel):
    dialogue_id: str
    opening_pattern: str
    user_persona_guess: str
    observed_behaviors: List[UserBehaviorEvent]
    voluntary_information: List[str]
    ask_triggered_information: List[str]
    action_request_reactions: List[str]
    offtrack_reactions: List[str]
    solution_reactions: List[str]
    summary: str


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
