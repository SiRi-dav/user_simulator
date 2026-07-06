from __future__ import annotations

from typing import List

from src.llm.llm_client import LLMClient
from src.roadmap.prompt_templates import ROADMAP_BUILDING_SYSTEM, ROADMAP_BUILDING_USER
from src.schemas import Case, Point, Relation, Roadmap, model_to_dict
from src.utils.json_utils import dumps_json
from src.utils.logging import OutputLogger


class RoadmapBuilder:
    def __init__(self, llm_client: LLMClient, logger: OutputLogger | None = None):
        self.llm_client = llm_client
        self.logger = logger

    def build_roadmap(self, target_case: Case, points: List[Point], relations: List[Relation]) -> Roadmap:
        user_prompt = ROADMAP_BUILDING_USER.format(
            target_case_json=dumps_json(model_to_dict(target_case)),
            points_json=dumps_json(model_to_dict(points)),
            relations_json=dumps_json(model_to_dict(relations)),
        )
        payload = self.llm_client.generate_json(ROADMAP_BUILDING_SYSTEM, user_prompt, schema_name="Roadmap")
        output = Roadmap(**payload)
        if self.logger:
            self.logger.log(
                "roadmaps.jsonl",
                target_case.case_id,
                "RoadmapBuilder",
                {"target_case": target_case, "points": points, "relations": relations},
                output,
            )
        return output
