from __future__ import annotations

import json
from typing import List

from schemas import CaseDialoguePair, CaseRecord, DialogueRecord
from utils import truncate_text


QUESTION_PATTERN_JSON_SCHEMA = """
{
  "case_id": "",
  "dialogue_level_patterns": [
    {
      "dialogue_id": "",
      "surface_problem": "",
      "initial_question": "",
      "known_facts": [],
      "hidden_facts": [],
      "missing_slots": [],
      "reveal_path": [],
      "user_style": "",
      "evidence": []
    }
  ],
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
    {
      "slot": "",
      "when_to_reveal": "",
      "example_user_phrase": "",
      "source": "dialogue|case|inferred"
    }
  ],
  "simulator_actions": [
    {
      "turn_stage": "opening|after_clarification|after_solution|closing",
      "user_intent": "",
      "behavior": "",
      "example": "",
      "depends_on_agent": ""
    }
  ],
  "evaluation_focus": []
}
""".strip()


FIELD_EXPLANATIONS = """
字段解释：
- dialogue_level_patterns：逐条对话的用户提问结果。每个输入 dialogue 至多输出一条记录，必须基于该 dialogue 本身，不要混入其他 dialogue；
  - dialogue_id：对应输入 dialogue_id；
  - surface_problem：该对话中用户表面描述的问题/直接现象；
  - initial_question：该对话里用户最初的问题或最能代表开场的表达；
  - known_facts：该对话中用户开场或早期已经知道/主动提供的信息；
  - hidden_facts：该对话中用户知道但后续才透露、或客服追问后才透露的信息；
  - missing_slots：该对话开场缺失、客服需要追问的信息；
  - reveal_path：该对话中信息透露的顺序，例如“先说现象 -> 被问后补充版本 -> 方案后反馈失败”；
  - user_style：该对话中用户的表达风格；
  - evidence：支持上述判断的短证据，只写简短片段，不要长段复制原文；
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
""".strip()


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
- 必须先逐条分析每个 dialogue，保留“每条真实对话对应一个用户提问结果”；
- 然后再做 case 级汇总，不要只输出混合后的总体结论；
- 必须区分真实对话中观察到的信息、从案例答案推断的信息、以及不确定的信息；
- 输出要能作为后续用户模拟器的中间表示，而不仅是自然语言总结。

请严格输出 JSON：
{QUESTION_PATTERN_JSON_SCHEMA}

{FIELD_EXPLANATIONS}

约束：
- dialogue_level_patterns 必须优先从真实 dialogue 抽取；如果某条对话信息很少，也要输出一条简短记录，并把不确定处放入 missing_slots 或 evidence；
- case 级字段 surface_problem_patterns、known_facts、hidden_facts 等，是对 dialogue_level_patterns 的聚合总结，不要求和 dialogue 数量一致；
- 如果某个信息只来自 case 答案，而真实对话没有说，请放入 inferred_from_case；
- 如果不确定真实用户是否会这样说，请放入 uncertain_points；
- 不要输出 markdown、解释文字、代码块；
- 不要输出电话号码、邮箱、URL、账号等敏感原文，可以用 [PHONE]、[EMAIL]、[URL]、[ACCOUNT] 代替。

输入数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def build_case_only_question_pattern_prompt(case: CaseRecord) -> str:
    payload = {
        "case": {
            "case_id": case.case_id,
            "title": case.title,
            "phenomenon": case.phenomenon,
            "solution": case.solution,
        }
    }
    return f"""
你正在帮助构建企业客服 AI 评测用的用户模拟器。

这次输入只有案例库 case，没有任何历史对话。

最终目标：
- 给定一个新 case，即使没有历史对话，也能推断真实用户可能如何提问；
- 输出结构必须和有历史对话时的 question_patterns.jsonl 兼容；
- 后续用户模拟器会直接消费这些字段生成多轮用户。

输入包括：
1. 案例标题：答案侧的知识名称；
2. 问题现象：案例库描述的问题表现；
3. 解决方案：客服 AI 最终应该引导到的处理步骤。

分析目标：
- 不要生成完整对话；
- 不要复述解决方案；
- 从 case 的标题、现象、解决方案中，反推用户在真实场景下可能看到什么、知道什么、不知道什么；
- 重点输出 surface_problem、initial_question、known_facts、hidden_facts、missing_slots、slot_reveal_plan；
- 因为没有真实历史对话，必须明确哪些内容是从 case 推断出来的。

请严格输出 JSON：
{QUESTION_PATTERN_JSON_SCHEMA}

{FIELD_EXPLANATIONS}

case-only 约束：
- 不存在真实历史对话，所以 dialogue_level_patterns 不是 observed dialogue，而是“case-only synthetic user seed”；
- dialogue_level_patterns 请输出 3 条，分别代表该 case 可能对应的 3 类用户开场方式；
- dialogue_id 使用 synthetic_1、synthetic_2、synthetic_3；
- evidence 只能引用 case 标题、问题现象、解决方案中的短片段；
- observed_from_dialogue 必须输出空数组 []；
- inferred_from_case 必须列出所有主要推断依据；
- slot_reveal_plan 中 source 只能使用 "case" 或 "inferred"，不要使用 "dialogue"；
- 如果某个用户信息无法从 case 判断，请放入 uncertain_points；
- 不要编造具体电话、邮箱、URL、账号、人员姓名；
- surface_problem_patterns 建议输出 3-5 条，少于 3 条时请从 case 现象和解决步骤中合理推断；
- initial_question_patterns 建议输出 3-5 条，必须是用户口语化开场，而不是案例标题改写；
- known_facts 表示用户从自身问题中通常能知道的信息；
- hidden_facts 表示用户可能知道但开场不会主动说、需要客服追问的信息。

输入数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def format_dialogue(dialogue: DialogueRecord, max_turns: int, max_chars: int) -> str:
    lines: List[str] = [f"dialogue_id: {dialogue.dialogue_id}"]
    for turn in dialogue.turns[:max_turns]:
        role = "用户" if turn.role == "user" else "客服"
        lines.append(f"{role}: {turn.text}")
    return truncate_text("\n".join(lines), max_chars)
