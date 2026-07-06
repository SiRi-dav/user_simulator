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
