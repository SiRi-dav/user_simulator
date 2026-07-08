from __future__ import annotations

from typing import Any, Dict, Optional

from src.llm.llm_client import LLMClient


class MockLLMClient(LLMClient):
    """Deterministic test double. Production code should use OpenAICompatibleClient."""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_name: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        if schema_name == "RetrievalQueries":
            return {
                "queries": [
                    {"query_type": "surface_query", "query": "Outlook 打开后闪退", "reason": "用户可观察现象"},
                    {"query_type": "diagnostic_query", "query": "未进入登录页面直接退出", "reason": "区分登录失败"},
                    {"query_type": "solution_query", "query": "结束残留进程重新打开", "reason": "相似处理动作"},
                ]
            }
        if schema_name == "RelatedCases":
            return {
                "related_cases": [
                    {"case_id": "CASE_002", "relation_type": "confusing_wrong_path", "reason": "同为 Outlook 登录相关"},
                    {"case_id": "CASE_003", "relation_type": "similar_solution", "reason": "同为重启进程类处理"},
                ]
            }
        points = [
            {
                "point_id": "P1",
                "source_case_id": "CASE_001",
                "content": "Outlook 打开后立即退出",
                "source_field": "phenomenon",
                "source_quote": "用户打开 Outlook 后程序立即退出",
                "point_type": "user_facing",
                "grounding_type": "explicit",
                "trigger": ["开场描述问题"],
                "visibility": "opening_available",
                "leakage_risk": "low",
                "reason": "用户直接观察到的表面现象",
            },
            {
                "point_id": "P2",
                "source_case_id": "CASE_001",
                "content": "还没进入登录页面就退出",
                "source_field": "phenomenon",
                "source_quote": "未进入登录页面",
                "point_type": "diagnostic",
                "grounding_type": "explicit",
                "trigger": ["询问是否能登录", "询问退出时机"],
                "visibility": "ask_triggered",
                "leakage_risk": "low",
                "reason": "可区分登录失败类问题",
            },
            {
                "point_id": "P3",
                "source_case_id": "CASE_001",
                "content": "结束 Outlook 残留进程后重新打开",
                "source_field": "solution",
                "source_quote": "结束 Outlook 残留进程后重新打开。",
                "point_type": "solution",
                "grounding_type": "explicit",
                "trigger": ["assistant 给出解决方案"],
                "visibility": "judge_only",
                "leakage_risk": "high",
                "reason": "目标解决方案",
            },
            {
                "point_id": "P4",
                "source_case_id": "CASE_002",
                "content": "Outlook 输入密码后登录失败",
                "source_field": "related_case",
                "source_quote": "输入密码后提示账号认证失败",
                "point_type": "external",
                "grounding_type": "explicit",
                "trigger": ["assistant 询问登录认证问题"],
                "visibility": "external_only",
                "leakage_risk": "medium",
                "reason": "相似但可能错误的方向",
            },
        ]
        if schema_name == "Points":
            return {"points": points}
        if schema_name == "PointVerificationResult":
            return {"verified_points": points, "dropped_points": [], "warnings": []}
        if schema_name == "Relations":
            return {
                "relations": [
                    {"from_point_id": "P1", "to_point_id": "P2", "relation_type": "specifies", "reason": "退出时机补充表面问题"},
                    {"from_point_id": "P2", "to_point_id": "P3", "relation_type": "supports_target", "reason": "诊断信息支持目标方案"},
                    {"from_point_id": "P4", "to_point_id": "P2", "relation_type": "similar_but_wrong", "reason": "登录失败方向不符合未进入登录页面"},
                ]
            }
        if schema_name == "Roadmap":
            return {
                "target_case_id": "CASE_001",
                "surface_problem": "我这边 Outlook 一打开就退出来了。",
                "opening_intent": "希望客服帮忙恢复 Outlook 正常打开",
                "user_facing_points": [points[0]],
                "diagnostic_points": [points[1]],
                "solution_points": [points[2]],
                "external_points": [points[3]],
                "relations": [
                    {"from_point_id": "P1", "to_point_id": "P2", "relation_type": "specifies", "reason": "退出时机补充表面问题"},
                    {"from_point_id": "P2", "to_point_id": "P3", "relation_type": "supports_target", "reason": "诊断信息支持目标方案"},
                ],
                "target_route": ["P1", "P2", "P3"],
                "external_routes": [["P1", "P4"]],
                "forbidden_content": ["CASE_001", "结束 Outlook 残留进程后重新打开"],
            }
        if schema_name == "InitialUserReply":
            return {"reply": "我这边 Outlook 一打开就退出来了，帮我看一下。"}
        if schema_name == "AssistantAct":
            text = user_prompt
            if "结束 Outlook" in text or "残留进程" in text:
                act = "solution_output"
            elif "是登录不上" in text or "还是" in text:
                act = "clarification_question"
            else:
                act = "action_request"
            return {"assistant_act": act, "request_summary": "assistant latest reply", "confidence": 0.9, "reason": "mock classification"}
        if schema_name == "KnowledgeDecision":
            solved = "结束 Outlook" in user_prompt or "残留进程" in user_prompt
            return {
                "assistant_act": "solution_output" if solved else "clarification_question",
                "matched_scope": "target_solution" if solved else "case_internal",
                "matched_point_id": "P3" if solved else "P2",
                "decision": "confirm_and_stop" if solved else "reveal_fact",
                "instruction": {
                    "user_intent": "确认方案" if solved else "补充退出时机",
                    "allowed_content": "好的，那我按这个方法试一下。" if solved else "是打开以后就直接退出来了，还没到登录那一步。",
                    "forbidden_content": ["CASE_001"],
                    "tone": "low_tech",
                    "should_stop": solved,
                },
                "state_update": {
                    "exposed_point_ids_add": [] if solved else ["P2"],
                    "rejected_external_point_ids_add": [],
                    "action_request_count_delta": 0,
                    "how_to_check_count_delta": 0,
                    "solution_status": "solved" if solved else "not_solved",
                    "should_stop": solved,
                    "stop_reason": "solved" if solved else None,
                },
                "reason": "mock decision",
            }
        if schema_name == "BlindUserReply":
            solved = "好的，那我按这个方法试一下" in user_prompt
            return {"reply": "好的，那我按这个方法试一下。" if solved else "是打开以后就直接退出来了，还没到登录那一步。"}
        if schema_name == "DialogueBehaviorSummary":
            return {
                "dialogue_id": "DIALOG_001",
                "opening_pattern": "用户先描述表面故障，信息较简短",
                "user_persona_guess": "低技术但配合的员工",
                "observed_behaviors": [
                    {
                        "dialogue_id": "DIALOG_001",
                        "turn_index": 1,
                        "assistant_act": "clarification_question",
                        "user_behavior": "reveal_new_fact",
                        "user_text": "是打开以后就直接退出来了，还没到登录那一步。",
                        "assistant_text": "是登录不上还是打开就退出？",
                        "released_information_type": "diagnostic_fact",
                        "behavior_reason": "用户在追问后补充退出时机",
                    }
                ],
                "voluntary_information": ["Outlook 打不开，一点开就退出来"],
                "ask_triggered_information": ["还没到登录那一步"],
                "action_request_reactions": [],
                "offtrack_reactions": [],
                "solution_reactions": ["方案具体时表示愿意尝试"],
                "summary": "该用户开场简短，被追问后能补充关键诊断信息。",
            }
        if schema_name == "EmployeePersonas":
            return {
                "personas": [
                    {
                        "persona_id": "persona_low_tech_cooperative",
                        "persona_name": "低技术但配合的员工",
                        "description": "不熟悉技术术语，但愿意按客服问题补充信息。",
                        "technical_literacy": "low",
                        "patience_level": "medium",
                        "clarity_level": "medium",
                        "cooperation_level": "high",
                        "typical_opening_style": ["先说表面问题，细节有限"],
                        "information_release_style": "被追问后释放诊断事实",
                        "action_request_behavior": "会追问一次怎么操作，再尝试执行",
                        "offtrack_reaction_style": "用自身现象轻微纠正",
                        "solution_acceptance_style": "方案具体时会接受并表示尝试",
                        "evidence_dialogue_ids": ["DIALOG_001"],
                        "reason": "mock persona for tests",
                    }
                ]
            }
        if schema_name == "BehaviorTaxonomy":
            return {
                "behavior_taxonomy": [
                    {
                        "behavior_name": "追问后补充诊断事实",
                        "definition": "assistant 追问区分信息后，用户提供新的故障细节。",
                        "trigger_assistant_acts": ["clarification_question"],
                        "typical_user_response_patterns": ["补充错误时机", "说明是否出现登录页"],
                        "persona_sensitivity": {
                            "low_tech": "可能用非技术语言描述",
                            "impatient": "回答更短",
                            "cooperative": "较完整回答",
                            "vague": "只给部分信息",
                        },
                        "simulator_policy_hint": "在 roadmap 允许时释放一个 ask_triggered diagnostic fact。",
                    }
                ]
            }
        if schema_name == "SimulatorQualityJudge":
            return {
                "answer_alignment_score": 0.8,
                "information_progress_score": 0.9,
                "user_knowledge_boundary_score": 1.0,
                "interaction_realism_score": 0.85,
                "overall_score": 0.8875,
                "reasons": ["mock judge result"],
            }
        return {}
