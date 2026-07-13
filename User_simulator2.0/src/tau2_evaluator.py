from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from src.review_exporter import safe_filename
from src.schemas import KnowledgeRoadmapArtifact
from src.simulator_evaluator import (
    classify_user_act,
    text_contains_content_loose,
    transcript_solution_accepted,
    weighted_average,
)
from src.transcript_exporter import build_transcript, read_simulation_logs, split_logs_into_sessions
from src.utils.jsonl import read_jsonl, write_jsonl


def evaluate_tau2_style(
    output_dir: Path,
    case_ids: Iterable[str] | None = None,
) -> list[Path]:
    evaluator = Tau2StyleEvaluator(output_dir)
    reports = evaluator.evaluate(case_ids)
    return evaluator.write_outputs(reports)


class Tau2StyleEvaluator:
    """Tau2-bench-style proxy evaluation for our IT-support simulator.

    tau2-bench uses a verifiable dual-control environment. We do not have a real
    device/database backend, so this module maps the same evaluation structure to
    our available proxy state: roadmap assertions, knowledge assessments,
    simulator state, and action-execution feedback in the conversation history.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.eval_dir = output_dir / "tau2_eval"
        self.knowledge_artifacts = load_knowledge_artifacts(output_dir / "knowledge_roadmaps.jsonl")

    def evaluate(self, case_ids: Iterable[str] | None = None) -> list[Dict[str, Any]]:
        selected = set(case_ids or [])
        logs_by_case: dict[str, list[Dict[str, Any]]] = {}
        for record in read_simulation_logs(self.output_dir / "simulation_logs.jsonl"):
            case_id = str(record.get("case_id") or "")
            if selected and case_id not in selected:
                continue
            logs_by_case.setdefault(case_id, []).append(record)
        if selected:
            missing = sorted(selected - set(logs_by_case))
            if missing:
                raise ValueError(f"case_id not found in simulation_logs.jsonl: {', '.join(missing)}")
        if not logs_by_case:
            raise ValueError(f"No simulation logs found: {self.output_dir / 'simulation_logs.jsonl'}")

        reports: list[Dict[str, Any]] = []
        for case_id in sorted(logs_by_case):
            sessions = split_logs_into_sessions(logs_by_case[case_id])
            artifact = self.knowledge_artifacts.get(case_id)
            session_reports = [
                evaluate_tau2_session(case_id, session_index, session, artifact)
                for session_index, session in enumerate(sessions, 1)
            ]
            reports.append(summarize_tau2_case(case_id, session_reports, artifact))
        return reports

    def write_outputs(self, reports: list[Dict[str, Any]]) -> list[Path]:
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = self.eval_dir / "tau2_eval.jsonl"
        md_path = self.eval_dir / "summary.md"
        write_jsonl(jsonl_path, reports)
        md_path.write_text(render_tau2_summary(reports), encoding="utf-8")
        for report in reports:
            case_path = self.eval_dir / f"{safe_filename(report['case_id'])}.md"
            case_path.write_text(render_tau2_case(report), encoding="utf-8")
        return [jsonl_path, md_path]


def evaluate_tau2_session(
    case_id: str,
    session_index: int,
    logs: list[Dict[str, Any]],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    transcript = build_transcript(case_id, logs)
    messages = transcript.get("messages") or []
    user_texts = [str(item.get("content") or "") for item in messages if item.get("role") == "user"]
    assistant_texts = [str(item.get("content") or "") for item in messages if item.get("role") == "assistant"]

    matched_point_ids = collect_matched_point_ids(logs)
    final_state = ((logs[-1].get("output") or {}).get("state") or {}) if logs else {}
    solution_match_target = any(
        ((record.get("output") or {}).get("knowledge_assessment") or {}).get("solution_match") == "target"
        or ((record.get("output") or {}).get("knowledge_assessment") or {}).get("matched_scope") == "target_solution"
        for record in logs
    )
    accepted_target = transcript_solution_accepted(transcript) or final_state.get("stop_reason") in {
        "accepted_actionable_solution",
        "solution_accepted",
    }

    action_requests = count_action_requests(logs)
    action_feedback_turns = sum(1 for text in user_texts if classify_user_act(text) == "action_feedback")
    repeated_try_without_feedback = has_repeated_try_without_feedback(user_texts)
    leakage = detect_user_leakage(user_texts, artifact)
    wrong_acceptance = has_acceptance_without_target(user_texts, solution_match_target, accepted_target)

    assertion_pass = 1.0 if (solution_match_target and accepted_target and not leakage) else 0.0
    action_match_score = action_matching_score(matched_point_ids, artifact, solution_match_target)
    communication_info_score = communication_info_score_from_logs(logs, artifact)
    natural_language_assertion_score = 1.0 if solution_match_target else action_match_score
    dual_control_score = dual_control_coordination_score(action_requests, action_feedback_turns, repeated_try_without_feedback)
    task_success = bool(assertion_pass and action_match_score > 0 and not wrong_acceptance)
    reward = weighted_average(
        {
            "assertion": assertion_pass,
            "action_matching": action_match_score,
            "communication_info": communication_info_score,
            "dual_control": dual_control_score,
        },
        {"assertion": 0.40, "action_matching": 0.25, "communication_info": 0.15, "dual_control": 0.20},
    )

    return {
        "session_id": f"{case_id}#{session_index}",
        "session_index": session_index,
        "turn_count": transcript.get("turn_count", len(logs)),
        "task_success": task_success,
        "reward": round(reward, 3),
        "assertion_pass": round(assertion_pass, 3),
        "action_matching_score": round(action_match_score, 3),
        "natural_language_assertion_score": round(natural_language_assertion_score, 3),
        "communication_info_score": round(communication_info_score, 3),
        "dual_control_coordination_score": round(dual_control_score, 3),
        "target_solution_hit": bool(solution_match_target),
        "accepted_target": bool(accepted_target),
        "wrong_acceptance": bool(wrong_acceptance),
        "knowledge_leakage": bool(leakage),
        "action_request_count": action_requests,
        "action_feedback_turns": action_feedback_turns,
        "repeated_try_without_feedback": bool(repeated_try_without_feedback),
        "failure_mode": classify_tau2_failure(
            task_success=task_success,
            target_solution_hit=bool(solution_match_target),
            accepted_target=bool(accepted_target),
            wrong_acceptance=bool(wrong_acceptance),
            leakage=bool(leakage),
            action_requests=action_requests,
            action_feedback_turns=action_feedback_turns,
            repeated_try_without_feedback=bool(repeated_try_without_feedback),
        ),
        "matched_point_ids": sorted(matched_point_ids),
        "assistant_messages": assistant_texts[:8],
        "user_messages": user_texts[:8],
    }


def summarize_tau2_case(
    case_id: str,
    session_reports: list[Dict[str, Any]],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    success_values = [1.0 if item["task_success"] else 0.0 for item in session_reports]
    rewards = [float(item["reward"]) for item in session_reports]
    failure_modes: dict[str, int] = {}
    for item in session_reports:
        failure_modes[str(item["failure_mode"])] = failure_modes.get(str(item["failure_mode"]), 0) + 1
    return {
        "case_id": case_id,
        "session_count": len(session_reports),
        "pass_hat_1": round(mean(success_values), 3),
        "pass_hat_k_all": bool(session_reports) and all(item["task_success"] for item in session_reports),
        "avg_reward": round(mean(rewards), 3),
        "avg_assertion_pass": round(mean([item["assertion_pass"] for item in session_reports]), 3),
        "avg_action_matching_score": round(mean([item["action_matching_score"] for item in session_reports]), 3),
        "avg_communication_info_score": round(mean([item["communication_info_score"] for item in session_reports]), 3),
        "avg_dual_control_coordination_score": round(
            mean([item["dual_control_coordination_score"] for item in session_reports]), 3
        ),
        "failure_modes": failure_modes,
        "target_route": list(artifact.roadmap.target_route) if artifact else [],
        "solution_point_ids": [point.point_id for point in artifact.roadmap.solution_points] if artifact else [],
        "sessions": session_reports,
    }


def collect_matched_point_ids(logs: list[Dict[str, Any]]) -> set[str]:
    matched: set[str] = set()
    for record in logs:
        output = record.get("output") or {}
        assessment = output.get("knowledge_assessment") or {}
        for point_id in assessment.get("matched_point_ids") or []:
            matched.add(str(point_id))
        state = output.get("state") or {}
        for point_id in state.get("exposed_point_ids") or []:
            matched.add(str(point_id))
    return matched


def count_action_requests(logs: list[Dict[str, Any]]) -> int:
    count = 0
    for record in logs:
        output = record.get("output") or {}
        assistant_act = output.get("assistant_act") or {}
        user_action = output.get("user_action") or {}
        if assistant_act.get("assistant_act") == "action_request":
            count += 1
        if user_action.get("state_update", {}).get("pending_action_result"):
            count += 1
    return count


def action_matching_score(
    matched_point_ids: set[str],
    artifact: KnowledgeRoadmapArtifact | None,
    solution_match_target: bool,
) -> float:
    if artifact is None:
        return 1.0 if solution_match_target else 0.0
    solution_ids = {point.point_id for point in artifact.roadmap.solution_points}
    if solution_match_target:
        return 1.0
    if not solution_ids:
        return 0.0
    return len(solution_ids & matched_point_ids) / len(solution_ids)


def communication_info_score_from_logs(logs: list[Dict[str, Any]], artifact: KnowledgeRoadmapArtifact | None) -> float:
    if artifact is None:
        return 1.0
    required_ids = {
        point_id
        for point_id in artifact.roadmap.target_route
        if point_id not in {point.point_id for point in artifact.roadmap.solution_points}
    }
    if not required_ids:
        return 1.0
    exposed_ids: set[str] = set()
    for record in logs:
        state = ((record.get("output") or {}).get("state") or {})
        exposed_ids.update(str(point_id) for point_id in state.get("exposed_point_ids") or [])
    return len(required_ids & exposed_ids) / len(required_ids)


def dual_control_coordination_score(
    action_requests: int,
    action_feedback_turns: int,
    repeated_try_without_feedback: bool,
) -> float:
    if action_requests <= 0:
        return 1.0
    feedback_score = min(1.0, action_feedback_turns / action_requests)
    repeat_penalty = 0.5 if repeated_try_without_feedback else 0.0
    return max(0.0, feedback_score - repeat_penalty)


def detect_user_leakage(user_texts: list[str], artifact: KnowledgeRoadmapArtifact | None) -> bool:
    if artifact is None:
        return False
    joined = "\n".join(user_texts)
    forbidden = list(artifact.roadmap.forbidden_content)
    forbidden.extend(point.content for point in artifact.roadmap.solution_points)
    return any(text_contains_content_loose(joined, content) for content in forbidden)


def has_acceptance_without_target(user_texts: list[str], solution_match_target: bool, accepted_target: bool) -> bool:
    if solution_match_target or accepted_target:
        return False
    return any(any(marker in text for marker in ("好的", "可以", "行", "谢谢", "感谢")) for text in user_texts)


def has_repeated_try_without_feedback(user_texts: list[str]) -> bool:
    try_like = [text for text in user_texts if "试" in text or "操作" in text or "按" in text]
    feedback_like = [text for text in user_texts if classify_user_act(text) == "action_feedback"]
    return len(try_like) >= 2 and not feedback_like


def classify_tau2_failure(
    *,
    task_success: bool,
    target_solution_hit: bool,
    accepted_target: bool,
    wrong_acceptance: bool,
    leakage: bool,
    action_requests: int,
    action_feedback_turns: int,
    repeated_try_without_feedback: bool,
) -> str:
    if task_success:
        return "success"
    if leakage:
        return "user_simulator_leakage"
    if wrong_acceptance:
        return "false_success_or_overcooperation"
    if target_solution_hit and not accepted_target:
        return "termination_or_acceptance_failure"
    if action_requests and not action_feedback_turns:
        return "dual_control_coordination_failure"
    if repeated_try_without_feedback:
        return "action_feedback_failure"
    if not target_solution_hit:
        return "assistant_reasoning_or_retrieval_failure"
    return "unknown_failure"


def load_knowledge_artifacts(path: Path) -> dict[str, KnowledgeRoadmapArtifact]:
    if not path.exists():
        return {}
    artifacts: dict[str, KnowledgeRoadmapArtifact] = {}
    for record in read_jsonl(path):
        artifact = KnowledgeRoadmapArtifact(**record)
        artifacts[artifact.case_id] = artifact
    return artifacts


def render_tau2_summary(reports: list[Dict[str, Any]]) -> str:
    lines = [
        "# Tau2-Style Dual-Control Evaluation Summary",
        "",
        "This report maps tau2-bench evaluation ideas to the IT-support simulator: proxy world state, action matching, natural-language assertions, communication information, dual-control coordination, and pass^k-style reliability.",
        "",
        "| case_id | sessions | pass^1 | pass^k_all | reward | assertion | action_match | comm_info | dual_control | main_failure_modes |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for report in reports:
        lines.append(
            "| {case_id} | {sessions} | {pass1:.3f} | {passk} | {reward:.3f} | {assertion:.3f} | {action:.3f} | {comm:.3f} | {dual:.3f} | {failures} |".format(
                case_id=report["case_id"],
                sessions=report["session_count"],
                pass1=report["pass_hat_1"],
                passk="yes" if report["pass_hat_k_all"] else "no",
                reward=report["avg_reward"],
                assertion=report["avg_assertion_pass"],
                action=report["avg_action_matching_score"],
                comm=report["avg_communication_info_score"],
                dual=report["avg_dual_control_coordination_score"],
                failures=format_failure_modes(report.get("failure_modes", {})),
            )
        )
    lines.extend(
        [
            "",
            "## Metric Mapping",
            "",
            "- `pass_hat_1`: fraction of simulated sessions that satisfy proxy success assertions.",
            "- `pass_hat_k_all`: whether all sessions for the case succeed, mirroring reliability-over-repeated-runs.",
            "- `assertion_pass`: final proxy state success, based on target solution hit + acceptance + no leakage.",
            "- `action_matching_score`: whether target solution actions/points appear in the trajectory.",
            "- `communication_info_score`: whether required target-route user information was elicited.",
            "- `dual_control_coordination_score`: whether assistant-requested user actions produced observable feedback.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_tau2_case(report: Dict[str, Any]) -> str:
    lines = [
        f"# Tau2-Style Evaluation {report['case_id']}",
        "",
        f"- session_count: {report['session_count']}",
        f"- pass_hat_1: {report['pass_hat_1']:.3f}",
        f"- pass_hat_k_all: {report['pass_hat_k_all']}",
        f"- avg_reward: {report['avg_reward']:.3f}",
        f"- avg_assertion_pass: {report['avg_assertion_pass']:.3f}",
        f"- avg_action_matching_score: {report['avg_action_matching_score']:.3f}",
        f"- avg_communication_info_score: {report['avg_communication_info_score']:.3f}",
        f"- avg_dual_control_coordination_score: {report['avg_dual_control_coordination_score']:.3f}",
        f"- failure_modes: {format_failure_modes(report.get('failure_modes', {}))}",
        "",
        "## Sessions",
        "",
    ]
    for session in report.get("sessions", []):
        lines.extend(
            [
                f"### {session['session_id']}",
                "",
                f"- task_success: {session['task_success']}",
                f"- reward: {session['reward']:.3f}",
                f"- assertion_pass: {session['assertion_pass']:.3f}",
                f"- action_matching_score: {session['action_matching_score']:.3f}",
                f"- communication_info_score: {session['communication_info_score']:.3f}",
                f"- dual_control_coordination_score: {session['dual_control_coordination_score']:.3f}",
                f"- target_solution_hit: {session['target_solution_hit']}",
                f"- accepted_target: {session['accepted_target']}",
                f"- wrong_acceptance: {session['wrong_acceptance']}",
                f"- knowledge_leakage: {session['knowledge_leakage']}",
                f"- action_request_count: {session['action_request_count']}",
                f"- action_feedback_turns: {session['action_feedback_turns']}",
                f"- failure_mode: {session['failure_mode']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def format_failure_modes(failure_modes: Dict[str, int]) -> str:
    if not failure_modes:
        return ""
    return ", ".join(f"{key}:{value}" for key, value in sorted(failure_modes.items()))


def mean(values: Iterable[float]) -> float:
    values_list = [float(value) for value in values]
    return sum(values_list) / len(values_list) if values_list else 0.0

