from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.llm.llm_client import LLMClient
from src.roadmap.prompt_templates import RELATION_BUILDING_SYSTEM, RELATION_BUILDING_USER
from src.schemas import Point, Relation, model_to_dict
from src.utils.json_utils import dumps_json
from src.utils.logging import OutputLogger


class RelationsOutput(BaseModel):
    relations: List[Relation]


class RelationBuilder:
    def __init__(self, llm_client: LLMClient, logger: OutputLogger | None = None):
        self.llm_client = llm_client
        self.logger = logger

    def build_relations(self, points: List[Point], case_id: str = "") -> List[Relation]:
        user_prompt = RELATION_BUILDING_USER.format(points_json=dumps_json(model_to_dict(points)))
        payload = self.llm_client.generate_json(RELATION_BUILDING_SYSTEM, user_prompt, schema_name="Relations")
        output = RelationsOutput(**payload)
        if self.logger:
            self.logger.log("relations.jsonl", case_id, "RelationBuilder", {"points": points}, output)
        return output.relations
