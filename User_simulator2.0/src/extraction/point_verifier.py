from __future__ import annotations

from typing import List

from src.extraction.prompt_templates import POINT_VERIFICATION_SYSTEM, POINT_VERIFICATION_USER
from src.llm.llm_client import LLMClient
from src.schemas import Case, Point, PointVerificationResult, model_to_dict
from src.utils.json_utils import dumps_json
from src.utils.logging import OutputLogger


class PointVerifier:
    def __init__(self, llm_client: LLMClient, logger: OutputLogger | None = None):
        self.llm_client = llm_client
        self.logger = logger

    def verify_points(self, target_case: Case, related_cases: List[Case], points: List[Point]) -> PointVerificationResult:
        user_prompt = POINT_VERIFICATION_USER.format(
            target_case_json=dumps_json(model_to_dict(target_case)),
            related_cases_json=dumps_json(model_to_dict(related_cases)),
            points_json=dumps_json(model_to_dict(points)),
        )
        payload = self.llm_client.generate_json(
            POINT_VERIFICATION_SYSTEM,
            user_prompt,
            schema_name="PointVerificationResult",
        )
        output = PointVerificationResult(**payload)
        if self.logger:
            self.logger.log(
                "verified_points.jsonl",
                target_case.case_id,
                "PointVerifier",
                {"target_case": target_case, "related_cases": related_cases, "points": points},
                output,
            )
        return output
