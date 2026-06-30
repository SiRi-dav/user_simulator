from __future__ import annotations

import json
from typing import List

from schemas import CaseDialoguePair, DialogueRecord
from utils import truncate_text


def build_case_question_pattern_prompt(
    pair: CaseDialoguePair,
    max_dialogues: int,
    max_turns_per_dialogue: int,
    max_chars_per_dialogue: int,
) -> str:
    dialogues = pair.dialogues[:max_dialogues]
    dialogue_blocks = [
        format_dialogue(dialogue, max_turns_per_dialogue, max_chars_per_dialogue)
        for dialogue in dialogues
    ]
    payload = {
        "case": {
            "case_id": pair.case.case_id,
            "title": pair.case.title,
            "phenomenon": pair.case.phenomenon,
            "solution": pair.case.solution,
        },
        "dialogue_count_used": len(dialogues),
        "dialogues": dialogue_blocks,
    }
    return f"""
你正在帮助构建企业客服 AI 评测用的用户模拟器。

输入包括：
1. 案例库 case：这是答案侧信息，包括问题标题、现象和解决方案；
2. 多条真实历史对话：这些对话最终命中了该 case_id，代表真实用户是如何把这个问题问出来的。

分析目标：
- 不要生成新的用户回复；
- 不要复述解决方案；
- 请总结“用户如何从真实问题出发，一步步提问并透露信息”；
- 重点提炼 case 到用户提问方式的框架。

请严格输出 JSON：
{{
  "case_id": "",
  "surface_problem_patterns": [],
  "initial_question_patterns": [],
  "known_facts": [],
  "hidden_facts": [],
  "reveal_patterns": [],
  "user_style_summary": "",
  "common_missing_slots": [],
  "difficulty_observations": [],
  "simulation_suggestions": []
}}

字段解释：
- surface_problem_patterns：用户面对该 case 时的表面问题/直接现象；
- initial_question_patterns：用户开场通常怎么问；
- known_facts：用户通常知道并可能主动提供的信息；
- hidden_facts：用户知道但往往被追问后才说的信息；
- reveal_patterns：信息透露节奏，例如先模糊描述、再补充 ID、错误码、地点等；
- user_style_summary：用户表达风格总结；
- common_missing_slots：开场常缺失的关键槽位；
- difficulty_observations：对客服 AI 有挑战的行为点；
- simulation_suggestions：后续用户模拟器如何模拟这类 case。

输入数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def format_dialogue(dialogue: DialogueRecord, max_turns: int, max_chars: int) -> str:
    lines: List[str] = [f"dialogue_id: {dialogue.dialogue_id}"]
    for turn in dialogue.turns[:max_turns]:
        role = "用户" if turn.role == "user" else "客服"
        lines.append(f"{role}: {turn.text}")
    return truncate_text("\n".join(lines), max_chars)

