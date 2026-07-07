from __future__ import annotations

from typing import Any, List

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
        payload = normalize_points_payload(payload, target_case, related_cases)
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


def normalize_points_payload(payload: dict[str, Any], target_case: Case, related_cases: List[Case]) -> dict[str, Any]:
    points = payload.get("points") or []
    if not isinstance(points, list):
        return {"points": []}
    normalized_points = [
        normalize_point_record(point, index, target_case, related_cases)
        for index, point in enumerate(points, 1)
        if isinstance(point, dict)
    ]
    return {"points": normalized_points}


def normalize_point_record(
    point: dict[str, Any],
    index: int,
    target_case: Case,
    related_cases: List[Case],
) -> dict[str, Any]:
    normalized = dict(point)
    point_id = str(normalized.get("point_id") or normalized.get("id") or f"P_AUTO_{index}").strip()
    content = first_non_empty(
        normalized.get("content"),
        normalized.get("text"),
        normalized.get("point"),
        normalized.get("description"),
        normalized.get("source_quote"),
    )
    point_type = infer_point_type(normalized, point_id)
    related_case_id = related_cases[0].case_id if related_cases else target_case.case_id

    normalized["point_id"] = point_id
    normalized["content"] = content
    normalized["point_type"] = point_type
    normalized["source_case_id"] = first_non_empty(
        normalized.get("source_case_id"),
        normalized.get("case_id"),
        related_case_id if point_type == "external" else target_case.case_id,
    )
    normalized["source_field"] = first_non_empty(normalized.get("source_field"), "text")
    normalized["source_quote"] = first_non_empty(normalized.get("source_quote"), content)
    normalized["grounding_type"] = first_non_empty(normalized.get("grounding_type"), "explicit")
    normalized["trigger"] = normalize_trigger(normalized.get("trigger"))
    normalized["visibility"] = first_non_empty(normalized.get("visibility"), default_visibility(point_type))
    normalized["leakage_risk"] = first_non_empty(normalized.get("leakage_risk"), default_leakage_risk(point_type))
    normalized["reason"] = first_non_empty(normalized.get("reason"), "Filled default metadata for LLM point output.")
    return normalized


def infer_point_type(point: dict[str, Any], point_id: str) -> str:
    raw_type = str(point.get("point_type") or "").strip()
    if raw_type in {"user_facing", "diagnostic", "solution", "external"}:
        return raw_type
    visibility = str(point.get("visibility") or "").strip().lower()
    point_id_lower = point_id.lower()
    if visibility in {"opening_available", "user_facing", "visible"} or point_id_lower.startswith("user"):
        return "user_facing"
    if visibility in {"hidden", "ask_triggered"} or point_id_lower.startswith("diag"):
        return "diagnostic"
    if visibility in {"judge_only", "solution_only"} or point_id_lower.startswith("sol"):
        return "solution"
    if visibility in {"external_only", "external"} or point_id_lower.startswith("ext"):
        return "external"
    return "diagnostic"


def default_visibility(point_type: str) -> str:
    if point_type == "user_facing":
        return "opening_available"
    if point_type == "solution":
        return "judge_only"
    if point_type == "external":
        return "external_only"
    return "ask_triggered"


def default_leakage_risk(point_type: str) -> str:
    if point_type == "solution":
        return "high"
    if point_type == "external":
        return "medium"
    return "low"


def normalize_trigger(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            text = "\n".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value).strip()
        if text:
            return text
    return ""
