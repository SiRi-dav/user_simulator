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
- 必须区分真实对话中观察到的信息、从案例答案推断的信息、以及不确定的信息；
- 输出要能作为后续用户模拟器的中间表示，而不仅是自然语言总结。

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
  "simulation_suggestions": [],
  "observed_from_dialogue": [],
  "inferred_from_case": [],
  "uncertain_points": [],
  "case_to_question_summary": "",
  "opening_question_templates": [],
  "slot_reveal_plan": [
    {{
      "slot": "",
      "when_to_reveal": "",
      "example_user_phrase": "",
      "source": "dialogue|case|inferred"
    }}
  ],
  "simulator_actions": [
    {{
      "turn_stage": "opening|after_clarification|after_solution|closing",
      "user_intent": "",
      "behavior": "",
      "example": "",
      "depends_on_agent": ""
    }}
  ],
  "evaluation_focus": []
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
- observed_from_dialogue：只能写真实历史对话中明确出现或高度稳定出现的用户行为/信息；
- inferred_from_case：只能写从案例标题、现象、解决方案推断出的用户可能问题，不要混入 observed；
- uncertain_points：样本不足、对话未直接支持、或你不确定的点；
- case_to_question_summary：一句话总结“答案侧 case 如何转化成用户侧问题”；
- opening_question_templates：可复用的用户开场模板，保留口语化表达，但不要编造具体账号、电话、URL；
- slot_reveal_plan：用户隐藏信息/槽位的透露计划，说明何时说、怎么说、来源是什么；
- simulator_actions：多轮模拟动作，不是完整对话，而是用户在不同阶段的行为策略；
- evaluation_focus：用这个 case 测客服 AI 时应重点检查什么能力。

约束：
- 如果某个信息只来自 case 答案，而真实对话没有说，请放入 inferred_from_case；
- 如果不确定真实用户是否会这样说，请放入 uncertain_points；
- 不要输出 markdown、解释文字、代码块；
- 不要输出电话号码、邮箱、URL、账号等敏感原文，可以用 [PHONE]、[EMAIL]、[URL]、[ACCOUNT] 代替。

输入数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def format_dialogue(dialogue: DialogueRecord, max_turns: int, max_chars: int) -> str:
    lines: List[str] = [f"dialogue_id: {dialogue.dialogue_id}"]
    for turn in dialogue.turns[:max_turns]:
        role = "用户" if turn.role == "user" else "客服"
        lines.append(f"{role}: {turn.text}")
    return truncate_text("\n".join(lines), max_chars)
