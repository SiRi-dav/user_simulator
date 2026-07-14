from src.pipelines.run_roadmap_api_simulation import run_one_with_assistant_api
from src.simulator.assistant_api import AssistantApiClient
from src.simulator.llm_client import MockLLMClient
from src.simulator.roadmap_adapter import persona_from_name, seed_from_knowledge_roadmap


def test_seed_from_knowledge_roadmap_uses_original_v1_seed_shape():
    seed = seed_from_knowledge_roadmap(build_roadmap_record(), persona=persona_from_name("low_tech"))

    assert seed.target_case_id == "KT001"
    assert seed.user_goal == "Outlook 打开后自动退出"
    assert seed.reveal_schedule.initial == ["Outlook 打开后自动退出"]
    assert seed.reveal_schedule.deep_followup == ["没有进入登录页面"]


def test_v1_roadmap_api_simulation_writes_compatible_logs():
    seed = seed_from_knowledge_roadmap(build_roadmap_record(), persona=persona_from_name("low_tech"))
    assistant = AssistantApiClient(post_json=fake_post_json)

    result = run_one_with_assistant_api(seed, assistant, max_turns=2, llm=MockLLMClient())

    assert result["simulator_version"] == "v1_enterprise_user_simulator"
    assert result["turns"][0]["role"] == "user"
    assert result["compatible_logs"]
    log = result["compatible_logs"][0]
    assert log["module"] == "Simulator.step"
    assert log["case_id"] == "KT001"
    assert log["output"]["simulator_variant"] == "v1_enterprise_user_simulator"
    assert log["input"]["history_before_reply"][0]["role"] == "user"


def fake_post_json(url, payload, timeout):
    if url.endswith("/query"):
        return ["Outlook 闪退", 0.01]
    if url.endswith("/trigger"):
        return ["预案", 0.01]
    if url.endswith("/policy"):
        return ["", 0.01]
    if url.endswith("/response"):
        return ["请问是否还没进入登录页面？", 0.01]
    return ["", 0.01]


def build_roadmap_record():
    return {
        "case_id": "KT001",
        "title": "Outlook 打开后退出",
        "roadmap": {
            "target_case_id": "KT001",
            "surface_problem": "Outlook 打开后自动退出",
            "opening_intent": "恢复 Outlook 正常打开",
            "user_facing_points": [
                {
                    "point_id": "P1",
                    "content": "Outlook 打开后自动退出",
                    "visibility": "opening_available",
                }
            ],
            "diagnostic_points": [
                {
                    "point_id": "P2",
                    "content": "没有进入登录页面",
                    "visibility": "ask_triggered",
                }
            ],
            "solution_points": [
                {
                    "point_id": "P3",
                    "content": "结束 Outlook 残留进程后重新打开",
                    "visibility": "judge_only",
                }
            ],
            "target_route": ["P1", "P2", "P3"],
        },
    }
