from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .schemas import RevealSchedule, UserGoalSeed, UserPersona


def seed_from_knowledge_roadmap(record: Dict[str, Any], persona: UserPersona | None = None) -> UserGoalSeed:
    """Convert a User Simulator 2.0 knowledge roadmap record into a v1 UserGoalSeed."""

    roadmap = record.get("roadmap") or {}
    case_id = str(record.get("case_id") or roadmap.get("target_case_id") or "").strip()
    title = str(record.get("title") or _nested_get(record, "target_case", "title") or "").strip()
    surface_problem = str(roadmap.get("surface_problem") or "").strip()
    opening_intent = str(roadmap.get("opening_intent") or "").strip()

    opening_facts = _dedupe(
        [surface_problem]
        + [
            point["content"]
            for point in _points(roadmap, "user_facing_points")
            if str(point.get("visibility") or "") == "opening_available"
        ]
    )
    followup_facts = _dedupe(
        point["content"]
        for point in _points(roadmap, "user_facing_points")
        if str(point.get("visibility") or "") != "opening_available"
    )
    diagnostic_facts = _dedupe(point["content"] for point in _points(roadmap, "diagnostic_points"))

    return UserGoalSeed(
        dialogue_id=f"roadmap_{case_id}",
        target_case_id=case_id or None,
        target_title=title or None,
        user_goal=surface_problem or opening_intent or title,
        known_facts=opening_facts + followup_facts,
        hidden_facts=diagnostic_facts,
        reveal_schedule=RevealSchedule(
            initial=opening_facts or [surface_problem or opening_intent or title],
            on_clarification=followup_facts,
            deep_followup=diagnostic_facts,
        ),
        persona=persona or UserPersona(),
        metadata={
            "source": "knowledge_roadmap",
            "opening_intent": opening_intent,
            "target_route": roadmap.get("target_route") or [],
        },
    )


def persona_from_name(name: str) -> UserPersona:
    if name == "low_tech":
        return UserPersona(tech_level="low", patience="medium", cooperation="medium", style="concise", emotion="neutral")
    if name == "cooperative":
        return UserPersona(tech_level="medium", patience="high", cooperation="high", style="concise", emotion="neutral")
    if name == "impatient":
        return UserPersona(tech_level="medium", patience="low", cooperation="medium", style="concise", emotion="impatient")
    if name == "vague":
        return UserPersona(tech_level="medium", patience="medium", cooperation="low", style="concise", emotion="neutral")
    return UserPersona()


def _points(roadmap: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    points = roadmap.get(key) or []
    return [point for point in points if isinstance(point, dict) and str(point.get("content") or "").strip()]


def _dedupe(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _nested_get(obj: Dict[str, Any], *keys: str) -> Any:
    current: Any = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
