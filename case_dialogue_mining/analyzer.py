from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from local_ai_client import LocalAIClient
from prompt_templates import build_case_question_pattern_prompt
from schemas import CaseDialoguePair, CaseQuestionPattern


def analyze_pairs(
    pairs: List[CaseDialoguePair],
    client: LocalAIClient,
    analysis_config: Dict[str, Any],
) -> Tuple[List[CaseQuestionPattern], List[Dict[str, Any]]]:
    patterns: List[CaseQuestionPattern] = []
    errors: List[Dict[str, Any]] = []
    for pair in pairs:
        prompt = build_case_question_pattern_prompt(
            pair=pair,
            max_dialogues=int(analysis_config.get("max_dialogues_per_case", 5)),
            max_turns_per_dialogue=int(analysis_config.get("max_turns_per_dialogue", 12)),
            max_chars_per_dialogue=int(analysis_config.get("max_chars_per_dialogue", 3000)),
        )
        try:
            raw_response = client.generate(prompt)
            pattern = parse_pattern(pair.case.case_id, raw_response)
            patterns.append(pattern)
            if pattern.parse_error:
                errors.append(
                    {
                        "case_id": pair.case.case_id,
                        "error": pattern.parse_error,
                        "raw_ai_response": raw_response,
                    }
                )
        except Exception as exc:
            errors.append({"case_id": pair.case.case_id, "error": str(exc)})
            patterns.append(CaseQuestionPattern(case_id=pair.case.case_id, parse_error=str(exc)))
    return patterns, errors


def parse_pattern(case_id: str, raw_response: str) -> CaseQuestionPattern:
    try:
        obj = json.loads(extract_json_object(raw_response))
        return CaseQuestionPattern(
            case_id=str(obj.get("case_id") or case_id),
            surface_problem_patterns=_as_str_list(obj.get("surface_problem_patterns")),
            initial_question_patterns=_as_str_list(obj.get("initial_question_patterns")),
            known_facts=_as_str_list(obj.get("known_facts")),
            hidden_facts=_as_str_list(obj.get("hidden_facts")),
            reveal_patterns=_as_str_list(obj.get("reveal_patterns")),
            user_style_summary=str(obj.get("user_style_summary") or ""),
            common_missing_slots=_as_str_list(obj.get("common_missing_slots")),
            difficulty_observations=_as_str_list(obj.get("difficulty_observations")),
            simulation_suggestions=_as_str_list(obj.get("simulation_suggestions")),
            observed_from_dialogue=_as_str_list(obj.get("observed_from_dialogue")),
            inferred_from_case=_as_str_list(obj.get("inferred_from_case")),
            uncertain_points=_as_str_list(obj.get("uncertain_points")),
            case_to_question_summary=str(obj.get("case_to_question_summary") or ""),
            opening_question_templates=_as_str_list(obj.get("opening_question_templates")),
            slot_reveal_plan=_as_dict_list(obj.get("slot_reveal_plan")),
            simulator_actions=_as_dict_list(obj.get("simulator_actions")),
            evaluation_focus=_as_str_list(obj.get("evaluation_focus")),
            raw_ai_response=raw_response,
        )
    except Exception as exc:
        return CaseQuestionPattern(case_id=case_id, raw_ai_response=raw_response, parse_error=str(exc))


def extract_json_object(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        return text[start : end + 1]
    return text


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_dict_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            items.append({str(key): val for key, val in item.items()})
    return items
