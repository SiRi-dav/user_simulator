from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.behavior_mining.prompt_templates import BEHAVIOR_TAXONOMY_SYSTEM, BEHAVIOR_TAXONOMY_USER
from src.llm.llm_client import LLMClient
from src.schemas import BehaviorTaxonomy, DialogueBehaviorSummary, model_to_dict
from src.utils.json_utils import dumps_json


class BehaviorTaxonomyOutput(BaseModel):
    behavior_taxonomy: List[BehaviorTaxonomy]


class BehaviorTaxonomyMiner:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def mine_taxonomy(self, summaries: List[DialogueBehaviorSummary]) -> List[BehaviorTaxonomy]:
        user_prompt = BEHAVIOR_TAXONOMY_USER.format(dialogues_json=dumps_json(model_to_dict(summaries)))
        payload = self.llm_client.generate_json(
            BEHAVIOR_TAXONOMY_SYSTEM,
            user_prompt,
            schema_name="BehaviorTaxonomy",
        )
        return BehaviorTaxonomyOutput(**payload).behavior_taxonomy
