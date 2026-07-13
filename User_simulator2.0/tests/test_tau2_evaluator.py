import subprocess
import sys
from pathlib import Path

from src.tau2_evaluator import Tau2StyleEvaluator, evaluate_tau2_session
from src.utils.jsonl import append_jsonl


ROOT = Path(__file__).resolve().parents[1]


def test_tau2_session_success_when_target_solution_is_accepted():
    logs = [
        build_log(
            "KT001",
            1,
            assistant_text="请在 Outlook 选项里开启桌面通知。",
            user_reply="好的，我去试试。",
            solution_match="target",
            matched_scope="target_solution",
            matched_point_ids=["S001"],
            solution_status="solution_accepted",
            stop_reason="accepted_actionable_solution",
        )
    ]

    result = evaluate_tau2_session("KT001", 1, logs, None)

    assert result["task_success"] is True
    assert result["assertion_pass"] == 1.0
    assert result["action_matching_score"] == 1.0
    assert result["failure_mode"] == "success"


def test_tau2_session_flags_false_success_when_user_accepts_without_target():
    logs = [
        build_log(
            "KT001",
            1,
            assistant_text="你可以先重启电脑看看。",
            user_reply="好的，谢谢。",
            solution_match="none",
            matched_scope="generic",
            matched_point_ids=[],
            solution_status="not_solved",
            stop_reason=None,
        )
    ]

    result = evaluate_tau2_session("KT001", 1, logs, None)

    assert result["task_success"] is False
    assert result["wrong_acceptance"] is True
    assert result["failure_mode"] == "false_success_or_overcooperation"


def test_tau2_script_writes_summary_and_jsonl(tmp_path):
    output_dir = tmp_path / "outputs"
    append_jsonl(output_dir / "simulation_logs.jsonl", build_log("KT001", 1))

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_tau2_style.py"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    summary = (output_dir / "tau2_eval" / "summary.md").read_text(encoding="utf-8")
    jsonl = (output_dir / "tau2_eval" / "tau2_eval.jsonl").read_text(encoding="utf-8")
    assert "Exported tau2-style evaluation files" in result.stdout
    assert "# Tau2-Style Dual-Control Evaluation Summary" in summary
    assert '"case_id": "KT001"' in jsonl


def test_tau2_evaluator_filters_case_ids(tmp_path):
    output_dir = tmp_path / "outputs"
    append_jsonl(output_dir / "simulation_logs.jsonl", build_log("KT001", 1))
    append_jsonl(output_dir / "simulation_logs.jsonl", build_log("KT002", 1))

    reports = Tau2StyleEvaluator(output_dir).evaluate(["KT002"])

    assert [report["case_id"] for report in reports] == ["KT002"]


def build_log(
    case_id: str,
    turn: int,
    assistant_text: str = "请在 Outlook 选项里开启桌面通知。",
    user_reply: str = "好的，我去试试。",
    solution_match: str = "target",
    matched_scope: str = "target_solution",
    matched_point_ids: list[str] | None = None,
    solution_status: str = "solution_accepted",
    stop_reason: str | None = "accepted_actionable_solution",
) -> dict:
    return {
        "timestamp": f"2026-01-01T00:00:0{turn}Z",
        "case_id": case_id,
        "module": "Simulator.step",
        "input": {
            "assistant_text": assistant_text,
            "history_before_reply": [
                {"role": "user", "content": "Outlook 没有新邮件提醒"},
                {"role": "assistant", "content": assistant_text},
            ],
        },
        "output": {
            "turn": turn,
            "assistant_text": assistant_text,
            "assistant_act": {"assistant_act": "solution_output"},
            "knowledge_assessment": {
                "solution_match": solution_match,
                "matched_scope": matched_scope,
                "matched_point_ids": matched_point_ids or ["S001"],
            },
            "user_action": {
                "user_action": "accept_actionable_solution_and_stop",
                "state_update": {"pending_action_result": False},
            },
            "user_reply": user_reply,
            "state": {
                "solution_status": solution_status,
                "stop_reason": stop_reason,
                "exposed_point_ids": [],
            },
        },
    }
