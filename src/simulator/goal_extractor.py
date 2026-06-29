from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .llm_client import LLMClient
from .schemas import DialogueTurn, NormalizedDialogue, RevealSchedule, UserGoalSeed, UserPersona


QUESTION_HINTS = ("怎么", "如何", "为什么", "无法", "不能", "失败", "报错", "打不开", "登不上", "不会", "查询")


def _user_turns(dialogue: NormalizedDialogue) -> List[DialogueTurn]:
    return [turn for turn in dialogue.turns if turn.role == "user" and turn.text.strip()]


def _agent_labels(dialogue: NormalizedDialogue) -> List[str]:
    labels = [turn.label for turn in dialogue.turns if turn.role == "agent" and turn.label]
    if labels:
        return labels
    return dialogue.metadata.get("agent_labels", []) or []


def _guess_goal(user_texts: List[str], title: str | None) -> str:
    if title:
        return f"解决或咨询：{title}"
    if not user_texts:
        return "完成一次企业知识问答咨询"
    first = user_texts[0].strip(" ，。！？")
    if any(hint in first for hint in QUESTION_HINTS):
        return first
    return f"解决这个问题：{first}"


def _split_facts(user_texts: List[str]) -> tuple[List[str], List[str]]:
    if not user_texts:
        return ["我有一个问题需要咨询"], []
    known = [user_texts[0]]
    hidden = user_texts[1:]
    return known, hidden


def _guess_persona(user_texts: List[str], labels: List[str]) -> UserPersona:
    merged = " ".join(user_texts)
    avg_len = sum(len(t) for t in user_texts) / max(len(user_texts), 1)
    tech_level = "high" if re.search(r"0x[0-9a-fA-F]+|https?://|VPN|ID|账号|密码|流程|系统", merged) else "medium"
    if any(word in merged for word in ("不懂", "不会", "不知道", "咋", "啥")):
        tech_level = "low"

    style = "verbose" if avg_len >= 35 else "concise"
    patience = "low" if any(word in merged for word in ("急", "赶紧", "怎么还", "算了")) else "medium"
    cooperation = "high" if len(user_texts) >= 3 and any("追问" in label for label in labels) else "medium"
    emotion = "anxious" if any(word in merged for word in ("急", "开会", "影响", "用不了")) else "neutral"
    return UserPersona(
        tech_level=tech_level,
        patience=patience,
        cooperation=cooperation,
        style=style,
        emotion=emotion,
    )


def extract_goal_seed(dialogue: NormalizedDialogue, llm: Optional[LLMClient] = None) -> UserGoalSeed:
    if llm is not None:
        llm_seed = _extract_goal_seed_with_llm(dialogue, llm)
        if llm_seed is not None:
            return llm_seed
    return extract_goal_seed_heuristic(dialogue)


def extract_goal_seed_heuristic(dialogue: NormalizedDialogue) -> UserGoalSeed:
    user_turns = _user_turns(dialogue)
    user_texts = [turn.text for turn in user_turns]
    labels = _agent_labels(dialogue)
    known_facts, hidden_facts = _split_facts(user_texts)

    schedule = RevealSchedule(
        initial=known_facts[:1],
        on_clarification=hidden_facts[:2],
        deep_followup=hidden_facts[2:],
    )
    noise = [
        text
        for text in user_texts
        if any(marker in text for marker in ("开会", "很急", "昨天", "上午", "下午"))
    ]

    return UserGoalSeed(
        dialogue_id=dialogue.dialogue_id,
        target_case_id=dialogue.resolution.case_id,
        target_title=dialogue.resolution.title,
        user_goal=_guess_goal(user_texts, dialogue.resolution.title),
        known_facts=known_facts,
        hidden_facts=hidden_facts,
        reveal_schedule=schedule,
        persona=_guess_persona(user_texts, labels),
        noise=noise,
        source_turns=dialogue.turns,
        metadata={
            "extractor": "heuristic_v1",
            "agent_labels": labels,
        },
    )


def _extract_goal_seed_with_llm(dialogue: NormalizedDialogue, llm: LLMClient) -> Optional[UserGoalSeed]:
    prompt = _build_goal_extraction_prompt(dialogue)
    raw = llm.generate_json(
        [
            {
                "role": "system",
                "content": "你是企业客服对话分析专家，擅长从真实对话中抽取用户目标、画像和信息透露节奏。只输出 JSON。",
            },
            {"role": "user", "content": prompt},
        ]
    )
    if not raw:
        return None
    try:
        return _seed_from_llm_json(dialogue, raw)
    except (TypeError, ValueError, KeyError):
        return None


def _build_goal_extraction_prompt(dialogue: NormalizedDialogue) -> str:
    turns = [
        {
            "role": turn.role,
            "text": turn.text,
            "label": turn.label,
            "turn_index": turn.turn_index,
        }
        for turn in dialogue.turns
    ]
    payload = {
        "dialogue_id": dialogue.dialogue_id,
        "turns": turns,
        "resolution": {
            "case_id": dialogue.resolution.case_id,
            "title": dialogue.resolution.title,
            "success": dialogue.resolution.success,
        },
    }
    return f"""
请从下面企业客服对话中抽取一个可用于“用户模拟器”的用户种子。

要求：
1. user_goal 写成用户真正想解决的问题，不要写客服视角。
2. known_facts 是用户一开始或很自然会主动说的信息。
3. hidden_facts 是用户被追问后才逐步透露的信息。
4. reveal_schedule 必须把信息分成 initial / on_clarification / deep_followup 三层。
5. persona 只能使用给定枚举值。
6. 不要编造对话中没有依据的具体事实。

输出 JSON，schema 如下：
{{
  "user_goal": "str",
  "known_facts": ["str"],
  "hidden_facts": ["str"],
  "reveal_schedule": {{
    "initial": ["str"],
    "on_clarification": ["str"],
    "deep_followup": ["str"]
  }},
  "persona": {{
    "tech_level": "low|medium|high",
    "patience": "low|medium|high",
    "cooperation": "low|medium|high",
    "style": "concise|verbose",
    "emotion": "neutral|anxious|impatient"
  }},
  "noise": ["str"]
}}

对话：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _enum_value(value: Any, allowed: set[str], default: str) -> str:
    value = str(value).strip()
    return value if value in allowed else default


def _seed_from_llm_json(dialogue: NormalizedDialogue, raw: Dict[str, Any]) -> UserGoalSeed:
    reveal_obj = raw.get("reveal_schedule") or {}
    persona_obj = raw.get("persona") or {}
    schedule = RevealSchedule(
        initial=_as_str_list(reveal_obj.get("initial")),
        on_clarification=_as_str_list(reveal_obj.get("on_clarification")),
        deep_followup=_as_str_list(reveal_obj.get("deep_followup")),
    )
    known_facts = _as_str_list(raw.get("known_facts")) or list(schedule.initial)
    hidden_facts = _as_str_list(raw.get("hidden_facts")) or (
        list(schedule.on_clarification) + list(schedule.deep_followup)
    )
    if not schedule.initial:
        schedule.initial = known_facts[:1]
    if not schedule.on_clarification and not schedule.deep_followup:
        schedule.on_clarification = hidden_facts[:2]
        schedule.deep_followup = hidden_facts[2:]

    if not raw.get("user_goal") or not schedule.initial:
        raise ValueError("LLM extraction missing required user_goal or initial facts")

    persona = UserPersona(
        tech_level=_enum_value(persona_obj.get("tech_level"), {"low", "medium", "high"}, "medium"),
        patience=_enum_value(persona_obj.get("patience"), {"low", "medium", "high"}, "medium"),
        cooperation=_enum_value(persona_obj.get("cooperation"), {"low", "medium", "high"}, "medium"),
        style=_enum_value(persona_obj.get("style"), {"concise", "verbose"}, "concise"),
        emotion=_enum_value(persona_obj.get("emotion"), {"neutral", "anxious", "impatient"}, "neutral"),
    )

    return UserGoalSeed(
        dialogue_id=dialogue.dialogue_id,
        target_case_id=dialogue.resolution.case_id,
        target_title=dialogue.resolution.title,
        user_goal=str(raw.get("user_goal", "")).strip(),
        known_facts=known_facts,
        hidden_facts=hidden_facts,
        reveal_schedule=schedule,
        persona=persona,
        noise=_as_str_list(raw.get("noise")),
        source_turns=dialogue.turns,
        metadata={
            "extractor": "llm_v1",
            "agent_labels": _agent_labels(dialogue),
        },
    )
