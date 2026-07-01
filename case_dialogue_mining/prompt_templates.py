from __future__ import annotations

import json
from typing import List

from schemas import CaseDialoguePair, CaseRecord, DialogueRecord
from utils import truncate_text


QUESTION_PATTERN_JSON_SCHEMA = """
{
  "case_id": "",
  "case_understanding": {
    "target_case_id": "",
    "user_visible_problem": "",
    "likely_user_goal": "",
    "required_slots": [],
    "case_to_question_summary": "",
    "evidence_from_case": []
  },
  "behavior_model": {
    "dialogue_level_patterns": [
      {
        "dialogue_id": "",
        "surface_problem": "",
        "initial_question": "",
        "known_facts": [],
        "hidden_facts": [],
        "missing_slots": [],
        "reveal_path": [
          {
            "condition": "",
            "reveal": "",
            "example_user_phrase": ""
          }
        ],
        "expression_style": "",
        "evidence": []
      }
    ],
    "surface_problem_patterns": [],
    "initial_question_patterns": [],
    "known_facts": [],
    "hidden_facts": [],
    "reveal_patterns": [],
    "expression_style_patterns": [],
    "common_missing_slots": [],
    "difficulty_observations": [],
    "observed_from_dialogue": [],
    "inferred_from_case": [],
    "uncertain_points": []
  },
  "simulation_plan": {
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
    "simulation_suggestions": [],
    "evaluation_focus": [],
    "stop_conditions": []
  }
}
""".strip()


FIELD_EXPLANATIONS = """
字段解释：
- case_understanding：从答案侧 case 得到的目标理解，回答“用户最终要解决什么、评测要命中哪个 case”；
  - target_case_id：目标 case_id；
  - user_visible_problem：用户能直接看到/感受到的问题现象；
  - likely_user_goal：用户真实想完成的事情，而不是客服方案本身；
  - required_slots：客服 AI 定位该 case 通常需要知道的关键信息；
  - case_to_question_summary：一句话总结“答案侧 case 如何转化成用户侧问题”；
  - evidence_from_case：来自案例标题、现象、解决方案的短证据。
- behavior_model：用户行为建模，回答“用户会怎么表达、知道什么、隐藏什么、怎么透露”；
- simulation_plan：模拟执行计划，回答“模拟器每一阶段应该怎么说、何时停、评测什么”；
- dialogue_level_patterns：逐条对话的用户提问结果。每个输入 dialogue 至多输出一条记录，必须基于该 dialogue 本身，不要混入其他 dialogue；
  - dialogue_id：对应输入 dialogue_id；
  - surface_problem：该对话中用户表面描述的问题/直接现象；
  - initial_question：该对话里用户最初的问题或最能代表开场的表达；
  - known_facts：该对话中用户开场或早期已经知道/主动提供的信息；
  - hidden_facts：该对话中用户知道但后续才透露、或客服追问后才透露的信息；
  - missing_slots：该对话开场缺失、客服需要追问的信息；
  - reveal_path：该对话中信息透露的路径，用结构化对象说明“客服问到什么时、用户透露什么、可能怎么说”；
  - expression_style：该对话中用户的表达方式，例如开场简短、描述模糊、依赖截图、先抱怨后补充信息。这里只记录表达现象，不判断用户 persona；
  - evidence：支持上述判断的短证据，只写简短片段，不要长段复制原文；
- surface_problem_patterns：用户面对该 case 时的表面问题/直接现象；
- initial_question_patterns：用户开场通常怎么问；
- known_facts：用户通常知道并可能主动提供的信息；
- hidden_facts：用户知道但往往被追问后才说的信息；
- reveal_patterns：信息透露节奏，例如先模糊描述、再补充 ID、错误码、地点等；
- expression_style_patterns：从该 case 的历史对话中观察到的表达方式规律，不等同于 persona_bank 里的用户画像；
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
- 程序会在解析后自动生成顶层兼容字段；你只需要输出 case_understanding、behavior_model、simulation_plan 三层。
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
- 只输出新的三层结构：case_understanding、behavior_model、simulation_plan。

请严格输出 JSON：
{QUESTION_PATTERN_JSON_SCHEMA}

{FIELD_EXPLANATIONS}

约束：
- dialogue_level_patterns 必须优先从真实 dialogue 抽取；如果某条对话信息很少，也要输出一条简短记录，并把不确定处放入 missing_slots 或 evidence；
- behavior_model 中的 surface_problem_patterns、known_facts、hidden_facts 等，是对 dialogue_level_patterns 的聚合总结，不要求和 dialogue 数量一致；
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
你正在帮助构建企业 IT 客服 AI 评测用的任务型用户模拟器。

当前输入只有案例库 case，没有任何真实历史对话。

你的任务不是回答用户问题，也不是生成完整客服对话，而是：
从“答案侧 case”反推出“真实用户侧可能如何提问”，并输出后续用户模拟器可直接消费的结构化 seed。

最终目标：
- 给定一个新 case，即使没有历史对话，也能推断真实用户可能如何开场提问；
- 输出结构必须和 question_patterns.jsonl 使用同一套三层 schema；
- 后续用户模拟器会消费这些字段，用于生成多轮用户提问；
- 模拟器最终用于评测客服 AI 是否能命中正确 case_id。

输入包括：
1. case_id：目标案例 ID；
2. case title：案例标题，通常是答案侧知识名称；
3. case phenomenon：案例库描述的问题现象；
4. case solution：案例库中的处理步骤或解决方案。

请特别注意：
- case solution 是客服侧答案，不是用户侧表达；
- 不要把解决方案直接改写成用户提问；
- 你需要先从 case 中推断用户真实能感知到的问题状态，再生成用户可能的提问方式。

请按照下面的推理顺序进行分析，但最终只输出 JSON，不要输出推理过程：

第一步：理解 case 解决的真实问题
- 这个 case 最终解决什么问题？
- 用户遇到这个问题时，表面上会看到什么？
- 用户真实想达成什么目标？
- 要准确定位到这个 case，客服 AI 需要收集哪些关键信息？

第二步：把答案侧 case 转成用户侧问题
- 用户通常不会知道 case_id；
- 用户通常不会知道完整解决方案；
- 用户通常只知道自己看到的报错、失败现象、打不开、权限不足、申请失败、升级失败等；
- 用户可能知道部分细节，例如软件名、系统名、错误码、账号、设备、时间、操作入口，但不一定会第一轮主动说。

第三步：区分三类信息
1. known_facts：用户从自身问题中天然知道、且可能开场就说的信息。例如哪个系统打不开、哪个软件闪退、看到什么报错、自己想申请什么权限。不要把解决方案步骤写入 known_facts。
2. hidden_facts：用户可能知道，但通常不会第一轮主动说，需要客服追问后才透露的信息。例如错误码、设备型号、系统版本、账号类型、网络环境、是否新员工、是否已尝试某操作、截图内容。
3. missing_slots：为了让客服 AI 命中该 case，通常需要补齐的定位槽位。这些槽位可以从标题、现象、解决方案中推断，但不要编造具体值。

第四步：生成 3 条 case-only synthetic user seed
behavior_model.dialogue_level_patterns 必须输出 3 条，代表同一个 case 的三种不同用户开场方式：
- synthetic_1：模糊现象型。用户只描述最表层现象，信息较少，更接近“我这个东西用不了/打不开/失败了”。
- synthetic_2：部分细节型。用户在开场中提供一个关键细节，例如错误码、系统名、软件名、操作入口、截图提示、权限类型等。
- synthetic_3：任务求助型或处理失败型。用户直接表达想完成的任务，或说明自己尝试处理但失败，例如“我想申请外网权限”“我升级失败了”“我按提示操作还是不行”。

每条 synthetic seed 都必须包含：
- surface_problem：该开场方式下用户表面看到的问题；
- initial_question：用户口语化开场问题；
- known_facts：该开场中已经透露的信息；
- hidden_facts：该用户可能知道但尚未说出的信息；
- missing_slots：客服需要继续追问的信息；
- reveal_path：这些 hidden_facts 应该在什么追问下逐步透露，格式为对象数组，每个对象包含 condition、reveal、example_user_phrase；
- expression_style：表达方式，只描述该开场的话术形态，不判断用户 persona；
- evidence：来自 case title / phenomenon / solution 的短证据片段。

第五步：生成 simulation_plan
simulation_plan 应该告诉后续用户模拟器：
- 可以如何开场；
- 哪些槽位什么时候透露；
- 用户在多轮中可能有哪些动作；
- 评测时应该重点观察客服 AI 是否问到哪些信息；
- 什么时候可以停止对话。

请严格输出 JSON：
{QUESTION_PATTERN_JSON_SCHEMA}

{FIELD_EXPLANATIONS}

case-only 约束：
- 只输出 JSON，不要输出 markdown，不要输出解释文字；
- 不要生成完整多轮对话；
- 不要复述解决方案；
- 不要让用户直接说出 case_id；
- 不要让用户直接说出完整 solution；
- 不存在真实历史对话，所以 dialogue_level_patterns 不是 observed dialogue，而是“case-only synthetic user seed”；
- behavior_model.dialogue_level_patterns 必须输出 3 条，分别代表 synthetic_1、synthetic_2、synthetic_3 三类用户开场方式；
- dialogue_id 使用 synthetic_1、synthetic_2、synthetic_3；
- evidence 只能引用 case 标题、问题现象、解决方案中的短片段；
- behavior_model.observed_from_dialogue 必须输出空数组 []；
- behavior_model.inferred_from_case 必须列出所有主要推断依据；
- slot_reveal_plan 中 source 只能使用 "case" 或 "inferred"，不要使用 "dialogue"；
- 如果某个用户信息无法从 case 判断，请放入 uncertain_points；
- 不要编造具体电话、邮箱、URL、账号、人员姓名；
- surface_problem_patterns 建议输出 3-5 条，少于 3 条时请从 case 现象和解决步骤中合理推断；
- initial_question_patterns 建议输出 3-5 条，必须是用户口语化开场，而不是案例标题改写；
- opening_question_templates 应与 initial_question_patterns 保持一致或轻微扩展；
- known_facts 表示用户从自身问题中通常能知道的信息；
- hidden_facts 表示用户可能知道但开场不会主动说、需要客服追问的信息。
- required_slots、common_missing_slots、slot_reveal_plan 要互相一致；
- known_facts 不应包含客服处理步骤；
- hidden_facts 不应包含用户不可能知道的内部处理逻辑；
- expression_style_patterns 只描述表达方式，例如简短、口语化、模糊、依赖截图、直接求助、先说失败现象等，不要写成 persona；
- difficulty_observations 应说明该 case 为什么可能难以命中，例如现象泛化、相似 case 多、关键槽位不明显、用户可能不主动提供错误码等。

输入数据：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def format_dialogue(dialogue: DialogueRecord, max_turns: int, max_chars: int) -> str:
    lines: List[str] = [f"dialogue_id: {dialogue.dialogue_id}"]
    for turn in dialogue.turns[:max_turns]:
        role = "用户" if turn.role == "user" else "客服"
        lines.append(f"{role}: {turn.text}")
    return truncate_text("\n".join(lines), max_chars)
