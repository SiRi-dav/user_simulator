from main import load_behavior_taxonomy, load_employee_personas
from src.llm.mock_llm_client import MockLLMClient
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.runtime.simulator import Simulator
from src.schemas import Case


def test_runtime_step_solved_sets_should_stop():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    roadmap = RoadmapBuilder(llm).build_roadmap(target, [], [])
    simulator = Simulator(roadmap, {"name": "low_tech"}, llm)
    simulator.start()
    result = simulator.step("你可以先结束 Outlook 的残留进程再重新打开。")
    assert result["state"]["solution_status"] == "solved"
    assert result["state"]["should_stop"] is True
    assert result["user_reply"]


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
