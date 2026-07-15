from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.behavior_mining.dialogue_loader import load_dialogues
from src.llm.llm_client import LLMClient
from src.review_exporter import safe_filename
from src.schemas import HistoricalDialogue, KnowledgeRoadmapArtifact, model_to_dict
from src.simulator_evaluator import expand_case_ids, historical_dialogues_to_transcripts, sample_transcripts
from src.transcript_exporter import build_transcript, read_simulation_logs, split_logs_into_sessions
from src.utils.json_utils import dumps_json
from src.utils.jsonl import write_jsonl


ACTION_REQUEST_MARKERS = (
    "请",
    "尝试",
    "试一下",
    "打开",
    "点击",
    "重启",
    "检查",
    "确认",
    "执行",
    "设置",
    "安装",
    "登录",
    "清除",
    "重新",
)
ACTION_FEEDBACK_MARKERS = (
    "试了",
    "看了",
    "打开了",
    "点了",
    "重启了",
    "执行了",
    "操作了",
    "还是",
    "不行",
    "没有",
    "找不到",
    "可以了",
    "好了",
)
ACCEPT_MARKERS = ("好的", "好", "可以", "行", "谢谢", "感谢", "解决了", "没问题")
RESISTANCE_MARKERS = ("不行", "没解决", "还是", "找不到", "不会", "不清楚", "看不懂", "没有用")


LLM_PRIMARY_EVAL_SYSTEM = """你是企业 IT 用户模拟器的严格评测专家。
你的任务是评估"模拟用户"本身,不要把 assistant 的能力问题算到用户模拟器头上。
规则抽取结果只作为 evidence,最终判断必须由你基于语义完成。
只输出合法 JSON,不要输出解释性正文。"""


LLM_PRIMARY_EVAL_USER = """目标 case_id:
{case_id}

目标 case roadmap:
{roadmap_json}

真实用户对话样本:
{real_transcripts_json}

模拟对话样本:
{simulated_transcripts_json}

用户侧真实消息集合（用于 user-only C2ST / discriminability, 不含 assistant 回复）:
{real_user_messages_json}

用户侧模拟消息集合（用于 user-only C2ST / discriminability, 不含 assistant 回复）:
{simulated_user_messages_json}

逐轮 assistant -> simulated user 对:
{conditional_pairs_json}

规则 evidence（只能辅助,不能直接当分数）:
{evidence_json}

请用 LLM judge 作为唯一正式评分来源,从以下六个维度评分。所有分数为 0.0 到 1.0,越高越好。

1. Conditional User Behavior
   评估在每一轮 assistant 回复已经给定时,模拟用户下一步反应是否合理。
   - assistant 追问事实: 用户是否只回答自己可见/路书允许的事实
   - assistant 要求动作: 用户是否执行、追问步骤、或反馈执行结果
   - assistant 给泛化或无效建议: 用户是否合理表达未解决、困惑、需要下一步
   - assistant 命中 target solution: 用户是否自然接受并结束
   - assistant 没命中 target solution: 用户是否避免错误接受
   - assistant 重复无效建议: 用户是否表现出真实阻力,而不是机械配合

2. Goal Alignment
   评估模拟用户是否忠实扮演该 case 用户。
   - 是否始终围绕初始问题
   - 是否按 assistant 追问逐步释放信息
   - 是否避免主动倾倒诊断点或 solution
   - 用户事实是否与 roadmap 一致,没有幻觉或跑题

3. Anti-overcooperation
   评估模拟用户是否不过度合作。
   - 不应轻易接受无效方案
   - 应有合理困惑、犹豫、追问、拒绝、执行反馈
   - 如果 assistant 没解决,用户合理失败/请求下一步应给高分

4. RealSim-style Behavior
   只评估用户侧行为分布和表达风格是否像真实用户。
   请从八个方面综合判断: user_intent, feedback, emotion, domain_specific_knowledge,
   personal_context_identity, message_length, linguistic_attributes, errors。

5. User-only C2ST / Discriminability
   只看用户消息集合,不要看 assistant 回复。
   如果真实用户消息和模拟用户消息很容易被区分,分低;如果难以区分,分高。
   请给出 distinguishing_cues。

6. Solution-conditioned Leakage-aware Response
   不要因为 assistant 没命中 target solution 而惩罚 simulator。
   你需要先判断 assistant-side:
   - assistant 是否命中 target solution
   - 是否存在 assistant_failure_confounded
   然后只评价 user-side:
   - assistant 命中 target solution 时,用户是否自然接受
   - assistant 未命中 target solution 时,用户是否没有错误接受
   - 用户是否在 assistant 提供相关信息前泄漏 solution、judge_only diagnostic、forbidden content 或 roadmap 内部信息

总体评分建议权重:
overall = 0.30 conditional_user_behavior + 0.20 goal_alignment + 0.15 anti_overcooperation
        + 0.15 realsim_behavior + 0.10 user_only_discriminability + 0.10 leakage_aware_response

返回 JSON:
{{
  "conditional_user_behavior_score": 0.0,
  "goal_alignment_score": 0.0,
  "anti_overcooperation_score": 0.0,
  "realsim_behavior_score": 0.0,
  "user_only_discriminability_score": 0.0,
  "leakage_aware_response_score": 0.0,
  "overall_score": 0.0,
  "assistant_solution_hit": true,
  "assistant_failure_confounded": false,
  "user_wrongly_accepted_without_target_solution": false,
  "user_leakage_detected": false,
  "subscores": {{
    "realsim_intent": 0.0,
    "realsim_feedback": 0.0,
    "realsim_emotion": 0.0,
    "realsim_domain_specific_knowledge": 0.0,
    "realsim_personal_context": 0.0,
    "realsim_message_length": 0.0,
    "realsim_linguistic_attributes": 0.0,
    "realsim_error_reporting": 0.0
  }},
  "failure_modes": ["..."],
  "distinguishing_cues": ["..."],
  "analysis": {{
    "conditional_user_behavior": "...",
    "goal_alignment": "...",
    "anti_overcooperation": "...",
    "realsim_behavior": "...",
    "user_only_discriminability": "...",
    "leakage_aware_response": "...",
    "assistant_confounding": "..."
  }}
}}"""


class LLMPrimarySimulatorEvaluator:
    def __init__(
        self,
        output_dir: Path,
        knowledge_artifacts: dict[str, KnowledgeRoadmapArtifact],
        llm_client: LLMClient,
    ):
        self.output_dir = output_dir
        self.eval_dir = output_dir / "simulator_eval_llm_primary"
        self.knowledge_artifacts = knowledge_artifacts
        self.llm_client = llm_client

    def evaluate(
        self,
        case_ids: Iterable[str],
        dialogues_path: Path,
        dialogue_fields: Dict[str, Any] | None = None,
        session_policy: str = "all",
    ) -> list[Path]:
        if session_policy not in {"all", "latest", "first"}:
            raise ValueError(f"Unsupported session_policy: {session_policy}")
        real_dialogues = load_dialogues(dialogues_path, dialogue_fields)
        reports: list[Dict[str, Any]] = []
        for case_id in [str(item) for item in case_ids]:
            real_transcripts = historical_dialogues_to_transcripts(select_real_dialogues(real_dialogues, case_id))
            simulated_transcripts = load_simulated_sessions(self.output_dir, case_id, session_policy=session_policy)
            if not real_transcripts:
                raise ValueError(f"No real dialogues found for case_id: {case_id}")
            if not simulated_transcripts:
                raise ValueError(f"No simulated sessions found for case_id: {case_id}")
            reports.append(self.evaluate_case(case_id, real_transcripts, simulated_transcripts))
        return self.write_outputs(reports)

    def evaluate_case(
        self,
        case_id: str,
        real_transcripts: list[Dict[str, Any]],
        simulated_transcripts: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        artifact = self.knowledge_artifacts.get(case_id)
        evidence = build_evidence(real_transcripts, simulated_transcripts, artifact)
        judge = self.judge_case(case_id, real_transcripts, simulated_transcripts, artifact, evidence)
        return {
            "case_id": case_id,
            "real_session_count": len(real_transcripts),
            "simulated_session_count": len(simulated_transcripts),
            "evaluation_mode": "llm_primary_user_conditioned",
            "overall_score": judge["overall_score"],
            "scores": {
                "conditional_user_behavior": judge["conditional_user_behavior_score"],
                "goal_alignment": judge["goal_alignment_score"],
                "anti_overcooperation": judge["anti_overcooperation_score"],
                "realsim_behavior": judge["realsim_behavior_score"],
                "user_only_discriminability": judge["user_only_discriminability_score"],
                "leakage_aware_response": judge["leakage_aware_response_score"],
            },
            "assistant_solution_hit": judge["assistant_solution_hit"],
            "assistant_failure_confounded": judge["assistant_failure_confounded"],
            "user_wrongly_accepted_without_target_solution": judge["user_wrongly_accepted_without_target_solution"],
            "user_leakage_detected": judge["user_leakage_detected"],
            "subscores": judge.get("subscores", {}),
            "failure_modes": judge.get("failure_modes", []),
            "distinguishing_cues": judge.get("distinguishing_cues", []),
            "analysis": judge.get("analysis", {}),
            "evidence": evidence,
            "llm_judge": judge,
        }

    def judge_case(
        self,
        case_id: str,
        real_transcripts: list[Dict[str, Any]],
        simulated_transcripts: list[Dict[str, Any]],
        artifact: KnowledgeRoadmapArtifact | None,
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        roadmap = model_to_dict(artifact.roadmap) if artifact else {}
        payload = self.llm_client.generate_json(
            LLM_PRIMARY_EVAL_SYSTEM,
            LLM_PRIMARY_EVAL_USER.format(
                case_id=case_id,
                roadmap_json=dumps_json(roadmap),
                real_transcripts_json=dumps_json(sample_transcripts(real_transcripts)),
                simulated_transcripts_json=dumps_json(sample_transcripts(simulated_transcripts)),
                real_user_messages_json=dumps_json(sample_user_messages(real_transcripts, limit=80)),
                simulated_user_messages_json=dumps_json(sample_user_messages(simulated_transcripts, limit=80)),
                conditional_pairs_json=dumps_json(build_conditional_pairs(simulated_transcripts, limit=80)),
                evidence_json=dumps_json(evidence),
            ),
            schema_name="LLMPrimarySimulatorEval",
        )
        return normalize_judge_payload(payload)

    def write_outputs(self, reports: list[Dict[str, Any]]) -> list[Path]:
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = self.eval_dir / "simulator_eval_llm_primary.jsonl"
        md_path = self.eval_dir / "summary.md"
        write_jsonl(jsonl_path, reports)
        md_path.write_text(render_summary(reports), encoding="utf-8")
        for report in reports:
            case_path = self.eval_dir / f"{safe_filename(report['case_id'])}.md"
            case_path.write_text(render_case_report(report), encoding="utf-8")
        return [jsonl_path, md_path]


def build_evidence(
    real_transcripts: list[Dict[str, Any]],
    simulated_transcripts: list[Dict[str, Any]],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    conditional_pairs = build_conditional_pairs(simulated_transcripts, limit=200)
    solution_contents = roadmap_texts(artifact, "solution_points")
    forbidden_contents = roadmap_forbidden_texts(artifact)
    return {
        "real_user_message_count": len(sample_user_messages(real_transcripts, limit=100000)),
        "simulated_user_message_count": len(sample_user_messages(simulated_transcripts, limit=100000)),
        "real_user_samples": sample_user_messages(real_transcripts, limit=12),
        "simulated_user_samples": sample_user_messages(simulated_transcripts, limit=12),
        "action_request_pairs": [pair for pair in conditional_pairs if pair.get("assistant_requests_action")][:20],
        "action_feedback_pairs": [pair for pair in conditional_pairs if pair.get("user_gives_action_feedback")][:20],
        "possible_wrong_acceptance_pairs": possible_wrong_acceptance_pairs(conditional_pairs, solution_contents),
        "possible_user_leakage": possible_user_leakage(simulated_transcripts, solution_contents + forbidden_contents),
        "assistant_solution_hit_candidates": assistant_solution_hit_candidates(simulated_transcripts, solution_contents),
        "resistance_turns": resistance_turns(simulated_transcripts),
        "note": "Evidence is heuristic extraction only. LLM judge must make final semantic decisions.",
    }


def select_real_dialogues(dialogues: list[HistoricalDialogue], case_id: str) -> list[HistoricalDialogue]:
    selected = []
    for dialogue in dialogues:
        ids = expand_case_ids(dialogue.case_id) | expand_case_ids(dialogue.final_case_id)
        if case_id in ids:
            selected.append(dialogue)
    return selected


def load_simulated_sessions(output_dir: Path, case_id: str, session_policy: str = "all") -> list[Dict[str, Any]]:
    logs = [record for record in read_simulation_logs(output_dir / "simulation_logs.jsonl") if record["case_id"] == case_id]
    sessions = split_logs_into_sessions(logs)
    transcripts = []
    for index, session in enumerate(sessions, 1):
        transcript = build_transcript(case_id, session)
        transcript["session_index"] = index
        transcript["session_id"] = f"{case_id}#{index}"
        transcripts.append(transcript)
    if session_policy == "latest" and transcripts:
        return [transcripts[-1]]
    if session_policy == "first" and transcripts:
        return [transcripts[0]]
    return transcripts


def sample_user_messages(transcripts: list[Dict[str, Any]], limit: int = 80) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for transcript in transcripts:
        session_id = transcript.get("session_id") or transcript.get("case_id")
        for message in transcript.get("messages") or []:
            if message.get("role") == "user":
                rows.append(
                    {
                        "session_id": session_id,
                        "turn": message.get("turn"),
                        "text": str(message.get("content") or ""),
                    }
                )
    return rows[:limit]


def build_conditional_pairs(transcripts: list[Dict[str, Any]], limit: int = 80) -> list[Dict[str, Any]]:
    pairs: list[Dict[str, Any]] = []
    for transcript in transcripts:
        session_id = transcript.get("session_id") or transcript.get("case_id")
        previous_assistant = ""
        previous_turn = None
        for message in transcript.get("messages") or []:
            role = message.get("role")
            text = str(message.get("content") or "")
            if role == "assistant":
                previous_assistant = text
                previous_turn = message.get("turn")
                continue
            if role != "user" or not previous_assistant:
                continue
            pairs.append(
                {
                    "session_id": session_id,
                    "assistant_turn": previous_turn,
                    "user_turn": message.get("turn"),
                    "assistant": previous_assistant,
                    "user": text,
                    "assistant_requests_action": contains_any(previous_assistant, ACTION_REQUEST_MARKERS),
                    "user_gives_action_feedback": contains_any(text, ACTION_FEEDBACK_MARKERS),
                    "user_accepts": contains_any(text, ACCEPT_MARKERS),
                    "user_resists": contains_any(text, RESISTANCE_MARKERS),
                }
            )
    return pairs[:limit]


def possible_wrong_acceptance_pairs(pairs: list[Dict[str, Any]], solution_contents: list[str]) -> list[Dict[str, Any]]:
    rows = []
    for pair in pairs:
        if not pair.get("user_accepts"):
            continue
        if any(text_matches(pair.get("assistant", ""), solution) for solution in solution_contents):
            continue
        rows.append(pair)
    return rows[:20]


def possible_user_leakage(transcripts: list[Dict[str, Any]], protected_contents: list[str]) -> list[Dict[str, Any]]:
    hits = []
    for transcript in transcripts:
        session_id = transcript.get("session_id") or transcript.get("case_id")
        assistant_seen = ""
        for message in transcript.get("messages") or []:
            role = message.get("role")
            text = str(message.get("content") or "")
            if role == "assistant":
                assistant_seen += "\n" + text
                continue
            if role != "user":
                continue
            for content in protected_contents:
                if text_matches(text, content) and not text_matches(assistant_seen, content):
                    hits.append({"session_id": session_id, "turn": message.get("turn"), "user": text, "matched": content})
                    break
    return hits[:20]


def assistant_solution_hit_candidates(transcripts: list[Dict[str, Any]], solution_contents: list[str]) -> list[Dict[str, Any]]:
    hits = []
    for transcript in transcripts:
        session_id = transcript.get("session_id") or transcript.get("case_id")
        for message in transcript.get("messages") or []:
            if message.get("role") != "assistant":
                continue
            text = str(message.get("content") or "")
            for solution in solution_contents:
                if text_matches(text, solution):
                    hits.append({"session_id": session_id, "turn": message.get("turn"), "assistant": text, "matched": solution})
                    break
    return hits[:20]


def resistance_turns(transcripts: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    rows = []
    for transcript in transcripts:
        session_id = transcript.get("session_id") or transcript.get("case_id")
        for message in transcript.get("messages") or []:
            text = str(message.get("content") or "")
            if message.get("role") == "user" and contains_any(text, RESISTANCE_MARKERS):
                rows.append({"session_id": session_id, "turn": message.get("turn"), "user": text})
    return rows[:20]


def roadmap_texts(artifact: KnowledgeRoadmapArtifact | None, field_name: str) -> list[str]:
    if artifact is None:
        return []
    return [str(item.content) for item in getattr(artifact.roadmap, field_name, []) if str(item.content).strip()]


def roadmap_forbidden_texts(artifact: KnowledgeRoadmapArtifact | None) -> list[str]:
    if artifact is None:
        return []
    texts = [str(item) for item in artifact.roadmap.forbidden_content if str(item).strip()]
    texts.extend(roadmap_texts(artifact, "external_points"))
    return texts


def contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker and marker in text for marker in markers)


def text_matches(text: Any, content: Any) -> bool:
    text_value = str(text or "").strip().lower()
    content_value = str(content or "").strip().lower()
    if not text_value or not content_value:
        return False
    if len(content_value) >= 4 and content_value in text_value:
        return True
    content_chars = {char for char in content_value if "\u4e00" <= char <= "\u9fff"}
    text_chars = {char for char in text_value if "\u4e00" <= char <= "\u9fff"}
    if len(content_chars) < 6:
        return False
    return len(content_chars & text_chars) / max(len(content_chars), 1) >= 0.75


def normalize_judge_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    conditional = score(payload.get("conditional_user_behavior_score"))
    goal = score(payload.get("goal_alignment_score"))
    anti = score(payload.get("anti_overcooperation_score"))
    realsim = score(payload.get("realsim_behavior_score"))
    c2st = score(payload.get("user_only_discriminability_score"))
    leakage = score(payload.get("leakage_aware_response_score"))
    default_overall = round(
        0.30 * conditional + 0.20 * goal + 0.15 * anti + 0.15 * realsim + 0.10 * c2st + 0.10 * leakage,
        3,
    )
    return {
        "conditional_user_behavior_score": conditional,
        "goal_alignment_score": goal,
        "anti_overcooperation_score": anti,
        "realsim_behavior_score": realsim,
        "user_only_discriminability_score": c2st,
        "leakage_aware_response_score": leakage,
        "overall_score": score(payload.get("overall_score"), default_overall),
        "assistant_solution_hit": bool(payload.get("assistant_solution_hit", False)),
        "assistant_failure_confounded": bool(payload.get("assistant_failure_confounded", False)),
        "user_wrongly_accepted_without_target_solution": bool(payload.get("user_wrongly_accepted_without_target_solution", False)),
        "user_leakage_detected": bool(payload.get("user_leakage_detected", False)),
        "subscores": normalize_scores_dict(payload.get("subscores") or {}),
        "failure_modes": normalize_string_list(payload.get("failure_modes")),
        "distinguishing_cues": normalize_string_list(payload.get("distinguishing_cues")),
        "analysis": normalize_analysis(payload.get("analysis") or {}),
    }


def score(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return round(max(0.0, min(1.0, numeric)), 3)


def normalize_scores_dict(payload: Dict[str, Any]) -> Dict[str, float]:
    return {str(key): score(value) for key, value in payload.items()}


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def normalize_analysis(value: Dict[str, Any]) -> Dict[str, str]:
    return {str(key): str(item) for key, item in value.items()}


def render_summary(reports: list[Dict[str, Any]]) -> str:
    lines = [
        "# LLM-Primary Simulator Evaluation Summary",
        "",
        "| case_id | real | simulated | overall | conditional | goal | anti-overcoop | realsim | user-c2st | leakage-response | assistant-confounded |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for report in reports:
        scores = report["scores"]
        lines.append(
            "| {case_id} | {real} | {sim} | {overall:.3f} | {conditional:.3f} | {goal:.3f} | {anti:.3f} | {realsim:.3f} | {c2st:.3f} | {leakage:.3f} | {confounded} |".format(
                case_id=report["case_id"],
                real=report["real_session_count"],
                sim=report["simulated_session_count"],
                overall=report["overall_score"],
                conditional=scores["conditional_user_behavior"],
                goal=scores["goal_alignment"],
                anti=scores["anti_overcooperation"],
                realsim=scores["realsim_behavior"],
                c2st=scores["user_only_discriminability"],
                leakage=scores["leakage_aware_response"],
                confounded="yes" if report["assistant_failure_confounded"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "This evaluator is LLM-judge primary. Heuristic rules only extract evidence and do not produce final scores.",
            "User-only C2ST/discriminability uses user messages only; assistant replies are excluded from that judgment.",
            "Solution hit is treated as assistant-side attribution. Assistant failure should not directly penalize the user simulator.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_case_report(report: Dict[str, Any]) -> str:
    scores = report["scores"]
    lines = [
        f"# LLM-Primary Evaluation {report['case_id']}",
        "",
        f"- overall_score: {report['overall_score']:.3f}",
        f"- conditional_user_behavior: {scores['conditional_user_behavior']:.3f}",
        f"- goal_alignment: {scores['goal_alignment']:.3f}",
        f"- anti_overcooperation: {scores['anti_overcooperation']:.3f}",
        f"- realsim_behavior: {scores['realsim_behavior']:.3f}",
        f"- user_only_discriminability: {scores['user_only_discriminability']:.3f}",
        f"- leakage_aware_response: {scores['leakage_aware_response']:.3f}",
        f"- assistant_solution_hit: {report['assistant_solution_hit']}",
        f"- assistant_failure_confounded: {report['assistant_failure_confounded']}",
        f"- user_wrongly_accepted_without_target_solution: {report['user_wrongly_accepted_without_target_solution']}",
        f"- user_leakage_detected: {report['user_leakage_detected']}",
        "",
        "## Failure Modes",
        "",
    ]
    lines.extend([f"- {item}" for item in report.get("failure_modes") or ["None reported."]])
    lines.extend(["", "## Distinguishing Cues", ""])
    lines.extend([f"- {item}" for item in report.get("distinguishing_cues") or ["None reported."]])
    lines.extend(["", "## Analysis", ""])
    for key, value in (report.get("analysis") or {}).items():
        lines.extend([f"### {key}", "", str(value), ""])
    lines.extend(["## Evidence", "", "```json", json.dumps(report.get("evidence") or {}, ensure_ascii=False, indent=2), "```"])
    return "\n".join(lines).rstrip() + "\n"
