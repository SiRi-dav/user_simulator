from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.behavior_mining.dialogue_loader import load_dialogues
from src.llm.llm_client import LLMClient
from src.metrics_exporter import knowledge_boundary_stats
from src.review_exporter import safe_filename
from src.schemas import HistoricalDialogue, KnowledgeRoadmapArtifact, model_to_dict
from src.transcript_exporter import build_transcript, read_simulation_logs
from src.utils.json_utils import dumps_json
from src.utils.jsonl import write_jsonl


USER_QUESTION_MARKERS = ("?", "？", "吗", "怎么", "如何", "为啥", "为什么", "能不能", "可以不")
ACCEPT_MARKERS = ("好的", "好", "可以", "行", "嗯", "谢谢", "感谢", "已解决", "解决了", "没问题")
REJECT_MARKERS = ("不行", "不可以", "没有用", "还是不行", "没解决", "不对", "不是", "不需要")
CONFUSION_MARKERS = ("不懂", "不会", "不知道", "没看懂", "看不明白", "不太清楚", "找不到", "没找到")
FRUSTRATION_MARKERS = ("急", "麻烦", "烦", "一直", "怎么还", "崩溃", "影响", "耽误")
ACTION_MARKERS = ("试了", "看了", "打开", "重启", "点击", "操作", "登录", "升级", "安装", "配置")
INFO_MARKERS = ("报错", "提示", "显示", "系统", "电脑", "账号", "邮箱", "文件", "版本", "网络")
OFF_TOPIC_MARKERS = ("天气", "吃饭", "旅游", "电影", "小说", "股票", "游戏")


SIMULATOR_EVAL_JUDGE_SYSTEM = """你是企业 IT 客服用户模拟器的评测专家。
你会对比真实用户对话和模拟用户对话，只评估“模拟用户”是否像真实用户、是否坚持目标、是否过度合作。
请只输出合法 JSON，不要输出解释性正文。"""


SIMULATOR_EVAL_JUDGE_USER = """目标 case_id:
{case_id}

真实对话样本:
{real_transcripts_json}

模拟对话样本:
{simulated_transcripts_json}

目标 case roadmap:
{roadmap_json}

规则统计摘要:
{feature_summary_json}

请评估这些规则指标难以可靠判断的语义维度：
1. behavioral_realism_score: 模拟用户在交流风格、信息透露节奏、澄清/困惑/错误反应上是否像真实用户。
2. user_sim_index: 细分为 communication_style、information_pattern、clarification_behavior、error_reaction，并给 score。
3. goal_alignment_score: 模拟用户是否始终围绕目标 case，是否没有偏离/偷看答案/提前泄露解决方案。
4. anti_overcooperation_score: 模拟用户是否避免过度配合；真实用户会有困惑、犹豫、追问、拒绝或失败反馈时，模拟用户是否也合理表现。

分数均为 0.0 到 1.0，越高越好。返回 JSON：
{{
  "behavioral_realism_score": 0.0,
  "user_sim_index": {{
    "score": 0.0,
    "communication_style": 0.0,
    "information_pattern": 0.0,
    "clarification_behavior": 0.0,
    "error_reaction": 0.0
  }},
  "goal_alignment_score": 0.0,
  "anti_overcooperation_score": 0.0,
  "overcooperation_risk": "low|medium|high",
  "reasons": ["..."]
}}"""


class SimulatorEvaluator:
    def __init__(
        self,
        output_dir: Path,
        knowledge_artifacts: dict[str, KnowledgeRoadmapArtifact],
        llm_client: LLMClient | None = None,
    ):
        self.output_dir = output_dir
        self.eval_dir = output_dir / "simulator_eval"
        self.knowledge_artifacts = knowledge_artifacts
        self.llm_client = llm_client

    def evaluate(
        self,
        case_ids: Iterable[str],
        dialogues_path: Path,
        dialogue_fields: Dict[str, Any] | None = None,
        use_judge: bool = False,
    ) -> list[Path]:
        case_ids_list = [str(case_id) for case_id in case_ids]
        real_dialogues = load_dialogues(dialogues_path, dialogue_fields)
        reports = []
        for case_id in case_ids_list:
            real_transcripts = historical_dialogues_to_transcripts(select_real_dialogues(real_dialogues, case_id))
            simulated_transcripts = load_simulated_sessions(self.output_dir, case_id)
            if not real_transcripts:
                raise ValueError(f"No real dialogues found for case_id: {case_id}")
            if not simulated_transcripts:
                raise ValueError(f"No simulated sessions found for case_id: {case_id}")
            reports.append(self.evaluate_case(case_id, real_transcripts, simulated_transcripts, use_judge=use_judge))
        return self.write_outputs(reports)

    def evaluate_case(
        self,
        case_id: str,
        real_transcripts: list[Dict[str, Any]],
        simulated_transcripts: list[Dict[str, Any]],
        use_judge: bool = False,
    ) -> Dict[str, Any]:
        artifact = self.knowledge_artifacts.get(case_id)
        real_features = [extract_features(item) for item in real_transcripts]
        sim_features = [extract_features(item) for item in simulated_transcripts]
        behavior = behavioral_realism(real_features, sim_features)
        goal = goal_alignment(case_id, simulated_transcripts, sim_features, artifact)
        cooperation = overly_cooperative(real_features, sim_features)
        llm_judge: Dict[str, Any] | None = None
        if use_judge:
            if self.llm_client is None:
                raise ValueError("LLM judge requested but no llm_client was configured.")
            llm_judge = self.judge_case(
                case_id,
                real_transcripts,
                simulated_transcripts,
                artifact,
                {
                    "real": summarize_features(real_features),
                    "simulated": summarize_features(sim_features),
                    "rule_behavioral_realism": behavior,
                    "rule_goal_alignment": goal,
                    "rule_overly_cooperative": cooperation,
                },
            )
            behavior = apply_behavior_judge(behavior, llm_judge)
            goal = apply_goal_judge(goal, llm_judge)
            cooperation = apply_cooperation_judge(cooperation, llm_judge)
        overall = round(
            weighted_average(
                {
                    "behavioral_realism": behavior["score"],
                    "goal_alignment": goal["score"],
                    "anti_overcooperation": cooperation["score"],
                },
                {"behavioral_realism": 0.45, "goal_alignment": 0.35, "anti_overcooperation": 0.20},
            ),
            3,
        )
        return {
            "case_id": case_id,
            "real_session_count": len(real_transcripts),
            "simulated_session_count": len(simulated_transcripts),
            "overall_score": overall,
            "behavioral_realism": behavior,
            "goal_alignment": goal,
            "overly_cooperative": cooperation,
            "llm_judge": llm_judge,
            "real_feature_summary": summarize_features(real_features),
            "simulated_feature_summary": summarize_features(sim_features),
        }

    def judge_case(
        self,
        case_id: str,
        real_transcripts: list[Dict[str, Any]],
        simulated_transcripts: list[Dict[str, Any]],
        artifact: KnowledgeRoadmapArtifact | None,
        feature_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.llm_client is None:
            raise ValueError("LLM judge requires llm_client")
        roadmap = model_to_dict(artifact.roadmap) if artifact else {}
        payload = self.llm_client.generate_json(
            SIMULATOR_EVAL_JUDGE_SYSTEM,
            SIMULATOR_EVAL_JUDGE_USER.format(
                case_id=case_id,
                real_transcripts_json=dumps_json(sample_transcripts(real_transcripts)),
                simulated_transcripts_json=dumps_json(sample_transcripts(simulated_transcripts)),
                roadmap_json=dumps_json(roadmap),
                feature_summary_json=dumps_json(feature_summary),
            ),
            schema_name="SimulatorEvalJudge",
        )
        return normalize_eval_judge_payload(payload)

    def write_outputs(self, reports: list[Dict[str, Any]]) -> list[Path]:
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = self.eval_dir / "simulator_eval.jsonl"
        md_path = self.eval_dir / "summary.md"
        write_jsonl(jsonl_path, reports)
        md_path.write_text(render_eval_summary(reports), encoding="utf-8")
        for report in reports:
            case_path = self.eval_dir / f"{safe_filename(report['case_id'])}.md"
            case_path.write_text(render_case_report(report), encoding="utf-8")
        return [jsonl_path, md_path]


def select_real_dialogues(dialogues: list[HistoricalDialogue], case_id: str) -> list[HistoricalDialogue]:
    selected = []
    for dialogue in dialogues:
        ids = expand_case_ids(dialogue.case_id) | expand_case_ids(dialogue.final_case_id)
        if case_id in ids:
            selected.append(dialogue)
    return selected


def collect_real_case_ids(dialogues: list[HistoricalDialogue]) -> list[str]:
    case_ids: list[str] = []
    seen: set[str] = set()
    for dialogue in dialogues:
        for case_id in sorted(expand_case_ids(dialogue.case_id) | expand_case_ids(dialogue.final_case_id)):
            if case_id not in seen:
                seen.add(case_id)
                case_ids.append(case_id)
    return case_ids


def expand_case_ids(value: str | None) -> set[str]:
    if not value:
        return set()
    normalized = str(value).replace(",", "\n").replace("，", "\n")
    return {item.strip() for item in normalized.splitlines() if item.strip()}


def historical_dialogues_to_transcripts(dialogues: list[HistoricalDialogue]) -> list[Dict[str, Any]]:
    transcripts = []
    for dialogue in dialogues:
        messages = [
            {"role": turn.speaker, "content": turn.text, "turn": index + 1}
            for index, turn in enumerate(dialogue.turns)
            if turn.speaker in {"user", "assistant"} and turn.text
        ]
        transcripts.append(
            {
                "case_id": dialogue.case_id or dialogue.final_case_id or "",
                "dialogue_id": dialogue.dialogue_id,
                "turn_count": len(messages),
                "solution_status": "resolved" if dialogue.resolved else "",
                "stop_reason": "",
                "messages": messages,
            }
        )
    return transcripts


def load_simulated_sessions(output_dir: Path, case_id: str) -> list[Dict[str, Any]]:
    logs = [record for record in read_simulation_logs(output_dir / "simulation_logs.jsonl") if record["case_id"] == case_id]
    sessions = split_logs_into_sessions(logs)
    return [build_transcript(case_id, session) for session in sessions if session]


def split_logs_into_sessions(logs: list[Dict[str, Any]]) -> list[list[Dict[str, Any]]]:
    sessions: list[list[Dict[str, Any]]] = []
    current: list[Dict[str, Any]] = []
    previous_turn = 0
    for record in sorted(logs, key=lambda item: str(item.get("timestamp") or "")):
        turn = int((record.get("output") or {}).get("turn") or 0)
        if current and (turn <= previous_turn or turn == 1):
            sessions.append(current)
            current = []
        current.append(record)
        previous_turn = turn
    if current:
        sessions.append(current)
    return sessions


def extract_features(transcript: Dict[str, Any]) -> Dict[str, Any]:
    messages = transcript.get("messages") or []
    user_texts = [str(item.get("content") or "") for item in messages if item.get("role") == "user"]
    assistant_texts = [str(item.get("content") or "") for item in messages if item.get("role") == "assistant"]
    acts = [classify_user_act(text) for text in user_texts]
    act_dist = distribution(acts, all_user_acts())
    return {
        "turn_count": len(messages),
        "user_turn_count": len(user_texts),
        "assistant_turn_count": len(assistant_texts),
        "avg_user_chars": mean([len(text) for text in user_texts]),
        "user_chars": [len(text) for text in user_texts],
        "user_question_rate": safe_rate(sum(1 for text in user_texts if contains_any(text, USER_QUESTION_MARKERS)), len(user_texts)),
        "act_distribution": act_dist,
        "accept_rate": act_dist["accept"],
        "reject_rate": act_dist["reject"],
        "clarification_rate": act_dist["clarify"],
        "confusion_rate": act_dist["confusion"],
        "frustration_rate": act_dist["frustration"],
        "action_feedback_rate": act_dist["action_feedback"],
        "provide_info_rate": act_dist["provide_info"],
        "off_topic_rate": act_dist["off_topic"],
    }


def classify_user_act(text: str) -> str:
    if contains_any(text, OFF_TOPIC_MARKERS):
        return "off_topic"
    if contains_any(text, FRUSTRATION_MARKERS):
        return "frustration"
    if contains_any(text, CONFUSION_MARKERS):
        return "confusion"
    if contains_any(text, REJECT_MARKERS):
        return "reject"
    if contains_any(text, USER_QUESTION_MARKERS):
        return "clarify"
    if contains_any(text, ACTION_MARKERS):
        return "action_feedback"
    if contains_any(text, ACCEPT_MARKERS):
        return "accept"
    if contains_any(text, INFO_MARKERS):
        return "provide_info"
    return "other"


def all_user_acts() -> list[str]:
    return ["accept", "reject", "clarify", "confusion", "frustration", "action_feedback", "provide_info", "off_topic", "other"]


def behavioral_realism(real_features: list[Dict[str, Any]], sim_features: list[Dict[str, Any]]) -> Dict[str, Any]:
    real_acts = average_distribution([item["act_distribution"] for item in real_features], all_user_acts())
    sim_acts = average_distribution([item["act_distribution"] for item in sim_features], all_user_acts())
    jsd = jensen_shannon(real_acts, sim_acts, all_user_acts())
    turn_w = wasserstein([item["user_turn_count"] for item in real_features], [item["user_turn_count"] for item in sim_features])
    char_w = wasserstein(flatten([item["user_chars"] for item in real_features]), flatten([item["user_chars"] for item in sim_features]))
    turn_score = distance_score(turn_w, scale=max(1.0, mean([item["user_turn_count"] for item in real_features])))
    char_score = distance_score(char_w, scale=max(1.0, mean(flatten([item["user_chars"] for item in real_features]))))
    act_score = 1.0 - min(1.0, jsd)
    usi = user_sim_index(real_features, sim_features)
    score = round(mean([turn_score, char_score, act_score, usi["score"]]), 3)
    return {
        "score": score,
        "session_length_wasserstein": round(turn_w, 3),
        "words_per_turn_wasserstein": round(char_w, 3),
        "dialogue_act_jsd": round(jsd, 3),
        "distribution_alignment_score": round(mean([turn_score, char_score, act_score]), 3),
        "user_sim_index": usi,
    }


def user_sim_index(real_features: list[Dict[str, Any]], sim_features: list[Dict[str, Any]]) -> Dict[str, Any]:
    style = pair_score(real_features, sim_features, "avg_user_chars")
    information = mean(
        [
            pair_score(real_features, sim_features, "provide_info_rate"),
            pair_score(real_features, sim_features, "action_feedback_rate"),
        ]
    )
    clarification = mean(
        [
            pair_score(real_features, sim_features, "clarification_rate"),
            pair_score(real_features, sim_features, "user_question_rate"),
        ]
    )
    error_response = mean(
        [
            pair_score(real_features, sim_features, "confusion_rate"),
            pair_score(real_features, sim_features, "frustration_rate"),
            pair_score(real_features, sim_features, "reject_rate"),
        ]
    )
    return {
        "score": round(mean([style, information, clarification, error_response]), 3),
        "communication_style": round(style, 3),
        "information_pattern": round(information, 3),
        "clarification_behavior": round(clarification, 3),
        "error_reaction": round(error_response, 3),
    }


def goal_alignment(
    case_id: str,
    simulated_transcripts: list[Dict[str, Any]],
    sim_features: list[Dict[str, Any]],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    boundary_scores = []
    solved = 0
    for transcript in simulated_transcripts:
        user_texts = [str(item.get("content") or "") for item in transcript.get("messages") or [] if item.get("role") == "user"]
        boundary = knowledge_boundary_stats(user_texts, artifact)
        boundary_scores.append(1.0 - boundary["boundary_violation_rate"])
        if transcript.get("solution_status") in {"solved", "accepted", "resolved"} or transcript.get("stop_reason") in {"solved", "solution_accepted"}:
            solved += 1
    goal_persistence = 1.0 - mean([item["off_topic_rate"] for item in sim_features])
    boundary_score = mean(boundary_scores) if boundary_scores else 0.0
    solved_rate = safe_rate(solved, len(simulated_transcripts))
    score = round(mean([goal_persistence, boundary_score, solved_rate]), 3)
    return {
        "score": score,
        "target_case_id": case_id,
        "goal_persistence_score": round(goal_persistence, 3),
        "knowledge_boundary_score": round(boundary_score, 3),
        "simulated_solved_rate": round(solved_rate, 3),
    }


def overly_cooperative(real_features: list[Dict[str, Any]], sim_features: list[Dict[str, Any]]) -> Dict[str, Any]:
    real_accept = mean([item["accept_rate"] for item in real_features])
    sim_accept = mean([item["accept_rate"] for item in sim_features])
    real_resistance = mean([resistance_rate(item) for item in real_features])
    sim_resistance = mean([resistance_rate(item) for item in sim_features])
    excess_accept = max(0.0, sim_accept - real_accept)
    missing_resistance = max(0.0, real_resistance - sim_resistance)
    penalty = min(1.0, excess_accept + missing_resistance)
    return {
        "score": round(1.0 - penalty, 3),
        "real_accept_rate": round(real_accept, 3),
        "simulated_accept_rate": round(sim_accept, 3),
        "real_resistance_rate": round(real_resistance, 3),
        "simulated_resistance_rate": round(sim_resistance, 3),
        "excess_accept_penalty": round(excess_accept, 3),
        "missing_resistance_penalty": round(missing_resistance, 3),
    }


def apply_behavior_judge(rule_behavior: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    behavior = dict(rule_behavior)
    judge_behavior_score = score_value(judge.get("behavioral_realism_score"), rule_behavior["score"])
    judge_usi = normalize_user_sim_index(judge.get("user_sim_index"))
    behavior["rule_score"] = rule_behavior["score"]
    behavior["llm_behavioral_realism_score"] = judge_behavior_score
    behavior["user_sim_index"] = judge_usi
    behavior["score"] = round(mean([rule_behavior["distribution_alignment_score"], judge_behavior_score, judge_usi["score"]]), 3)
    return behavior


def apply_goal_judge(rule_goal: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    goal = dict(rule_goal)
    llm_goal_score = score_value(judge.get("goal_alignment_score"), rule_goal["score"])
    goal["rule_score"] = rule_goal["score"]
    goal["llm_goal_alignment_score"] = llm_goal_score
    goal["score"] = round(mean([rule_goal["knowledge_boundary_score"], rule_goal["goal_persistence_score"], llm_goal_score]), 3)
    return goal


def apply_cooperation_judge(rule_cooperation: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    cooperation = dict(rule_cooperation)
    llm_score = score_value(judge.get("anti_overcooperation_score"), rule_cooperation["score"])
    cooperation["rule_score"] = rule_cooperation["score"]
    cooperation["llm_anti_overcooperation_score"] = llm_score
    cooperation["overcooperation_risk"] = str(judge.get("overcooperation_risk") or "")
    cooperation["score"] = round(mean([rule_cooperation["score"], llm_score]), 3)
    return cooperation


def normalize_eval_judge_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_sim_index_payload = normalize_user_sim_index(payload.get("user_sim_index"))
    return {
        "behavioral_realism_score": score_value(payload.get("behavioral_realism_score"), user_sim_index_payload["score"]),
        "user_sim_index": user_sim_index_payload,
        "goal_alignment_score": score_value(payload.get("goal_alignment_score"), 0.0),
        "anti_overcooperation_score": score_value(payload.get("anti_overcooperation_score"), 0.0),
        "overcooperation_risk": normalize_risk(payload.get("overcooperation_risk")),
        "reasons": normalize_string_list(payload.get("reasons")),
    }


def normalize_user_sim_index(value: Any) -> Dict[str, float]:
    payload = value if isinstance(value, dict) else {}
    fields = {
        "communication_style": score_value(payload.get("communication_style"), 0.0),
        "information_pattern": score_value(payload.get("information_pattern"), 0.0),
        "clarification_behavior": score_value(payload.get("clarification_behavior"), 0.0),
        "error_reaction": score_value(payload.get("error_reaction"), 0.0),
    }
    score = score_value(payload.get("score"), mean(fields.values()))
    return {"score": score, **fields}


def score_value(value: Any, default: float = 0.0) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return round(max(0.0, min(1.0, float(default))), 3)


def normalize_risk(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"low", "medium", "high"} else "medium"


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:8]
    text = str(value or "").strip()
    return [text] if text else []


def sample_transcripts(transcripts: list[Dict[str, Any]], limit: int = 3) -> list[Dict[str, Any]]:
    return [compact_transcript(transcript) for transcript in transcripts[:limit]]


def compact_transcript(transcript: Dict[str, Any]) -> Dict[str, Any]:
    messages = transcript.get("messages") or []
    return {
        "dialogue_id": transcript.get("dialogue_id", ""),
        "case_id": transcript.get("case_id", ""),
        "turn_count": transcript.get("turn_count", len(messages)),
        "solution_status": transcript.get("solution_status", ""),
        "messages": messages[:16],
    }


def resistance_rate(features: Dict[str, Any]) -> float:
    return features["reject_rate"] + features["clarification_rate"] + features["confusion_rate"] + features["frustration_rate"]


def summarize_features(features: list[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "avg_user_turn_count": round(mean([item["user_turn_count"] for item in features]), 3),
        "avg_user_chars": round(mean([item["avg_user_chars"] for item in features]), 3),
        "avg_user_question_rate": round(mean([item["user_question_rate"] for item in features]), 3),
        "avg_act_distribution": {
            key: round(value, 3)
            for key, value in average_distribution([item["act_distribution"] for item in features], all_user_acts()).items()
        },
    }


def render_eval_summary(reports: list[Dict[str, Any]]) -> str:
    lines = [
        "# Simulator Evaluation Summary",
        "",
        "| case_id | real | simulated | overall | behavioral | goal | anti-overcoop |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for report in reports:
        lines.append(
            "| {case_id} | {real} | {sim} | {overall:.3f} | {behavior:.3f} | {goal:.3f} | {coop:.3f} |".format(
                case_id=report["case_id"],
                real=report["real_session_count"],
                sim=report["simulated_session_count"],
                overall=report["overall_score"],
                behavior=report["behavioral_realism"]["score"],
                goal=report["goal_alignment"]["score"],
                coop=report["overly_cooperative"]["score"],
            )
        )
    lines.append("")
    if any(report.get("llm_judge") for report in reports):
        lines.append("Scores combine rule-based distribution metrics with LLM judge scores for semantic realism, goal alignment, and over-cooperation.")
    else:
        lines.append("Scores are rule-based offline estimates. Re-run with --judge to add LLM semantic judging for realism, goal alignment, and over-cooperation.")
    return "\n".join(lines) + "\n"


def render_case_report(report: Dict[str, Any]) -> str:
    behavior = report["behavioral_realism"]
    goal = report["goal_alignment"]
    coop = report["overly_cooperative"]
    lines = [
        f"# Simulator Evaluation {report['case_id']}",
        "",
        f"- real_session_count: {report['real_session_count']}",
        f"- simulated_session_count: {report['simulated_session_count']}",
        f"- overall_score: {report['overall_score']:.3f}",
        "",
        "## Behavioral Realism",
        "",
        f"- score: {behavior['score']:.3f}",
        f"- rule_score: {behavior.get('rule_score', behavior['score'])}",
        f"- llm_behavioral_realism_score: {behavior.get('llm_behavioral_realism_score', '')}",
        f"- dialogue_act_jsd: {behavior['dialogue_act_jsd']:.3f}",
        f"- session_length_wasserstein: {behavior['session_length_wasserstein']:.3f}",
        f"- words_per_turn_wasserstein: {behavior['words_per_turn_wasserstein']:.3f}",
        f"- user_sim_index: {behavior['user_sim_index']['score']:.3f}",
        "",
        "## Goal Alignment",
        "",
        f"- score: {goal['score']:.3f}",
        f"- rule_score: {goal.get('rule_score', goal['score'])}",
        f"- llm_goal_alignment_score: {goal.get('llm_goal_alignment_score', '')}",
        f"- goal_persistence_score: {goal['goal_persistence_score']:.3f}",
        f"- knowledge_boundary_score: {goal['knowledge_boundary_score']:.3f}",
        f"- simulated_solved_rate: {goal['simulated_solved_rate']:.3f}",
        "",
        "## Overly Cooperative",
        "",
        f"- anti_overcooperation_score: {coop['score']:.3f}",
        f"- rule_score: {coop.get('rule_score', coop['score'])}",
        f"- llm_anti_overcooperation_score: {coop.get('llm_anti_overcooperation_score', '')}",
        f"- overcooperation_risk: {coop.get('overcooperation_risk', '')}",
        f"- real_accept_rate: {coop['real_accept_rate']:.3f}",
        f"- simulated_accept_rate: {coop['simulated_accept_rate']:.3f}",
        f"- real_resistance_rate: {coop['real_resistance_rate']:.3f}",
        f"- simulated_resistance_rate: {coop['simulated_resistance_rate']:.3f}",
        "",
    ]
    if report.get("llm_judge"):
        lines.extend(["## LLM Judge Reasons", ""])
        lines.extend(f"- {reason}" for reason in report["llm_judge"].get("reasons", []))
        lines.append("")
    lines.extend(
        [
            "## Feature Summary",
            "",
            "```json",
            json.dumps(
                {
                    "real": report["real_feature_summary"],
                    "simulated": report["simulated_feature_summary"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker in text for marker in markers)


def distribution(values: list[str], labels: list[str]) -> Dict[str, float]:
    total = len(values)
    return {label: safe_rate(values.count(label), total) for label in labels}


def average_distribution(distributions: list[Dict[str, float]], labels: list[str]) -> Dict[str, float]:
    if not distributions:
        return {label: 0.0 for label in labels}
    return {label: mean([item.get(label, 0.0) for item in distributions]) for label in labels}


def jensen_shannon(p: Dict[str, float], q: Dict[str, float], labels: list[str]) -> float:
    p_values = [max(0.0, p.get(label, 0.0)) for label in labels]
    q_values = [max(0.0, q.get(label, 0.0)) for label in labels]
    p_total = sum(p_values) or 1.0
    q_total = sum(q_values) or 1.0
    p_values = [value / p_total for value in p_values]
    q_values = [value / q_total for value in q_values]
    m_values = [(p_value + q_value) / 2 for p_value, q_value in zip(p_values, q_values)]
    return (kl_divergence(p_values, m_values) + kl_divergence(q_values, m_values)) / 2


def kl_divergence(p_values: list[float], q_values: list[float]) -> float:
    total = 0.0
    for p_value, q_value in zip(p_values, q_values):
        if p_value <= 0:
            continue
        total += p_value * math.log(p_value / max(q_value, 1e-12), 2)
    return total


def wasserstein(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    left_sorted = sorted(float(item) for item in left)
    right_sorted = sorted(float(item) for item in right)
    n = max(len(left_sorted), len(right_sorted))
    distances = []
    for index in range(n):
        left_index = min(len(left_sorted) - 1, round(index * (len(left_sorted) - 1) / max(1, n - 1)))
        right_index = min(len(right_sorted) - 1, round(index * (len(right_sorted) - 1) / max(1, n - 1)))
        distances.append(abs(left_sorted[left_index] - right_sorted[right_index]))
    return mean(distances)


def pair_score(real_features: list[Dict[str, Any]], sim_features: list[Dict[str, Any]], key: str) -> float:
    real_value = mean([float(item.get(key) or 0.0) for item in real_features])
    sim_value = mean([float(item.get(key) or 0.0) for item in sim_features])
    return distance_score(abs(real_value - sim_value), scale=max(1.0, abs(real_value)))


def distance_score(distance: float, scale: float) -> float:
    return max(0.0, 1.0 - min(1.0, distance / max(scale, 1e-9)))


def weighted_average(values: Dict[str, float], weights: Dict[str, float]) -> float:
    total_weight = sum(weights.values()) or 1.0
    return sum(values[key] * weights.get(key, 0.0) for key in values) / total_weight


def mean(values: Iterable[float]) -> float:
    items = [float(value) for value in values]
    return statistics.mean(items) if items else 0.0


def safe_rate(count: float, total: float, default: float = 0.0) -> float:
    return float(count) / float(total) if total else default


def flatten(values: Iterable[Iterable[float]]) -> list[float]:
    return [item for group in values for item in group]
