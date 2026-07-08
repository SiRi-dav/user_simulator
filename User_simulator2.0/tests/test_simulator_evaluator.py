from src.schemas import DialogueTurn, HistoricalDialogue
from src.simulator_evaluator import (
    behavioral_realism,
    collect_real_case_ids,
    extract_features,
    select_real_dialogues,
    split_logs_into_sessions,
)


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
