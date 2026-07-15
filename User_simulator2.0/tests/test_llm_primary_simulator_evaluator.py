from src.llm_primary_simulator_evaluator import (
    build_conditional_pairs,
    build_evidence,
    normalize_judge_payload,
    sample_user_messages,
)


def test_conditional_pairs_extract_user_reaction_only():
    transcript = {
        "case_id": "KT001",
        "messages": [
            {"role": "user", "content": "Outlook 打不开", "turn": 0},
            {"role": "assistant", "content": "请重启 Outlook 后再看一下", "turn": 1},
            {"role": "user", "content": "我试了，还是不行", "turn": 1},
        ],
    }

    pairs = build_conditional_pairs([transcript])

    assert len(pairs) == 1
    assert pairs[0]["assistant_requests_action"] is True
    assert pairs[0]["user_gives_action_feedback"] is True
    assert pairs[0]["user_resists"] is True


def test_user_only_messages_exclude_assistant():
    transcript = {
        "case_id": "KT001",
        "messages": [
            {"role": "user", "content": "Outlook 打不开", "turn": 0},
            {"role": "assistant", "content": "请重启 Outlook", "turn": 1},
            {"role": "user", "content": "还是不行", "turn": 1},
        ],
    }

    messages = sample_user_messages([transcript])

    assert [item["text"] for item in messages] == ["Outlook 打不开", "还是不行"]


def test_build_evidence_marks_wrong_acceptance_as_candidate_only():
    transcript = {
        "case_id": "KT001",
        "messages": [
            {"role": "user", "content": "Outlook 打不开", "turn": 0},
            {"role": "assistant", "content": "你可以先重启电脑试试", "turn": 1},
            {"role": "user", "content": "好的，谢谢", "turn": 1},
        ],
    }

    evidence = build_evidence([], [transcript], artifact=None)

    assert evidence["possible_wrong_acceptance_pairs"]
    assert evidence["note"].startswith("Evidence is heuristic")


def test_normalize_judge_payload_uses_new_default_overall_weighting():
    payload = {
        "conditional_user_behavior_score": 1.0,
        "goal_alignment_score": 0.5,
        "anti_overcooperation_score": 0.5,
        "realsim_behavior_score": 0.5,
        "user_only_discriminability_score": 0.5,
        "leakage_aware_response_score": 0.5,
    }

    result = normalize_judge_payload(payload)

    assert result["overall_score"] == 0.65
    assert result["assistant_failure_confounded"] is False


def test_normalize_judge_payload_calibrates_missing_overall_only():
    payload = {
        "conditional_user_behavior_score": 0.62,
        "goal_alignment_score": 0.62,
        "anti_overcooperation_score": 0.62,
        "realsim_behavior_score": 0.62,
        "user_only_discriminability_score": 0.40,
        "leakage_aware_response_score": 0.40,
    }

    result = normalize_judge_payload(payload)
    explicit = normalize_judge_payload({**payload, "overall_score": 0.52})

    assert result["overall_score"] == 0.60
    assert explicit["overall_score"] == 0.52
