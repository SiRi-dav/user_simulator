from __future__ import annotations

from typing import Any, Dict, List

from src.llm.llm_client import LLMClient
from src.runtime.prompt_templates import KNOWLEDGE_DECISION_SYSTEM, KNOWLEDGE_DECISION_USER
from src.schemas import AssistantAct, DialogueState, KnowledgeDecision, Roadmap, model_to_dict
from src.utils.json_utils import dumps_json


class KnowledgeModule:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def decide(
        self,
        assistant_text: str,
        assistant_act: AssistantAct,
        roadmap: Roadmap,
        state: DialogueState,
        persona: Dict[str, Any],
        behavior_taxonomy: List[Dict[str, Any]],
        dialogue_history: List[Dict[str, str]],
    ) -> KnowledgeDecision:
        user_prompt = KNOWLEDGE_DECISION_USER.format(
            assistant_text=assistant_text,
            assistant_act_json=dumps_json(model_to_dict(assistant_act)),
            roadmap_json=dumps_json(model_to_dict(roadmap)),
            state_json=dumps_json(model_to_dict(state)),
            persona_json=dumps_json(persona),
            behavior_taxonomy_json=dumps_json(model_to_dict(behavior_taxonomy)),
            dialogue_history_json=dumps_json(dialogue_history),
        )
        payload = self.llm_client.generate_json(KNOWLEDGE_DECISION_SYSTEM, user_prompt, schema_name="KnowledgeDecision")
        return KnowledgeDecision(**payload)
