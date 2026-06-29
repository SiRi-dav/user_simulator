from __future__ import annotations

import re
from typing import List

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


def extract_goal_seed(dialogue: NormalizedDialogue) -> UserGoalSeed:
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

