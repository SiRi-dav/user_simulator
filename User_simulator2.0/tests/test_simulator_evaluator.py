from pathlib import Path

from src.llm.mock_llm_client import MockLLMClient
from src.schemas import DialogueTurn, HistoricalDialogue
from src.simulator_evaluator import (
    SimulatorEvaluator,
    behavioral_realism,
    collect_real_case_ids,
    extract_features,
    load_simulated_sessions,
    opening_similarity_alignment,
    select_real_dialogues,
    split_logs_into_sessions,
    trajectory_state_metrics,
)
from src.utils.jsonl import append_jsonl
from tests.test_evaluator_metrics import build_test_artifact


def test_select_real_dialogues_matches_case_id_inside_joined_list():
    dialogues = [
        HistoricalDialogue(
            dialogue_id="d1",
            case_id="KT001\nKT002",
            turns=[DialogueTurn(speaker="user", text="打不开")],
        ),
        HistoricalDialogue(
            dialogue_id="d2",
            case_id="KT003",
            turns=[DialogueTurn(speaker="user", text="登录失败")],
        ),
    ]

    selected = select_real_dialogues(dialogues, "KT002")

    assert [dialogue.dialogue_id for dialogue in selected] == ["d1"]


def test_collect_real_case_ids_keeps_unique_ids():
    dialogues = [
        HistoricalDialogue(
            dialogue_id="d1",
            case_id="KT001\nKT002",
            turns=[DialogueTurn(speaker="user", text="打不开")],
        ),
        HistoricalDialogue(
            dialogue_id="d2",
            case_id="KT002\nKT003",
            turns=[DialogueTurn(speaker="user", text="登录失败")],
        ),
    ]

    assert collect_real_case_ids(dialogues) == ["KT001", "KT002", "KT003"]


def test_split_logs_into_sessions_uses_turn_restart():
    logs = [
        {"timestamp": "2026-01-01T00:00:01Z", "output": {"turn": 1}},
        {"timestamp": "2026-01-01T00:00:02Z", "output": {"turn": 2}},
        {"timestamp": "2026-01-01T00:01:01Z", "output": {"turn": 1}},
        {"timestamp": "2026-01-01T00:01:02Z", "output": {"turn": 2}},
    ]

    sessions = split_logs_into_sessions(logs)

    assert [len(session) for session in sessions] == [2, 2]


def test_load_simulated_sessions_can_select_latest_session(tmp_path: Path):
    output_dir = tmp_path / "outputs"
    for timestamp, turn, reply in [
        ("2026-01-01T00:00:01Z", 1, "第一次开场"),
        ("2026-01-01T00:00:02Z", 2, "第一次结束"),
        ("2026-01-01T00:10:01Z", 1, "第二次开场"),
        ("2026-01-01T00:10:02Z", 2, "第二次结束"),
    ]:
        append_jsonl(
            output_dir / "simulation_logs.jsonl",
            {
                "timestamp": timestamp,
                "case_id": "KT001",
                "module": "Simulator.step",
                "input": {"history_before_reply": [{"role": "user", "content": reply}]},
                "output": {
                    "turn": turn,
                    "user_reply": reply,
                    "state": {"solution_status": "", "stop_reason": ""},
                },
            },
        )

    all_sessions = load_simulated_sessions(output_dir, "KT001", session_policy="all")
    latest_sessions = load_simulated_sessions(output_dir, "KT001", session_policy="latest")
    first_sessions = load_simulated_sessions(output_dir, "KT001", session_policy="first")

    assert len(all_sessions) == 2
    assert len(latest_sessions) == 1
    assert "第二次" in latest_sessions[0]["messages"][0]["content"]
    assert "第一次" in first_sessions[0]["messages"][0]["content"]


def test_behavioral_realism_returns_bounded_score():
    real = [
        extract_features(
            {
                "messages": [
                    {"role": "user", "content": "我的邮箱打不开"},
                    {"role": "assistant", "content": "有什么提示？"},
                    {"role": "user", "content": "提示账号异常"},
                ]
            }
        )
    ]
    simulated = [
        extract_features(
            {
                "messages": [
                    {"role": "user", "content": "邮箱打不开了"},
                    {"role": "assistant", "content": "有什么提示？"},
                    {"role": "user", "content": "显示账号异常"},
                ]
            }
        )
    ]

    result = behavioral_realism(real, simulated)

    assert 0.0 <= result["score"] <= 1.0
    assert 0.0 <= result["user_sim_index"]["score"] <= 1.0


def test_behavioral_realism_includes_low_weight_opening_similarity():
    real_transcripts = [
        {
            "messages": [
                {"role": "user", "content": "Outlook打开后自动退出"},
            ]
        }
    ]
    simulated_transcripts = [
        {
            "messages": [
                {"role": "user", "content": "我这边Outlook一打开就退出来了，帮我看一下"},
            ]
        }
    ]
    real = [extract_features(item) for item in real_transcripts]
    simulated = [extract_features(item) for item in simulated_transcripts]
    opening = opening_similarity_alignment(real_transcripts, simulated_transcripts, build_test_artifact())

    result = behavioral_realism(real, simulated, opening)

    assert 0.0 <= result["opening_similarity_score"] <= 1.0
    assert result["opening_similarity_alignment"]["real_sim_opening_similarity"] > 0.0
    assert result["opening_similarity_alignment"]["real_surface_similarity"] > 0.0
    assert result["opening_similarity_alignment"]["sim_surface_similarity"] > 0.0
    assert result["score_weights"]["opening_similarity"] == 0.10


def test_evaluate_case_can_use_llm_judge(tmp_path: Path):
    real = [
        {
            "case_id": "KT001",
            "messages": [
                {"role": "user", "content": "我的邮箱打不开"},
                {"role": "assistant", "content": "有什么提示？"},
                {"role": "user", "content": "提示账号异常"},
            ],
        }
    ]
    simulated = [
        {
            "case_id": "KT001",
            "messages": [
                {"role": "user", "content": "邮箱打不开了"},
                {"role": "assistant", "content": "有什么提示？"},
                {"role": "user", "content": "显示账号异常"},
            ],
        }
    ]
    evaluator = SimulatorEvaluator(tmp_path, {}, llm_client=MockLLMClient())

    result = evaluator.evaluate_case("KT001", real, simulated, use_judge=True)

    assert result["llm_judge"]["behavioral_realism_score"] == 0.82
    assert result["behavioral_realism"]["llm_judge_score"] == 0.82
    assert result["behavioral_realism"]["score"] != 0.82
    assert result["goal_alignment"]["llm_judge_score"] == 0.9
    assert result["overly_cooperative"]["llm_judge_score"] == 0.7
    assert "trajectory_state" in result
    assert "trajectory_state_score" in result["goal_alignment"]


def test_trajectory_state_detects_wrong_acceptance_without_target_solution():
    simulated = [
        {
            "case_id": "KT001",
            "solution_status": "",
            "stop_reason": "",
            "messages": [
                {"role": "user", "content": "邮箱打不开了"},
                {"role": "assistant", "content": "你可以先重启电脑看看。"},
                {"role": "user", "content": "好的，谢谢。"},
            ],
        }
    ]

    result = trajectory_state_metrics(simulated, None)

    assert result["wrong_acceptance_rate"] == 1.0
    assert result["target_solution_hit_rate"] == 0.0
    assert result["score"] < 1.0


def test_trajectory_state_tracks_action_feedback_use():
    simulated = [
        {
            "case_id": "KT001",
            "solution_status": "",
            "stop_reason": "",
            "messages": [
                {"role": "user", "content": "邮箱打不开了"},
                {"role": "assistant", "content": "你先重启 Outlook 试一下。"},
                {"role": "user", "content": "我试了，还是打不开。"},
            ],
        }
    ]

    result = trajectory_state_metrics(simulated, None)

    assert result["action_feedback_use_rate"] == 1.0
    assert result["repeated_try_without_feedback_rate"] == 0.0
