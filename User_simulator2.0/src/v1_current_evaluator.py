from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable


def evaluate_v1_outputs_with_current_metrics(
    v1_results_path: Path,
    real_dialogues_path: Path,
    output_dir: Path,
    case_ids: Iterable[str] | None = None,
) -> list[Path]:
    evaluator = V1CurrentMetricsEvaluator(
        v1_results_path=v1_results_path,
        real_dialogues_path=real_dialogues_path,
        output_dir=output_dir,
    )
    reports = evaluator.evaluate(case_ids=case_ids)
    return evaluator.write_outputs(reports)


class V1CurrentMetricsEvaluator:
    """Evaluate User Simulator 1.0 outputs with the current metric shape.

    This module is intentionally self-contained so it can live on the original
    main branch, where the User Simulator 2.0 evaluator package does not exist.
    It keeps the same output style: per-case JSONL plus a readable summary.
    """

    def __init__(self, v1_results_path: Path, real_dialogues_path: Path, output_dir: Path):
        self.v1_results_path = v1_results_path
        self.real_dialogues_path = real_dialogues_path
        self.output_dir = output_dir
        self.eval_dir = output_dir / "v1_current_eval"

    def evaluate(self, case_ids: Iterable[str] | None = None) -> list[Dict[str, Any]]:
        selected = set(case_ids or [])
        real_dialogues = load_dialogues(self.real_dialogues_path)
        real_by_case = group_real_dialogues_by_case(real_dialogues)
        v1_records = read_jsonl(self.v1_results_path)

        reports: list[Dict[str, Any]] = []
        for index, record in enumerate(v1_records, 1):
            transcript = v1_record_to_transcript(record, index)
            case_id = str(transcript.get("case_id") or "")
            if not case_id or (selected and case_id not in selected):
                continue
            real_transcripts = real_by_case.get(case_id, [])
            if not real_transcripts:
                raise ValueError(f"No real dialogues found for case_id: {case_id}")
            reports.append(evaluate_case(case_id, real_transcripts, transcript, record))

        if selected:
            found = {report["case_id"] for report in reports}
            missing = sorted(selected - found)
            if missing:
                raise ValueError(f"case_id not found in v1 results: {', '.join(missing)}")
        if not reports:
            raise ValueError(f"No v1 simulation records found: {self.v1_results_path}")
        return reports

    def write_outputs(self, reports: list[Dict[str, Any]]) -> list[Path]:
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = self.eval_dir / "v1_current_eval.jsonl"
        md_path = self.eval_dir / "summary.md"
        write_jsonl(jsonl_path, reports)
        md_path.write_text(render_v1_current_summary(reports), encoding="utf-8")
        for report in reports:
            case_path = self.eval_dir / f"{safe_filename(report['case_id'])}.md"
            case_path.write_text(render_case_report(report), encoding="utf-8")
        return [jsonl_path, md_path]


def evaluate_case(
    case_id: str,
    real_transcripts: list[Dict[str, Any]],
    sim_transcript: Dict[str, Any],
    raw_record: Dict[str, Any],
) -> Dict[str, Any]:
    real_profile = aggregate_profile(real_transcripts)
    sim_profile = transcript_profile(sim_transcript)
    metrics = raw_record.get("metrics") or sim_transcript.get("v1_metrics") or {}

    behavior_score = behavior_realism_score(real_profile, sim_profile)
    goal_score = goal_alignment_score(metrics, sim_transcript)
    cooperation_score = overly_cooperative_score(sim_transcript, metrics)
    overall = round((behavior_score + goal_score + cooperation_score) / 3, 4)

    return {
        "case_id": case_id,
        "evaluated_simulator_version": "v1_main_branch",
        "overall_score": overall,
        "scores": {
            "behavioral_realism": behavior_score,
            "goal_alignment": goal_score,
            "overly_cooperative_resistance": cooperation_score,
        },
        "real_profile": real_profile,
        "sim_profile": sim_profile,
        "v1_metrics": metrics,
        "simulation": sim_transcript,
    }


def v1_record_to_transcript(record: Dict[str, Any], index: int = 1) -> Dict[str, Any]:
    turns = record.get("turns") or record.get("dialogue_log") or []
    messages: list[Dict[str, Any]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = normalize_v1_role(turn.get("role"))
        text = str(turn.get("text") or turn.get("utterance") or turn.get("response") or "").strip()
        if not role or not text:
            continue
        messages.append(
            {
                "role": role,
                "content": text,
                "turn": int(turn.get("turn_id") or len(messages) + 1),
            }
        )
    metrics = record.get("metrics") or {}
    target_case_id = record.get("target_case_id") or metrics.get("target_case_id") or record.get("case_id") or ""
    success = bool(metrics.get("success"))
    return {
        "case_id": str(target_case_id),
        "dialogue_id": str(record.get("dialogue_id") or f"v1_sim_{index:06d}"),
        "turn_count": len(messages),
        "solution_status": "resolved" if success else "",
        "stop_reason": "solution_accepted" if success else str(metrics.get("failure_type") or ""),
        "messages": messages,
        "v1_metrics": metrics,
    }


def normalize_v1_role(role: Any) -> str:
    text = str(role or "").strip().lower()
    if text == "user":
        return "user"
    if text in {"agent", "assistant", "system"}:
        return "assistant"
    return ""


def load_dialogues(path: Path) -> list[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return normalize_dialogue_dict(payload)
    return []


def normalize_dialogue_dict(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        case_ids = value.get("caseId") or value.get("case_id") or []
        case_id = ""
        if isinstance(case_ids, list) and case_ids:
            case_id = str(case_ids[0])
        elif case_ids:
            case_id = str(case_ids)
        rows.append(
            {
                "dialogue_id": str(key),
                "case_id": case_id,
                "turns": value.get("text") or value.get("turns") or [],
            }
        )
    return rows


def group_real_dialogues_by_case(dialogues: list[Dict[str, Any]]) -> dict[str, list[Dict[str, Any]]]:
    grouped: dict[str, list[Dict[str, Any]]] = {}
    for index, dialogue in enumerate(dialogues, 1):
        transcript = real_dialogue_to_transcript(dialogue, index)
        case_id = transcript.get("case_id")
        if case_id:
            grouped.setdefault(str(case_id), []).append(transcript)
    return grouped


def real_dialogue_to_transcript(dialogue: Dict[str, Any], index: int) -> Dict[str, Any]:
    case_id = dialogue.get("case_id") or dialogue.get("caseId") or ""
    if isinstance(case_id, list):
        case_id = case_id[0] if case_id else ""
    messages: list[Dict[str, Any]] = []
    turns = dialogue.get("turns") or dialogue.get("text") or []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = normalize_real_role(turn.get("role") or turn.get("speaker") or first_key(turn))
        text = extract_turn_text(turn)
        if role and text:
            messages.append({"role": role, "content": text, "turn": len(messages) + 1})
    return {
        "case_id": str(case_id),
        "dialogue_id": str(dialogue.get("dialogue_id") or dialogue.get("id") or f"real_{index:06d}"),
        "messages": messages,
        "turn_count": len(messages),
    }


def normalize_real_role(role: Any) -> str:
    text = str(role or "").strip().lower()
    if text in {"user", "用户", "customer"}:
        return "user"
    if text in {"assistant", "agent", "客服", "system"}:
        return "assistant"
    return ""


def first_key(obj: Dict[str, Any]) -> str:
    return next(iter(obj.keys()), "")


def extract_turn_text(turn: Dict[str, Any]) -> str:
    for key in ("text", "content", "utterance", "response", "用户", "客服"):
        if key in turn:
            return str(turn.get(key) or "").strip()
    if len(turn) == 1:
        return str(next(iter(turn.values())) or "").strip()
    return ""


def aggregate_profile(transcripts: list[Dict[str, Any]]) -> Dict[str, Any]:
    profiles = [transcript_profile(transcript) for transcript in transcripts]
    if not profiles:
        return {}
    return {
        "turn_count": mean(profile["turn_count"] for profile in profiles),
        "user_turn_count": mean(profile["user_turn_count"] for profile in profiles),
        "assistant_turn_count": mean(profile["assistant_turn_count"] for profile in profiles),
        "avg_user_chars": mean(profile["avg_user_chars"] for profile in profiles),
        "question_rate": mean(profile["question_rate"] for profile in profiles),
        "friction_rate": mean(profile["friction_rate"] for profile in profiles),
        "acceptance_rate": mean(profile["acceptance_rate"] for profile in profiles),
        "dialogue_act_distribution": average_distribution(
            [profile["dialogue_act_distribution"] for profile in profiles]
        ),
    }


def transcript_profile(transcript: Dict[str, Any]) -> Dict[str, Any]:
    messages = transcript.get("messages") or []
    user_messages = [message for message in messages if message.get("role") == "user"]
    assistant_messages = [message for message in messages if message.get("role") == "assistant"]
    user_texts = [str(message.get("content") or "") for message in user_messages]
    act_counts = Counter(classify_user_act(text) for text in user_texts)
    return {
        "turn_count": len(messages),
        "user_turn_count": len(user_messages),
        "assistant_turn_count": len(assistant_messages),
        "avg_user_chars": mean(len(text) for text in user_texts),
        "question_rate": ratio(sum(contains_question(text) for text in user_texts), len(user_texts)),
        "friction_rate": ratio(sum(has_friction(text) for text in user_texts), len(user_texts)),
        "acceptance_rate": ratio(sum(is_acceptance(text) for text in user_texts), len(user_texts)),
        "dialogue_act_distribution": normalize_counts(act_counts),
    }


def behavior_realism_score(real_profile: Dict[str, Any], sim_profile: Dict[str, Any]) -> float:
    if not real_profile:
        return 0.0
    parts = [
        closeness(sim_profile["turn_count"], real_profile["turn_count"]),
        closeness(sim_profile["avg_user_chars"], real_profile["avg_user_chars"]),
        closeness(sim_profile["question_rate"], real_profile["question_rate"], scale=1.0),
        1.0 - distribution_distance(
            sim_profile["dialogue_act_distribution"],
            real_profile["dialogue_act_distribution"],
        ),
    ]
    return round(max(0.0, min(1.0, mean(parts))), 4)


def goal_alignment_score(metrics: Dict[str, Any], transcript: Dict[str, Any]) -> float:
    if metrics.get("success") or transcript.get("solution_status") == "resolved":
        return 1.0
    failure_type = str(metrics.get("failure_type") or transcript.get("stop_reason") or "")
    if failure_type in {"selection_fail", "retrieval_fail", "answer_fail"}:
        return 0.35
    if failure_type in {"timeout", "user_gave_up", "over_clarification"}:
        return 0.2
    return 0.5


def overly_cooperative_score(transcript: Dict[str, Any], metrics: Dict[str, Any]) -> float:
    profile = transcript_profile(transcript)
    score = 0.55
    if profile["question_rate"] > 0:
        score += 0.15
    if profile["friction_rate"] > 0:
        score += 0.2
    if profile["acceptance_rate"] > 0.35 and not metrics.get("success"):
        score -= 0.2
    if int(metrics.get("clarification_count") or 0) >= 3 and profile["friction_rate"] == 0:
        score -= 0.15
    return round(max(0.0, min(1.0, score)), 4)


def classify_user_act(text: str) -> str:
    if is_acceptance(text):
        return "accept"
    if has_friction(text):
        return "friction"
    if contains_question(text):
        return "clarify"
    return "inform"


def contains_question(text: str) -> bool:
    return "?" in text or "？" in text or any(word in text for word in ("怎么", "如何", "为什么", "是否", "吗"))


def has_friction(text: str) -> bool:
    return any(word in text for word in ("不行", "没用", "还是", "无法", "不会", "不懂", "太麻烦", "不清楚", "解决不了"))


def is_acceptance(text: str) -> bool:
    return any(word in text for word in ("好的", "谢谢", "可以", "明白", "我去试", "已解决", "没问题"))


def closeness(value: float, target: float, scale: float | None = None) -> float:
    if target == 0:
        return 1.0 if value == 0 else 0.0
    normalizer = scale if scale is not None else max(abs(target), 1.0)
    return max(0.0, 1.0 - abs(value - target) / normalizer)


def distribution_distance(left: Dict[str, float], right: Dict[str, float]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    return sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys) / 2


def average_distribution(distributions: list[Dict[str, float]]) -> Dict[str, float]:
    counts: Counter[str] = Counter()
    for distribution in distributions:
        counts.update(distribution)
    total = len(distributions) or 1
    return {key: round(value / total, 4) for key, value in counts.items()}


def normalize_counts(counts: Counter[str]) -> Dict[str, float]:
    total = sum(counts.values())
    if not total:
        return {}
    return {key: round(value / total, 4) for key, value in counts.items()}


def ratio(value: float, total: float) -> float:
    return 0.0 if total == 0 else round(value / total, 4)


def mean(values: Iterable[float]) -> float:
    rows = list(values)
    return 0.0 if not rows else round(sum(rows) / len(rows), 4)


def render_v1_current_summary(reports: list[Dict[str, Any]]) -> str:
    lines = [
        "# Simulator Evaluation Summary",
        "",
        f"- Cases: {len(reports)}",
        f"- Overall avg: {mean(report['overall_score'] for report in reports):.4f}",
        f"- Behavioral realism avg: {mean(report['scores']['behavioral_realism'] for report in reports):.4f}",
        f"- Goal alignment avg: {mean(report['scores']['goal_alignment'] for report in reports):.4f}",
        f"- Over-cooperation resistance avg: {mean(report['scores']['overly_cooperative_resistance'] for report in reports):.4f}",
        "",
        "## Per Case",
        "",
    ]
    for report in reports:
        scores = report["scores"]
        lines.append(
            f"- {report['case_id']}: overall={report['overall_score']:.4f}, "
            f"behavior={scores['behavioral_realism']:.4f}, "
            f"goal={scores['goal_alignment']:.4f}, "
            f"cooperation={scores['overly_cooperative_resistance']:.4f}"
        )
    lines.extend(
        [
            "",
            "## Version Mapping",
            "",
            "These scores evaluate original main-branch User Simulator outputs with the current metric dimensions.",
            "The module is self-contained for main-branch experiments; it does not depend on User Simulator 2.0 runtime code.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_case_report(report: Dict[str, Any]) -> str:
    scores = report["scores"]
    return "\n".join(
        [
            f"# {report['case_id']}",
            "",
            f"- Overall: {report['overall_score']:.4f}",
            f"- Behavioral realism: {scores['behavioral_realism']:.4f}",
            f"- Goal alignment: {scores['goal_alignment']:.4f}",
            f"- Over-cooperation resistance: {scores['overly_cooperative_resistance']:.4f}",
            "",
            "## Real Profile",
            "",
            fenced_json(report["real_profile"]),
            "",
            "## Sim Profile",
            "",
            fenced_json(report["sim_profile"]),
            "",
        ]
    )


def fenced_json(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def read_jsonl(path: Path) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


def write_jsonl(path: Path, rows: list[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
