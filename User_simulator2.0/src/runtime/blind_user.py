from __future__ import annotations

from typing import Any, Dict, List

from src.llm.llm_client import LLMClient
from src.runtime.prompt_templates import (
    ASSISTANT_ACT_SYSTEM,
    ASSISTANT_ACT_USER,
    BLIND_USER_REPLY_SYSTEM,
    BLIND_USER_REPLY_USER,
    INITIAL_USER_SYSTEM,
    INITIAL_USER_USER,
)
from src.schemas import AssistantAct, BlindUserInstruction, model_to_dict
from src.utils.json_utils import dumps_json


class BlindUser:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def initial_reply(self, surface_problem: str, opening_intent: str, persona: Dict[str, Any]) -> str:
        user_prompt = INITIAL_USER_USER.format(
            surface_problem=surface_problem,
            opening_intent=opening_intent,
            persona_json=dumps_json(persona),
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

    def render_reply(
        self,
        instruction: BlindUserInstruction,
        persona: Dict[str, Any],
        surface_problem: str,
        dialogue_history: List[Dict[str, str]],
    ) -> str:
        user_prompt = BLIND_USER_REPLY_USER.format(
            surface_problem=surface_problem,
            persona_json=dumps_json(persona),
            instruction_json=dumps_json(model_to_dict(instruction)),
            dialogue_history_json=dumps_json(dialogue_history),
        )
        payload = self.llm_client.generate_json(BLIND_USER_REPLY_SYSTEM, user_prompt, schema_name="BlindUserReply")
        return str(payload["reply"])
