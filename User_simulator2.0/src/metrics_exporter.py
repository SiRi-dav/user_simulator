from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.llm.llm_client import LLMClient
from src.schemas import KnowledgeRoadmapArtifact, model_to_dict
from src.transcript_exporter import build_transcript, read_simulation_logs
from src.utils.json_utils import dumps_json
from src.utils.jsonl import write_jsonl


QUESTION_MARKERS = ("吗", "？", "?", "是否", "有没有", "是不是", "哪个", "什么", "能否", "可否")
ANSWER_SIGNALS = ("是", "不是", "有", "没有", "可以", "不可以", "我这边", "目前", "刚", "看了", "系统", "文件", "报错")
INTERNAL_TERMS = ("user-facing", "diagnostic", "solution point", "external", "roadmap", "Knowledge Module", "Blind User")


SIMULATOR_JUDGE_SYSTEM = """You are an evaluator for an enterprise IT user simulator.
Judge the simulated user's quality, not the assistant's quality.
Return only valid JSON."""

SIMULATOR_JUDGE_USER = """Transcript:
{transcript_json}

Runtime roadmap:
{roadmap_json}

Evaluate the simulated user on four dimensions, each from 0.0 to 1.0:
1. answer_alignment_score: whether user replies answer the assistant's latest question.
2. information_progress_score: whether user replies move the dialogue forward with useful information, confirmation, denial, action attempt, or result feedback.
3. user_knowledge_boundary_score: whether the user stays within what a real blind user should know and does not reveal solution/internal/external-case facts prematurely.
4. interaction_realism_score: whether the user sounds like a realistic employee user, concise and non-template-like.

Return JSON:
{{
  "answer_alignment_score": 0.0,
  "information_progress_score": 0.0,
  "user_knowledge_boundary_score": 0.0,
  "interaction_realism_score": 0.0,
  "overall_score": 0.0,
  "reasons": ["..."]
}}"""


class MetricsExporter:
    def __init__(
        self,
        output_dir: Path,
        knowledge_artifacts: dict[str, KnowledgeRoadmapArtifact],
        llm_client: LLMClient | None = None,
    ):
        self.output_dir = output_dir
        self.metrics_dir = output_dir / "metrics"
        self.knowledge_artifacts = knowledge_artifacts
        self.llm_client = llm_client

    def export_case(self, case_id: str, use_judge: bool = False) -> list[Path]:
        records = self.calculate_cases([case_id], use_judge=use_judge)
        if not records:
            raise ValueError(f"case_id not found in simulation_logs.jsonl: {case_id}")
        return self.write_outputs(records)

    def export_cases(self, case_ids: Iterable[str] | None = None, use_judge: bool = False) -> list[Path]:
        records = self.calculate_cases(case_ids, use_judge=use_judge)
        if not records:
            raise ValueError("No simulation logs found for selected cases.")
        return self.write_outputs(records)

    def calculate_cases(self, case_ids: Iterable[str] | None = None, use_judge: bool = False) -> list[Dict[str, Any]]:
        selected = set(case_ids or [])
        logs_by_case: dict[str, list[Dict[str, Any]]] = {}
        for record in read_simulation_logs(self.output_dir / "simulation_logs.jsonl"):
            case_id = record["case_id"]
            if selected and case_id not in selected:
                continue
            logs_by_case.setdefault(case_id, []).append(record)
        metrics = []
        for case_id in sorted(logs_by_case):
            artifact = self.knowledge_artifacts.get(case_id)
            transcript = build_transcript(case_id, logs_by_case[case_id])
            metric = calculate_rule_metrics(case_id, transcript, artifact)
            if use_judge:
                metric["llm_judge"] = self.judge_case(transcript, artifact)
            metrics.append(metric)
        return metrics

    def judge_case(self, transcript: Dict[str, Any], artifact: KnowledgeRoadmapArtifact | None) -> Dict[str, Any]:
        if self.llm_client is None:
            raise ValueError("--judge requires an LLM client")
        roadmap = model_to_dict(artifact.roadmap) if artifact else {}
        payload = self.llm_client.generate_json(
            SIMULATOR_JUDGE_SYSTEM,
            SIMULATOR_JUDGE_USER.format(transcript_json=dumps_json(transcript), roadmap_json=dumps_json(roadmap)),
            schema_name="SimulatorQualityJudge",
        )
        return normalize_judge_payload(payload)

    def write_outputs(self, records: list[Dict[str, Any]]) -> list[Path]:
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = self.metrics_dir / "simulation_metrics.jsonl"
        md_path = self.metrics_dir / "summary.md"
        write_jsonl(jsonl_path, records)
        md_path.write_text(render_metrics_summary(records), encoding="utf-8")
        return [jsonl_path, md_path]


def calculate_rule_metrics(
    case_id: str,
    transcript: Dict[str, Any],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    messages = transcript.get("messages") or []
    user_messages = [message for message in messages if message.get("role") == "user"]
    assistant_messages = [message for message in messages if message.get("role") == "assistant"]
    user_texts = [str(message.get("content") or "") for message in user_messages]
    avg_user_reply_chars = average([len(text) for text in user_texts])
    answer_stats = answer_alignment_stats(messages)
    progress_stats = information_progress_stats(user_texts)
    boundary_stats = knowledge_boundary_stats(user_texts, artifact)
    realism_stats = interaction_realism_stats(user_texts)
    scores = {
        "answer_alignment_score": answer_stats["answer_alignment_rate"],
        "information_progress_score": progress_stats["information_progress_rate"],
        "user_knowledge_boundary_score": 1.0 - boundary_stats["boundary_violation_rate"],
        "interaction_realism_score": realism_stats["interaction_realism_score"],
    }
    return {
        "case_id": case_id,
        "turn_count": transcript.get("turn_count", 0),
        "user_message_count": len(user_messages),
        "assistant_message_count": len(assistant_messages),
        "avg_user_reply_chars": round(avg_user_reply_chars, 3),
        **answer_stats,
        **progress_stats,
        **boundary_stats,
        **realism_stats,
        **scores,
        "overall_rule_score": round(average(list(scores.values())), 3),
        "stop_reason": transcript.get("stop_reason", ""),
        "solution_status": transcript.get("solution_status", ""),
    }


def answer_alignment_stats(messages: list[Dict[str, Any]]) -> Dict[str, Any]:
    question_count = 0
    answered_count = 0
    previous_assistant = ""
    for message in messages:
        role = message.get("role")
        content = str(message.get("content") or "")
        if role == "assistant":
            previous_assistant = content
            continue
        if role != "user" or not previous_assistant or not is_question(previous_assistant):
            continue
        question_count += 1
        if has_answer_signal(content, previous_assistant):
            answered_count += 1
    miss_count = question_count - answered_count
    return {
        "assistant_question_count": question_count,
        "answered_question_count": answered_count,
        "answer_miss_count": miss_count,
        "answer_alignment_rate": safe_rate(answered_count, question_count, default=1.0),
    }


def information_progress_stats(user_texts: list[str]) -> Dict[str, Any]:
    if not user_texts:
        return {"progress_turn_count": 0, "no_progress_turn_count": 0, "information_progress_rate": 0.0}
    seen = set()
    progress = 0
    for text in user_texts:
        normalized = normalize_text(text)
        has_new_text = normalized not in seen
        has_action_signal = any(token in text for token in ("看了", "试了", "打开", "重启", "结束", "确认", "有", "没有", "是", "不是"))
        if has_new_text or has_action_signal:
            progress += 1
        seen.add(normalized)
    return {
        "progress_turn_count": progress,
        "no_progress_turn_count": len(user_texts) - progress,
        "information_progress_rate": safe_rate(progress, len(user_texts), default=0.0),
    }


def knowledge_boundary_stats(user_texts: list[str], artifact: KnowledgeRoadmapArtifact | None) -> Dict[str, Any]:
    if artifact is None:
        return {"boundary_violation_count": 0, "boundary_violation_rate": 0.0, "boundary_violation_hits": []}
    forbidden = list(artifact.roadmap.forbidden_content)
    forbidden.extend(point.content for point in artifact.roadmap.solution_points)
    forbidden.extend(point.content for point in artifact.roadmap.external_points)
    hits = []
    for text in user_texts:
        for item in forbidden:
            if text_matches_forbidden(text, item):
                hits.append({"reply": text, "matched": item})
                break
    return {
        "boundary_violation_count": len(hits),
        "boundary_violation_rate": safe_rate(len(hits), len(user_texts), default=0.0),
        "boundary_violation_hits": hits[:5],
    }


def interaction_realism_stats(user_texts: list[str]) -> Dict[str, Any]:
    if not user_texts:
        return {"overlong_reply_rate": 0.0, "internal_term_rate": 0.0, "interaction_realism_score": 0.0}
    overlong = sum(1 for text in user_texts if len(text) > 80)
    internal = sum(1 for text in user_texts if any(term in text for term in INTERNAL_TERMS))
    realism_score = 1.0 - min(1.0, safe_rate(overlong + internal, len(user_texts), default=0.0))
    return {
        "overlong_reply_rate": safe_rate(overlong, len(user_texts), default=0.0),
        "internal_term_rate": safe_rate(internal, len(user_texts), default=0.0),
        "interaction_realism_score": realism_score,
    }


def normalize_judge_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    scores = {
        "answer_alignment_score": clamp_float(payload.get("answer_alignment_score")),
        "information_progress_score": clamp_float(payload.get("information_progress_score")),
        "user_knowledge_boundary_score": clamp_float(payload.get("user_knowledge_boundary_score")),
        "interaction_realism_score": clamp_float(payload.get("interaction_realism_score")),
    }
    overall = payload.get("overall_score")
    scores["overall_score"] = clamp_float(overall if overall is not None else average(list(scores.values())))
    reasons = payload.get("reasons")
    scores["reasons"] = [str(item) for item in reasons] if isinstance(reasons, list) else []
    return scores


def render_metrics_summary(records: list[Dict[str, Any]]) -> str:
    lines = [
        "# User Simulator Metrics Summary",
        "",
        "| case_id | turns | answer_align | info_progress | boundary | realism | overall_rule | judge_overall |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        judge = record.get("llm_judge") or {}
        lines.append(
            "| {case_id} | {turns} | {answer:.2f} | {progress:.2f} | {boundary:.2f} | {realism:.2f} | {overall:.2f} | {judge_overall} |".format(
                case_id=record["case_id"],
                turns=record.get("turn_count", 0),
                answer=float(record.get("answer_alignment_score", 0.0)),
                progress=float(record.get("information_progress_score", 0.0)),
                boundary=float(record.get("user_knowledge_boundary_score", 0.0)),
                realism=float(record.get("interaction_realism_score", 0.0)),
                overall=float(record.get("overall_rule_score", 0.0)),
                judge_overall=f"{float(judge.get('overall_score')):.2f}" if "overall_score" in judge else "",
            )
        )
    return "\n".join(lines) + "\n"


def is_question(text: str) -> bool:
    return any(marker in text for marker in QUESTION_MARKERS)


def has_answer_signal(user_text: str, assistant_text: str) -> bool:
    if any(signal in user_text for signal in ANSWER_SIGNALS):
        return True
    assistant_chars = meaningful_chars(assistant_text)
    user_chars = meaningful_chars(user_text)
    if not assistant_chars:
        return False
    overlap = len(assistant_chars & user_chars) / max(len(assistant_chars), 1)
    return overlap >= 0.15


def text_matches_forbidden(reply: str, forbidden: str) -> bool:
    item = str(forbidden or "").strip()
    if len(item) < 4:
        return False
    if item in reply:
        return True
    item_chars = meaningful_chars(item)
    reply_chars = meaningful_chars(reply)
    if len(item_chars) < 4:
        return False
    return len(item_chars & reply_chars) / len(item_chars) >= 0.65


def meaningful_chars(text: str) -> set[str]:
    return {char for char in str(text or "") if char.strip() and char not in "，。！？、；：,.!?;:()（）【】[]<>《》\"' "}


def normalize_text(text: str) -> str:
    return "".join(str(text or "").split())


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def safe_rate(numerator: int, denominator: int, default: float = 0.0) -> float:
    return round(numerator / denominator, 3) if denominator else default


def clamp_float(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(1.0, numeric))
