from main import (
    build_blind_user_runtime_view,
    build_blind_user_view,
    build_runtime_roadmap,
    load_behavior_taxonomy,
    load_employee_personas,
)
from src.llm.mock_llm_client import MockLLMClient
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.runtime.blind_user import BlindUser
from src.runtime.simulator import Simulator
from src.schemas import BlindUserCaseView, BlindUserInstruction, Case


class PromptCaptureLLMClient(MockLLMClient):
    def __init__(self):
        self.last_user_prompt = ""

    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        self.last_user_prompt = user_prompt
        if schema_name == "BlindUserReply":
            return {"reply": "好的。"}
        return super().generate_json(system_prompt, user_prompt, schema_name, temperature)


class InitialPromptCaptureLLMClient(MockLLMClient):
    def __init__(self):
        self.initial_prompt = ""

    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        if schema_name == "InitialUserReply":
            self.initial_prompt = user_prompt
            return {"reply": "用户开场"}
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
    assert result["state"]["solution_status"] == "solved"
    assert result["state"]["should_stop"] is True
    assert result["user_reply"]


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


def test_blind_user_reply_prompt_hides_specific_forbidden_solution_text():
    llm = PromptCaptureLLMClient()
    instruction = BlindUserInstruction(
        user_intent="确认方案",
        allowed_content="好的，我试一下。",
        forbidden_content=["结束 Outlook 残留进程后重新打开", "CASE_001"],
        tone="low_tech",
    )

    BlindUser(llm).render_reply(instruction, {"name": "low_tech"}, None, [], "Outlook 打不开", [])

    assert "结束 Outlook 残留进程后重新打开" not in llm.last_user_prompt
    assert "CASE_001" not in llm.last_user_prompt
    assert "hidden_solution_or_case_details" in llm.last_user_prompt
