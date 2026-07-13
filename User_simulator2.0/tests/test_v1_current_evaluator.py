import subprocess
import sys
import json
from pathlib import Path

from src.v1_current_evaluator import v1_record_to_transcript


ROOT = Path(__file__).resolve().parents[1]


def test_v1_record_to_transcript_maps_agent_to_assistant():
    record = build_v1_record("KT001", success=True)

    transcript = v1_record_to_transcript(record)

    assert transcript["case_id"] == "KT001"
    assert transcript["solution_status"] == "resolved"
    assert transcript["stop_reason"] == "solution_accepted"
    assert [message["role"] for message in transcript["messages"]] == ["user", "assistant", "user"]
    assert transcript["messages"][1]["content"] == "请提供错误提示。"


def test_evaluate_v1_with_current_metrics_script_writes_outputs(tmp_path):
    output_dir = tmp_path / "outputs"
    dialogues_path = tmp_path / "dialogues.jsonl"
    v1_results_path = tmp_path / "v1_results.jsonl"
    append_jsonl(dialogues_path, build_real_dialogue("KT001"))
    append_jsonl(v1_results_path, build_v1_record("KT001", success=True))

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_v1_with_current_metrics.py"),
            "--v1-results",
            str(v1_results_path),
            "--dialogues",
            str(dialogues_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    summary = (output_dir / "v1_current_eval" / "summary.md").read_text(encoding="utf-8")
    jsonl = (output_dir / "v1_current_eval" / "v1_current_eval.jsonl").read_text(encoding="utf-8")
    assert "Exported v1-current evaluation files" in result.stdout
    assert "# Simulator Evaluation Summary" in summary
    assert "v1_main_branch" in jsonl


def build_v1_record(case_id: str, success: bool = False) -> dict:
    return {
        "dialogue_id": "dialogue_001",
        "target_case_id": case_id,
        "turns": [
            {"role": "user", "turn_id": 1, "text": "邮箱打不开"},
            {
                "role": "agent",
                "turn_id": 1,
                "text": "请提供错误提示。",
                "recommended_case_id": None,
                "action": "ask_clarification",
                "evidence": ["case candidate"],
            },
            {"role": "user", "turn_id": 2, "text": "提示账号异常"},
        ],
        "metrics": {
            "target_case_id": case_id,
            "recommended_case_id": case_id if success else "KT_OTHER",
            "success": success,
            "failure_type": "success" if success else "selection_fail",
            "n_user_turns": 2,
            "n_agent_turns": 1,
            "clarification_count": 1,
            "final_patience": 6,
            "user_end_reason": None,
        },
    }


def build_real_dialogue(case_id: str) -> dict:
    return {
        "dialogue_id": "real_001",
        "case_id": case_id,
        "resolved": True,
        "turns": [
            {"speaker": "user", "text": "邮箱打不开"},
            {"speaker": "assistant", "text": "有什么提示？"},
            {"speaker": "user", "text": "提示账号异常"},
        ],
    }


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
