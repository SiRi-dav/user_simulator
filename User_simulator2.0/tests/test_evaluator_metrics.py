"""
Test cases for enhanced evaluation metrics.

This module tests the new metrics:
1. Opening Realism (initial question quality)
2. Information Rhythm (information release pattern)
"""

from src.evaluator_metrics import (
    calculate_opening_leak_risk,
    calculate_opening_naturalness,
    calculate_text_similarity,
    check_info_accuracy,
    information_rhythm_stats,
    is_question,
    opening_realism_stats,
    tokenize_chinese,
)
from src.schemas import KnowledgeRoadmapArtifact, RuntimePoint, RuntimeRoadmap


def build_test_roadmap():
    """Build a test roadmap for testing."""
    return RuntimeRoadmap(
        target_case_id="KT001",
        surface_problem="Outlook打开后自动退出",
        opening_intent="解决Outlook打开后退出的问题",
        user_facing_points=[
            RuntimePoint(
                point_id="P1",
                content="Outlook打开后自动退出",
                point_type="user_facing",
                trigger=[],
                visibility="opening_available",
            )
        ],
        diagnostic_points=[
            RuntimePoint(
                point_id="P2",
                content="没有显示错误提示",
                point_type="diagnostic",
                trigger=["问错误信息"],
                visibility="ask_triggered",
            ),
            RuntimePoint(
                point_id="P3",
                content="点击Outlook图标后闪退",
                point_type="diagnostic",
                trigger=["问具体现象"],
                visibility="ask_triggered",
            ),
        ],
        solution_points=[
            RuntimePoint(
                point_id="P4",
                content="重新安装Outlook",
                point_type="solution",
                trigger=[],
                visibility="judge_only",
            )
        ],
        external_points=[
            RuntimePoint(
                point_id="P5",
                content="网络连接问题",
                point_type="external",
                trigger=[],
                visibility="external_only",
            )
        ],
        relations=[],
        target_route=["P1", "P2", "P3", "P4"],
        external_routes=[],
        forbidden_content=["重新安装", "修复模式"],
    )


def build_test_artifact():
    """Build a test artifact for testing."""
    return KnowledgeRoadmapArtifact(
        case_id="KT001",
        title="Outlook打开后退出",
        roadmap=build_test_roadmap(),
    )


def test_opening_realism_stats_with_good_opening():
    """Test opening realism with a natural, appropriate opening."""
    transcript = {
        "case_id": "KT001",
        "turn_count": 1,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [
            {"role": "user", "content": "我这边Outlook一打开就退出来了，帮我看一下。"},
        ],
    }

    metrics = opening_realism_stats(transcript, build_test_artifact())

    assert metrics["has_opening"] is True
    assert metrics["surface_semantic_similarity"] > 0.0  # Should have some similarity
    assert metrics["opening_naturalness_score"] > 0.5  # Natural opening
    assert metrics["opening_info_leak_risk"] == 0.0  # No leak
    assert metrics["opening_realism_score"] > 0.3  # Overall acceptable


def test_opening_realism_stats_with_bad_opening():
    """Test opening realism with an unnatural opening."""
    transcript = {
        "case_id": "KT001",
        "turn_count": 1,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [
            {"role": "user", "content": "关于Outlook应用启动过程中出现的异常终止现象，烦请协助诊断。"},
        ],
    }

    metrics = opening_realism_stats(transcript, build_test_artifact())

    assert metrics["has_opening"] is True
    assert metrics["opening_naturalness_score"] <= 0.7  # Too formal (allows equality)
    assert metrics["opening_realism_score"] < 0.9  # Should be lower due to formality


def test_opening_realism_stats_with_leak():
    """Test opening realism with information leak."""
    transcript = {
        "case_id": "KT001",
        "turn_count": 1,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [
            {"role": "user", "content": "我这边Outlook点击图标后闪退了，没有显示错误提示，需要重新安装。"},
        ],
    }

    metrics = opening_realism_stats(transcript, build_test_artifact())

    assert metrics["has_opening"] is True
    assert metrics["opening_info_leak_risk"] > 0.0  # Has leak (diagnostic info)


def test_opening_realism_stats_no_user_message():
    """Test opening realism with no user message."""
    transcript = {
        "case_id": "KT001",
        "turn_count": 0,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [],
    }

    metrics = opening_realism_stats(transcript, build_test_artifact())

    assert metrics["has_opening"] is False
    assert metrics["opening_realism_score"] == 0.0


def test_information_rhythm_stats_good_sequence():
    """Test information rhythm with proper sequence."""
    transcript = {
        "case_id": "KT001",
        "turn_count": 3,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [
            {"role": "user", "content": "我这边Outlook一打开就退出来了，帮我看一下。", "turn": 1},
            {"role": "assistant", "content": "有显示错误提示吗？", "turn": 1},
            {"role": "user", "content": "没有显示错误提示。", "turn": 2},
            {"role": "assistant", "content": "是点击图标后就闪退吗？", "turn": 2},
            {"role": "user", "content": "是的，点击图标后就闪退。", "turn": 3},
        ],
    }

    metrics = information_rhythm_stats(transcript, build_test_artifact())

    assert metrics["premature_diagnostic_rate"] < 0.5  # Diagnostic info after questions
    assert metrics["info_release_timing_score"] > 0.5  # Good timing
    assert metrics["information_rhythm_score"] > 0.5  # Overall good


def test_information_rhythm_stats_premature_leak():
    """Test information rhythm with premature diagnostic info."""
    transcript = {
        "case_id": "KT001",
        "turn_count": 2,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [
            {"role": "user", "content": "我这边Outlook点击后闪退了，没有显示错误提示。", "turn": 1},
            {"role": "assistant", "content": "请问是什么具体现象？", "turn": 1},
            {"role": "user", "content": "就是打不开。", "turn": 2},
        ],
    }

    metrics = information_rhythm_stats(transcript, build_test_artifact())

    assert metrics["premature_diagnostic_rate"] > 0.0  # Diagnostic info in first message
    assert metrics["information_rhythm_score"] < 0.8  # Penalized for premature leak


def test_information_rhythm_stats_no_artifact():
    """Test information rhythm with no artifact."""
    transcript = {
        "case_id": "KT001",
        "turn_count": 1,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [
            {"role": "user", "content": "我这边Outlook一打开就退出来了，帮我看一下。"},
        ],
    }

    metrics = information_rhythm_stats(transcript, None)

    assert metrics["premature_diagnostic_rate"] == 0.0
    assert metrics["information_rhythm_score"] == 0.0


def test_calculate_text_similarity():
    """Test text similarity calculation."""
    sim1 = calculate_text_similarity("Outlook打不开", "Outlook打开后自动退出")
    assert sim1 > 0.0  # Should have some overlap

    sim2 = calculate_text_similarity("Excel有问题", "Outlook打不开")
    assert sim2 < sim1  # Should have less overlap than the first pair

    sim3 = calculate_text_similarity("", "Outlook打不开")
    assert sim3 == 0.0  # Empty text


def test_tokenize_chinese():
    """Test Chinese tokenization."""
    tokens = tokenize_chinese("Outlook打开后退出")
    assert "打开" in tokens or "打开后" in tokens or "outlook" in tokens
    assert len(tokens) > 0


def test_calculate_opening_naturalness():
    """Test opening naturalness calculation."""
    # Natural opening
    natural_score = calculate_opening_naturalness("我这边Outlook打不开，帮我看一下")
    assert natural_score > 0.5

    # Too long - should be penalized but still may be reasonable if it has natural markers
    long_opening = "我这边" + "很着急" * 50 + "Outlook打不开"
    long_score = calculate_opening_naturalness(long_opening)
    # Long text gets penalty but may still score decent due to natural markers
    assert long_score < natural_score  # Should be lower than natural opening

    # Too formal - should be penalized
    formal_score = calculate_opening_naturalness("烦请协助诊断Outlook异常终止现象")
    assert formal_score < natural_score  # Should be lower than natural opening


def test_calculate_opening_leak_risk():
    """Test opening leak risk calculation."""
    # No leak
    no_leak = calculate_opening_leak_risk("Outlook打不开", build_test_artifact())
    assert no_leak == 0.0

    # Diagnostic leak
    diag_leak = calculate_opening_leak_risk("Outlook没有显示错误提示", build_test_artifact())
    assert diag_leak > 0.0

    # Solution leak (critical)
    solution_leak = calculate_opening_leak_risk("需要重新安装Outlook", build_test_artifact())
    assert solution_leak == 1.0


def test_is_question():
    """Test question detection."""
    assert is_question("是打不开吗？") is True
    assert is_question("有没有错误提示") is True
    assert is_question("请问是什么问题") is True
    assert is_question("我这边打不开") is False


def test_check_info_accuracy():
    """Test info accuracy checking."""
    roadmap = build_test_roadmap()

    # Accurate match
    acc1 = check_info_accuracy("Outlook打开后自动退出", roadmap)
    assert acc1 > 0.0

    # No match
    acc2 = check_info_accuracy("Excel有问题", roadmap)
    assert acc2 == 0.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
