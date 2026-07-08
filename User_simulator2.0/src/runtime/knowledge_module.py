from __future__ import annotations

from typing import Any, Dict, List

from src.llm.llm_client import LLMClient
from src.runtime.prompt_templates import KNOWLEDGE_ASSESSMENT_SYSTEM, KNOWLEDGE_ASSESSMENT_USER
from src.schemas import AssistantAct, DialogueState, KnowledgeAssessment, RuntimeRoadmap, model_to_dict
from src.utils.json_utils import dumps_json


class KnowledgeModule:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def assess(
        self,
        assistant_text: str,
        assistant_act: AssistantAct,
        roadmap: RuntimeRoadmap,
        state: DialogueState,
        dialogue_history: List[Dict[str, str]],
    ) -> KnowledgeAssessment:
        user_prompt = KNOWLEDGE_ASSESSMENT_USER.format(
            assistant_text=assistant_text,
            assistant_act_json=dumps_json(model_to_dict(assistant_act)),
            roadmap_json=dumps_json(model_to_dict(roadmap)),
            state_json=dumps_json(model_to_dict(state)),
            dialogue_history_json=dumps_json(dialogue_history),
        )
        payload = self.llm_client.generate_json(
            KNOWLEDGE_ASSESSMENT_SYSTEM,
            user_prompt,
            schema_name="KnowledgeAssessment",
        )
        return KnowledgeAssessment(**payload)
