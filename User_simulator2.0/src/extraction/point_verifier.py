from __future__ import annotations

from typing import Any, List

from src.extraction.point_extractor import normalize_point_record
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
        payload = normalize_verification_payload(payload, target_case, related_cases, points)
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


def normalize_verification_payload(
    payload: dict[str, Any],
    target_case: Case,
    related_cases: List[Case],
    original_points: List[Point],
) -> dict[str, Any]:
    point_lookup = {point.point_id: model_to_dict(point) for point in original_points}
    return {
        "verified_points": normalize_verification_points(
            payload.get("verified_points"),
            point_lookup,
            target_case,
            related_cases,
        ),
        "dropped_points": normalize_verification_points(
            payload.get("dropped_points"),
            point_lookup,
            target_case,
            related_cases,
        ),
        "warnings": normalize_warnings(payload.get("warnings")),
    }


def normalize_verification_points(
    raw_points: Any,
    point_lookup: dict[str, dict[str, Any]],
    target_case: Case,
    related_cases: List[Case],
) -> list[dict[str, Any]]:
    if raw_points is None:
        return []
    if not isinstance(raw_points, list):
        raw_points = [raw_points]
    normalized: list[dict[str, Any]] = []
    for index, raw_point in enumerate(raw_points, 1):
        if isinstance(raw_point, str):
            raw_point = {"point_id": raw_point}
        if not isinstance(raw_point, dict):
            continue
        point_id = str(raw_point.get("point_id") or raw_point.get("id") or "").strip()
        if point_id and point_id in point_lookup:
            merged = dict(point_lookup[point_id])
            merged.update({key: value for key, value in raw_point.items() if value is not None and value != ""})
            normalized.append(merged)
            continue
        normalized.append(normalize_point_record(raw_point, index, target_case, related_cases))
    return normalized


def normalize_warnings(raw_warnings: Any) -> list[str]:
    if raw_warnings is None:
        return []
    if not isinstance(raw_warnings, list):
        raw_warnings = [raw_warnings]
    warnings: list[str] = []
    for warning in raw_warnings:
        if warning is None or warning == "":
            continue
        if isinstance(warning, str):
            warnings.append(warning)
        elif isinstance(warning, dict):
            warnings.append(dumps_json(warning))
        else:
            warnings.append(str(warning))
    return warnings
