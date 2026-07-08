from src.llm.mock_llm_client import MockLLMClient
from src.metrics_exporter import MetricsExporter, calculate_rule_metrics
from src.schemas import KnowledgeRoadmapArtifact, RuntimeRoadmap
from src.utils.jsonl import append_jsonl, read_jsonl


def build_artifact():
    return KnowledgeRoadmapArtifact(
        case_id="KT001",
        title="Excel打不开",
        roadmap=RuntimeRoadmap(
            target_case_id="KT001",
            surface_problem="Excel打不开",
            opening_intent="解决Excel打不开",
            user_facing_points=[],
            diagnostic_points=[],
            solution_points=[],
            external_points=[],
            relations=[],
            target_route=[],
            external_routes=[],
            forbidden_content=[],
        ),
    )


def test_calculate_rule_metrics_scores_core_dimensions():
    transcript = {
        "case_id": "KT001",
        "turn_count": 1,
        "stop_reason": "",
        "solution_status": "not_solved",
        "messages": [
            {"role": "user", "content": "Excel打不开"},
            {"role": "assistant", "content": "是所有文件都打不开吗？"},
            {"role": "user", "content": "是的，所有Excel都打不开。"},
        ],
    }

    metrics = calculate_rule_metrics("KT001", transcript, build_artifact())

    assert metrics["answer_alignment_score"] == 1.0
    assert metrics["information_progress_score"] == 1.0
    assert metrics["user_knowledge_boundary_score"] == 1.0
    assert metrics["interaction_realism_score"] == 1.0


def test_metrics_exporter_writes_jsonl_and_summary_with_optional_judge(tmp_path):
    output_dir = tmp_path / "outputs"
    append_jsonl(
        output_dir / "simulation_logs.jsonl",
        {
            "case_id": "KT001",
            "module": "Simulator.step",
            "input": {
                "history_before_reply": [
                    {"role": "user", "content": "Excel打不开"},
                    {"role": "assistant", "content": "是所有文件都打不开吗？"},
                ]
            },
            "output": {
                "turn": 1,
                "user_reply": "是的，所有Excel都打不开。",
                "state": {"solution_status": "not_solved"},
            },
        },
    )

    paths = MetricsExporter(output_dir, {"KT001": build_artifact()}, llm_client=MockLLMClient()).export_case("KT001", use_judge=True)

    assert len(paths) == 2
    records = read_jsonl(output_dir / "metrics" / "simulation_metrics.jsonl")
    assert records[0]["case_id"] == "KT001"
    assert records[0]["llm_judge"]["overall_score"] == 0.8875
    summary = (output_dir / "metrics" / "summary.md").read_text(encoding="utf-8")
    assert "answer_align" in summary
