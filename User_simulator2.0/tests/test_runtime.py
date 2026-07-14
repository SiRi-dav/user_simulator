from main import (
    build_blind_user_runtime_view,
    build_blind_user_view,
    build_runtime_roadmap,
    count_case_analysis_artifacts,
    load_completed_analysis_case_ids,
    load_behavior_taxonomy,
    load_employee_personas,
    persist_case_analysis_artifacts,
)
from src.llm.mock_llm_client import MockLLMClient
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.runtime.blind_user import BlindUser
from src.runtime.simulator import Simulator
from src.schemas import BlindUserCaseView, Case, CaseAnalysisDebugArtifact, DialogueState, KnowledgeAssessment, KnowledgeRoadmapArtifact


class PromptCaptureLLMClient(MockLLMClient):
    def __init__(self):
        self.last_user_prompt = ""

    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        self.last_user_prompt = user_prompt
        if schema_name == "BlindUserAction":
            return {
                "user_action": "continue",
                "reply": "好的。",
                "state_update": {"solution_status": "not_solved", "should_stop": False, "stop_reason": None},
                "reason": "capture prompt",
            }
        return super().generate_json(system_prompt, user_prompt, schema_name, temperature)


class InitialPromptCaptureLLMClient(MockLLMClient):
    def __init__(self):
        self.initial_prompt = ""

    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        if schema_name == "InitialUserReply":
            self.initial_prompt = user_prompt
            return {"reply": "用户开场"}
        return super().generate_json(system_prompt, user_prompt, schema_name, temperature)


class SilentStopLLMClient(MockLLMClient):
    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        if schema_name == "BlindUserAction":
            return {
                "user_action": "stop_no_effective_solution",
                "reply": "",
                "state_update": {
                    "solution_status": "not_solved",
                    "should_stop": True,
                    "stop_reason": "assistant_unable_to_provide_effective_solution",
                },
                "reason": "no executable next step",
            }
        return super().generate_json(system_prompt, user_prompt, schema_name, temperature)


def test_runtime_step_solved_sets_should_stop():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    simulator = Simulator(
        build_blind_user_runtime_view(build_blind_user_view(roadmap)),
        build_runtime_roadmap(roadmap),
        {"name": "low_tech"},
        llm,
    )
    simulator.start()
    result = simulator.step("你可以先结束 Outlook 的残留进程再重新打开。")
    assert result["state"]["solution_status"] == "solution_accepted"
    assert result["state"]["should_stop"] is True
    assert result["user_action"]["user_action"] == "accept_actionable_solution_and_stop"
    assert result["user_reply"]


def test_simulator_applies_pending_action_result_state_update():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    simulator = Simulator(
        build_blind_user_runtime_view(build_blind_user_view(roadmap)),
        build_runtime_roadmap(roadmap),
        {"name": "low_tech"},
        llm,
    )

    simulator._apply_state_update(
        {
            "pending_action_result": True,
            "last_action_summary": "重启应用",
            "pending_action_solution_match": "actionable_but_not_target",
            "pending_action_result_facts": ["重启后仍显示原错误"],
        }
    )
    assert simulator.state.pending_action_result is True
    assert simulator.state.last_action_summary == "重启应用"
    assert simulator.state.pending_action_solution_match == "actionable_but_not_target"
    assert simulator.state.pending_action_result_facts == ["重启后仍显示原错误"]

    simulator._apply_state_update(
        {
            "pending_action_result": False,
            "last_action_summary": None,
            "pending_action_solution_match": None,
            "pending_action_result_facts": [],
        }
    )
    assert simulator.state.pending_action_result is False
    assert simulator.state.last_action_summary is None
    assert simulator.state.pending_action_solution_match is None
    assert simulator.state.pending_action_result_facts == []


def test_simulator_allows_silent_stop_without_appending_empty_user_reply():
    llm = SilentStopLLMClient()
    target = Case(case_id="CASE_001", title="加域失败", phenomenon="加域失败", solution="后台处理")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    simulator = Simulator(
        build_blind_user_runtime_view(build_blind_user_view(roadmap)),
        build_runtime_roadmap(roadmap),
        {"name": "low_tech"},
        llm,
    )
    simulator.start()
    result = simulator.step("需要管理员账号和密码执行 netdom join。")

    assert result["user_reply"] == ""
    assert simulator.state.should_stop is True
    assert simulator.state.stop_reason == "assistant_unable_to_provide_effective_solution"
    assert simulator.dialogue_history[-1]["role"] == "assistant"


def test_simulator_initial_reply_uses_blind_view_not_full_roadmap_surface_problem():
    llm = InitialPromptCaptureLLMClient()
    target = Case(case_id="CASE_001", title="内部完整标题", phenomenon="完整 roadmap 里的现象", solution="隐藏解决方案")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    blind_case_view = BlindUserCaseView(
        case_id="CASE_001",
        surface_problem="安全视图里的表层问题",
        opening_intent="安全视图里的开场意图",
        user_facing_points=[],
    )
    blind_runtime_view = build_blind_user_runtime_view(blind_case_view)

    Simulator(blind_runtime_view, build_runtime_roadmap(roadmap), {"name": "low_tech"}, llm).start()

    assert "安全视图里的表层问题" in llm.initial_prompt
    assert "安全视图里的开场意图" in llm.initial_prompt
    assert "隐藏解决方案" not in llm.initial_prompt


def test_build_blind_user_runtime_view_keeps_only_visible_text_not_point_metadata():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="内部标题", phenomenon="用户看到的现象", solution="隐藏解决方案")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    case_view = build_blind_user_view(roadmap)

    runtime_view = build_blind_user_runtime_view(case_view)
    payload = runtime_view.model_dump()

    assert payload["user_visible_facts"]
    assert "point_id" not in str(payload)
    assert "source_quote" not in str(payload)
    assert "source_case_id" not in str(payload)


def test_persist_case_analysis_artifacts_marks_case_completed(tmp_path):
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    blind_view = build_blind_user_view(roadmap)
    knowledge_artifact = KnowledgeRoadmapArtifact(
        case_id=target.case_id,
        title=target.title,
        roadmap=build_runtime_roadmap(roadmap),
    )
    debug_artifact = CaseAnalysisDebugArtifact(
        case_id=target.case_id,
        target_case=target,
        retrieval_queries=[],
        related_cases=[],
        verified_points=[],
        dropped_points=[],
        warnings=[],
        relations=[],
        roadmap=roadmap,
    )

    totals = persist_case_analysis_artifacts(tmp_path, blind_view, knowledge_artifact, debug_artifact)

    assert totals["knowledge"] == 1
    assert totals["blind_runtime"] == 1
    assert count_case_analysis_artifacts(tmp_path) == {
        "blind_views": 1,
        "blind_runtime": 1,
        "knowledge": 1,
        "debug": 1,
    }
    assert load_completed_analysis_case_ids(tmp_path) == {"CASE_001"}


def test_runtime_loads_manual_seed_behavior_assets_when_outputs_missing(tmp_path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    personas = load_employee_personas(output_dir / "employee_personas.jsonl")
    taxonomy = load_behavior_taxonomy(output_dir / "user_behavior_taxonomy.jsonl")

    assert personas[0].persona_id == "persona_real_problem_low_tech"
    assert {item.behavior_name for item in taxonomy} >= {
        "陈述或继续澄清问题",
        "回答客服并释放信息",
        "询问具体操作办法",
    }
    assert all(item.decision_rules for item in taxonomy)
    assert all(item.prohibited_behaviors for item in taxonomy)
    assert all(item.state_transitions for item in taxonomy)

    resolution_policy = next(item for item in taxonomy if item.behavior_name == "确认解决、继续求助或升级")
    assert any("solution_match=target" in rule for rule in resolution_policy.decision_rules)
    assert any("impatient" in rule for rule in resolution_policy.prohibited_behaviors)

    how_to_policy = next(item for item in taxonomy if item.behavior_name == "询问具体操作办法")
    action_policy = next(item for item in taxonomy if item.behavior_name == "尝试操作并反馈结果")
    opening_policy = next(item for item in taxonomy if item.behavior_name == "陈述或继续澄清问题")
    assert any("动作复杂" in rule for rule in how_to_policy.decision_rules)
    assert any("action_execution_feedback.has_pending_result=true" in rule for rule in action_policy.decision_rules)
    assert any("不强制选择 report_action_result" in rule for rule in action_policy.decision_rules)
    assert any("pending_action_solution_match" in rule for rule in action_policy.decision_rules)
    assert "默认一句话" in opening_policy.simulator_policy_hint
    assert any("不复盘全部历史" in rule for rule in opening_policy.decision_rules)
    assert any("后台" in rule for rule in opening_policy.decision_rules)
    assert any("长篇复盘" in item for item in action_policy.prohibited_behaviors)


def test_runtime_uses_seed_rules_and_merges_mined_behavior_evidence(tmp_path):
    output_path = tmp_path / "user_behavior_taxonomy.jsonl"
    output_path.write_text(
        '{"behavior_name":"确认解决或继续求助","definition":"旧规则","trigger_assistant_acts":["solution_output"],'
        '"typical_user_response_patterns":["我先试试看"],"persona_sensitivity":{"cooperative":"low"},'
        '"simulator_policy_hint":"旧提示","decision_rules":["target 需要等待执行结果"],'
        '"prohibited_behaviors":["旧禁止项"],"state_transitions":{"old":"old"}}\n',
        encoding="utf-8",
    )

    taxonomy = load_behavior_taxonomy(output_path)
    resolution = next(item for item in taxonomy if item.behavior_name == "确认解决、继续求助或升级")

    assert len(taxonomy) == 6
    assert resolution.definition != "旧规则"
    assert "我先试试看" in resolution.typical_user_response_patterns
    assert resolution.persona_sensitivity["cooperative"] == "low"
    assert any("solution_match=target" in rule for rule in resolution.decision_rules)
    assert "target 需要等待执行结果" not in resolution.decision_rules
    assert "old" not in resolution.state_transitions


def test_blind_user_action_prompt_receives_only_allowed_knowledge_assessment_fields():
    llm = PromptCaptureLLMClient()
    assessment = KnowledgeAssessment(
        assistant_act="solution_output",
        matched_scope="target_solution",
        matched_point_ids=["P3"],
        allowed_facts=["assistant 已给出可尝试方法"],
        unknown_requested_facts=[],
        solution_match="target",
        progress_status="new_progress",
        no_more_user_info=False,
        state_update={},
        reason="test",
    )

    BlindUser(llm).choose_action_and_reply(assessment, {"name": "low_tech"}, None, [], "Outlook 打不开", [])

    assert "allowed_facts" in llm.last_user_prompt
    assert "assistant 已给出可尝试方法" in llm.last_user_prompt
    assert "forbidden_content" not in llm.last_user_prompt
    assert "hidden_solution_or_case_details" not in llm.last_user_prompt


def test_blind_user_action_prompt_exposes_action_execution_feedback():
    llm = PromptCaptureLLMClient()
    assessment = KnowledgeAssessment(
        assistant_act="clarification_question",
        matched_scope="case_internal",
        matched_point_ids=[],
        allowed_facts=["当前仍不可用"],
        unknown_requested_facts=[],
        solution_match="none",
        progress_status="new_progress",
        no_more_user_info=False,
        state_update={},
        reason="test",
    )
    state = DialogueState(
        pending_action_result=True,
        last_action_summary="重启 Outlook",
        pending_action_solution_match="actionable_but_not_target",
        pending_action_result_facts=["重启后还是看不到新邮件提醒"],
    )

    BlindUser(llm).choose_action_and_reply(
        assessment,
        {"name": "low_tech"},
        None,
        [],
        "Outlook 没有新邮件提醒",
        [],
        state,
    )

    assert "Action execution feedback" in llm.last_user_prompt
    assert '"has_pending_result": true' in llm.last_user_prompt
    assert "重启 Outlook" in llm.last_user_prompt
    assert "重启后还是看不到新邮件提醒" in llm.last_user_prompt
    assert "world-model feedback" in llm.last_user_prompt
