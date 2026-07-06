from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.extraction.prompt_templates import POINT_EXTRACTION_SYSTEM, POINT_EXTRACTION_USER
from src.llm.llm_client import LLMClient
from src.schemas import Case, Point, model_to_dict
from src.utils.json_utils import dumps_json
from src.utils.logging import OutputLogger


class PointsOutput(BaseModel):
    points: List[Point]


class PointExtractor:
    def __init__(self, llm_client: LLMClient, logger: OutputLogger | None = None):
        self.llm_client = llm_client
        self.logger = logger

    def extract_points(self, target_case: Case, related_cases: List[Case]) -> List[Point]:
        user_prompt = POINT_EXTRACTION_USER.format(
            target_case_json=dumps_json(model_to_dict(target_case)),
            related_cases_json=dumps_json(model_to_dict(related_cases)),
        )
        payload = self.llm_client.generate_json(POINT_EXTRACTION_SYSTEM, user_prompt, schema_name="Points")
        output = PointsOutput(**payload)
        if self.logger:
            self.logger.log(
                "points.jsonl",
                target_case.case_id,
                "PointExtractor",
                {"target_case": target_case, "related_cases": related_cases},
                output,
            )
        return output.points
