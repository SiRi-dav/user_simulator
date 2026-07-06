from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.behavior_mining.prompt_templates import PERSONA_MINING_SYSTEM, PERSONA_MINING_USER
from src.llm.llm_client import LLMClient
from src.schemas import DialogueBehaviorSummary, EmployeePersona, model_to_dict
from src.utils.json_utils import dumps_json


class PersonasOutput(BaseModel):
    personas: List[EmployeePersona]


class PersonaMiner:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def mine_personas(self, summaries: List[DialogueBehaviorSummary]) -> List[EmployeePersona]:
        user_prompt = PERSONA_MINING_USER.format(dialogues_json=dumps_json(model_to_dict(summaries)))
        payload = self.llm_client.generate_json(PERSONA_MINING_SYSTEM, user_prompt, schema_name="EmployeePersonas")
        return PersonasOutput(**payload).personas
