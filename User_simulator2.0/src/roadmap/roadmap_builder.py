from __future__ import annotations

from typing import Any, List

from src.llm.llm_client import LLMClient
from src.roadmap.prompt_templates import ROADMAP_BUILDING_SYSTEM, ROADMAP_BUILDING_USER
from src.schemas import Case, Point, Relation, Roadmap, model_to_dict
from src.extraction.point_extractor import normalize_point_record
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
        payload = normalize_roadmap_payload(payload, target_case, points, relations)
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


POINT_GROUPS = ("user_facing_points", "diagnostic_points", "solution_points", "external_points")


def normalize_roadmap_payload(
    payload: dict[str, Any],
    target_case: Case,
    points: List[Point],
    relations: List[Relation],
) -> dict[str, Any]:
    normalized = dict(payload or {})
    point_lookup = {point.point_id: model_to_dict(point) for point in points}
    normalized["target_case_id"] = str(normalized.get("target_case_id") or target_case.case_id)
    normalized["surface_problem"] = str(normalized.get("surface_problem") or target_case.title or target_case.phenomenon)
    normalized["opening_intent"] = str(normalized.get("opening_intent") or "希望尽快解决当前问题，恢复正常工作。")
    for group in POINT_GROUPS:
        normalized[group] = normalize_point_group(
            normalized.get(group),
            group,
            point_lookup,
            target_case,
        )
    if not normalized["user_facing_points"]:
        normalized["user_facing_points"] = [model_to_dict(point) for point in points if point.point_type == "user_facing"]
    if not normalized["diagnostic_points"]:
        normalized["diagnostic_points"] = [model_to_dict(point) for point in points if point.point_type == "diagnostic"]
    if not normalized["solution_points"]:
        normalized["solution_points"] = [model_to_dict(point) for point in points if point.point_type == "solution"]
    if not normalized["external_points"]:
        normalized["external_points"] = [model_to_dict(point) for point in points if point.point_type == "external"]
    normalized["relations"] = normalize_relations(normalized.get("relations"), relations)
    normalized["target_route"] = normalize_route(normalized.get("target_route")) or [
        point.point_id for point in points if point.point_type in {"user_facing", "diagnostic", "solution"}
    ]
    normalized["external_routes"] = normalize_routes(normalized.get("external_routes"))
    normalized["forbidden_content"] = normalize_string_list(normalized.get("forbidden_content"))
    return normalized


def normalize_point_group(
    raw_points: Any,
    group: str,
    point_lookup: dict[str, dict[str, Any]],
    target_case: Case,
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
        point_with_type = dict(raw_point)
        point_with_type.setdefault("point_type", point_type_for_group(group))
        normalized.append(normalize_point_record(point_with_type, index, target_case, []))
    return normalized


def point_type_for_group(group: str) -> str:
    return {
        "user_facing_points": "user_facing",
        "diagnostic_points": "diagnostic",
        "solution_points": "solution",
        "external_points": "external",
    }.get(group, "diagnostic")


def normalize_relations(raw_relations: Any, fallback_relations: List[Relation]) -> list[dict[str, Any]]:
    if not isinstance(raw_relations, list):
        return [model_to_dict(relation) for relation in fallback_relations]
    normalized = []
    for relation in raw_relations:
        if not isinstance(relation, dict):
            continue
        if {"from_point_id", "to_point_id", "relation_type", "reason"} <= relation.keys():
            normalized.append(relation)
    if normalized:
        return normalized
    return [model_to_dict(relation) for relation in fallback_relations]


def normalize_route(raw_route: Any) -> list[str]:
    if not isinstance(raw_route, list):
        return []
    return [str(item).strip() for item in raw_route if str(item).strip()]


def normalize_routes(raw_routes: Any) -> list[list[str]]:
    if not isinstance(raw_routes, list):
        return []
    return [route for route in (normalize_route(item) for item in raw_routes) if route]


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []
