import subprocess
import sys
from pathlib import Path

from src.utils.jsonl import append_jsonl


ROOT = Path(__file__).resolve().parents[1]


def test_export_combined_eval_script_writes_markdown_and_json(tmp_path):
    output_dir = tmp_path / "outputs"
    append_jsonl(output_dir / "simulator_eval" / "simulator_eval.jsonl", build_eval_record("KT001"))

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_combined_eval.py"),
            "--output-dir",
            str(output_dir),
            "--output",
            "combined_eval",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    md_text = (output_dir / "simulator_eval" / "combined_eval.md").read_text(encoding="utf-8")
    json_text = (output_dir / "simulator_eval" / "combined_eval.json").read_text(encoding="utf-8")
    assert "Exported combined evaluation files" in result.stdout
    assert "# Simulator Evaluation Summary" in md_text
    assert "# Simulator Evaluation KT001" in md_text
    assert '"case_id": "KT001"' in json_text


def test_export_combined_roadmaps_script_writes_markdown_and_json(tmp_path):
    output_dir = tmp_path / "outputs"
    append_jsonl(output_dir / "knowledge_roadmaps.jsonl", build_roadmap_record("KT001"))

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_combined_roadmaps.py"),
            "--output-dir",
            str(output_dir),
            "--output",
            "combined_roadmaps",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    md_text = (output_dir / "review" / "combined_roadmaps.md").read_text(encoding="utf-8")
    json_text = (output_dir / "review" / "combined_roadmaps.json").read_text(encoding="utf-8")
    assert "Exported combined roadmap files" in result.stdout
    assert "# All Knowledge Roadmaps" in md_text
    assert "# KT001 测试案例" in md_text
    assert '"case_id": "KT001"' in json_text


def build_eval_record(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "real_session_count": 1,
        "simulated_session_count": 1,
        "overall_score": 0.8,
        "behavioral_realism": {
            "score": 0.8,
            "dialogue_act_jsd": 0.1,
            "session_length_wasserstein": 0.0,
            "words_per_turn_wasserstein": 0.0,
            "user_sim_index": {"score": 0.8},
        },
        "goal_alignment": {
            "score": 0.9,
            "goal_persistence_score": 1.0,
            "knowledge_boundary_score": 1.0,
            "simulated_solved_rate": 0.7,
        },
        "overly_cooperative": {
            "score": 0.7,
            "real_accept_rate": 0.2,
            "simulated_accept_rate": 0.3,
            "real_resistance_rate": 0.5,
            "simulated_resistance_rate": 0.4,
        },
        "enhanced_evaluation": {"opening_realism_score": 0.8, "information_rhythm_score": 0.7},
        "real_feature_summary": {},
        "simulated_feature_summary": {},
    }


def build_roadmap_record(case_id: str) -> dict:
    return {
        "case_id": case_id,
        "title": "测试案例",
        "roadmap": {
            "target_case_id": case_id,
            "surface_problem": "Outlook 没有通知",
            "opening_intent": "希望恢复邮件通知",
            "user_facing_points": [],
            "diagnostic_points": [],
            "solution_points": [
                {
                    "point_id": "S001",
                    "content": "开启 Outlook 桌面通知",
                    "point_type": "solution",
                    "trigger": [],
                    "visibility": "judge_only",
                }
            ],
            "external_points": [],
            "relations": [],
            "target_route": ["S001"],
            "external_routes": [],
            "forbidden_content": [],
        },
    }
