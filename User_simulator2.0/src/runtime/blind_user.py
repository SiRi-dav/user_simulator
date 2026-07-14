from __future__ import annotations

from typing import Any, Dict, List

from src.llm.llm_client import LLMClient
from src.runtime.prompt_templates import (
    ASSISTANT_ACT_SYSTEM,
    ASSISTANT_ACT_USER,
    BLIND_USER_ACTION_SYSTEM,
    BLIND_USER_ACTION_USER,
    INITIAL_USER_SYSTEM,
    INITIAL_USER_USER,
)
from src.schemas import AssistantAct, BlindUserAction, DialogueState, KnowledgeAssessment, model_to_dict
from src.utils.json_utils import dumps_json


class BlindUser:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def initial_reply(
        self,
        surface_problem: str,
        opening_intent: str,
        persona: Dict[str, Any],
        employee_persona: Dict[str, Any] | None = None,
    ) -> str:
        user_prompt = INITIAL_USER_USER.format(
            surface_problem=surface_problem,
            opening_intent=opening_intent,
            persona_json=dumps_json(persona),
            employee_persona_json=dumps_json(employee_persona or {}),
        )
        payload = self.llm_client.generate_json(INITIAL_USER_SYSTEM, user_prompt, schema_name="InitialUserReply")
        return str(payload["reply"])

    def parse_assistant_act(self, assistant_text: str, dialogue_history: List[Dict[str, str]]) -> AssistantAct:
        user_prompt = ASSISTANT_ACT_USER.format(
            dialogue_history_json=dumps_json(dialogue_history),
            assistant_text=assistant_text,
        )
        payload = self.llm_client.generate_json(ASSISTANT_ACT_SYSTEM, user_prompt, schema_name="AssistantAct")
        return AssistantAct(**payload)

    def choose_action_and_reply(
        self,
        assessment: KnowledgeAssessment,
        persona: Dict[str, Any],
        employee_persona: Dict[str, Any] | None,
        behavior_policy: List[Dict[str, Any]],
        surface_problem: str,
        dialogue_history: List[Dict[str, str]],
        state: DialogueState | None = None,
    ) -> BlindUserAction:
        assessment_json = model_to_dict(assessment)
        user_prompt = BLIND_USER_ACTION_USER.format(
            surface_problem=surface_problem,
            persona_json=dumps_json(persona),
            employee_persona_json=dumps_json(employee_persona or {}),
            behavior_policy_json=dumps_json(model_to_dict(behavior_policy)),
            knowledge_assessment_json=dumps_json(assessment_json),
            action_execution_feedback_json=dumps_json(build_action_execution_feedback(state)),
            state_json=dumps_json(model_to_dict(state) if state else {}),
            dialogue_history_json=dumps_json(dialogue_history),
        )
        payload = self.llm_client.generate_json(
            BLIND_USER_ACTION_SYSTEM,
            user_prompt,
            schema_name="BlindUserAction",
        )
        return BlindUserAction(**payload)


def build_action_execution_feedback(state: DialogueState | None) -> Dict[str, Any]:
    if not state or not state.pending_action_result:
        return {"has_pending_result": False}
    return {
        "has_pending_result": True,
        "executed_action": state.last_action_summary,
        "action_solution_match": state.pending_action_solution_match,
        "observations": list(state.pending_action_result_facts),
        "usage_policy": (
            "This is world-model feedback produced after the user executed the previous assistant-requested action. "
            "Consider it before ordinary new facts, then combine it with the latest assistant reply and the behavior policy."
        ),
    }
