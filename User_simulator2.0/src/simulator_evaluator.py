from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.behavior_mining.dialogue_loader import load_dialogues
from src.evaluator_metrics import information_rhythm_stats, opening_realism_stats
from src.llm.llm_client import LLMClient
from src.metrics_exporter import knowledge_boundary_stats
from src.review_exporter import safe_filename
from src.schemas import HistoricalDialogue, KnowledgeRoadmapArtifact, model_to_dict
from src.transcript_exporter import build_transcript, read_simulation_logs
from src.utils.json_utils import dumps_json
from src.utils.jsonl import write_jsonl


USER_QUESTION_MARKERS = ("?", "?", "吗", "怎么", "如何", "为啥", "为什么", "能不能", "可以不")
ACCEPT_MARKERS = ("好的", "好", "可以", "行", "嗯", "谢谢", "感谢", "已解决", "解决了", "没问题")
REJECT_MARKERS = ("不行", "不可以", "没有用", "还是不行", "没解决", "不对", "不是", "不需要")
CONFUSION_MARKERS = ("不懂", "不会", "不知道", "没看懂", "看不明白", "不太清楚", "找不到", "没找到")
FRUSTRATION_MARKERS = ("急", "麻烦", "烦", "一直", "怎么还", "崩溃", "影响", "耽误")
ACTION_MARKERS = ("试了", "看了", "打开", "重启", "点击", "操作", "登录", "升级", "安装", "配置")
INFO_MARKERS = ("报错", "提示", "显示", "系统", "电脑", "账号", "邮箱", "文件", "版本", "网络")
OFF_TOPIC_MARKERS = ("天气", "吃饭", "旅游", "电影", "小说", "股票", "游戏")


SIMULATOR_EVAL_JUDGE_SYSTEM = """你是企业 IT 客服用户模拟器的评测专家。
你会对比真实用户对话和模拟用户对话,只评估"模拟用户"的质量。
请只输出合法 JSON,不要输出解释性正文。"""


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

请从以下三个核心维度评估模拟用户的真实度和合理性（0.0 到 1.0,越高越好）:

1. 行为真实度 (Behavioral Realism)
   重点关注:**初始提问像不像真实用户**
   - 初始提问的自然度:是否像真实员工的表达方式（不过于正式、不过于简略）
   - 初始提问与目标案例表面问题的相似度:是否准确描述了问题现象
   - 整体交流风格:是否像真实用户的语言风格和节奏
   - 澄清/困惑/错误反应:遇到问题时是否像真实用户一样反应

   评分标准:
   - 0.8-1.0:非常真实,初始提问自然且准确,整体交流风格与真实用户高度一致
   - 0.5-0.7:基本真实,初始提问合理但有一些不自然之处
   - 0.2-0.4:不够真实,初始提问过于正式或过于简略,交流风格有明显差异
   - 0.0-0.1:完全不真实,初始提问像机器生成或明显违背真实用户行为

2. 目标对齐 (Goal Alignment)
   重点关注:**后续对话的信息输出是否忠实于初始目标**
   - 目标坚持度:是否始终围绕初始问题,没有被带偏
   - 信息输出时机:是否在被追问时才透露诊断信息,而不是主动倾倒
   - 信息输出准确性:是否与roadmap中的事实一致,没有幻觉或偏离
   - 能否走到解决:是否能在合理轮次内接受有效解决方案

   评分标准:
   - 0.8-1.0:高度对齐,始终围绕目标,信息输出时机准确,能够走到解决
   - 0.5-0.7:基本对齐,大部分时间围绕目标,信息输出基本合理
   - 0.2-0.4:对齐度低,容易跑题或信息输出节奏混乱
   - 0.0-0.1:完全不对齐,严重偏离目标或信息输出完全不合理

3. 过度合作 (Overly Cooperative)
   重点关注:**整体是否过于配合,缺少真实用户的阻力**
   - 配合度对比:是否比真实用户更容易接受方案
   - 阻力表现:是否缺少真实用户的困惑、犹豫、追问、挫败感
   - 质疑和拒绝:是否缺乏合理的质疑和拒绝行为
   - 逼真度:是否让待测系统过于轻松过关

   评分标准:
   - 0.8-1.0:逼真,表现出合理的困惑、犹豫、追问,不会过于配合
   - 0.5-0.7:基本逼真,有一些真实用户的阻力表现
   - 0.2-0.4:过度配合,缺少真实的困惑和质疑
   - 0.0-0.1:严重过度配合,完全不像真实用户的行为

返回 JSON:
{{
  "behavioral_realism_score": 0.0,
  "goal_alignment_score": 0.0,
  "anti_overcooperation_score": 0.0,
  "overall_score": 0.0,
  "analysis": {{
    "behavioral_realism_analysis": "...",
    "goal_alignment_analysis": "...",
    "overcooperation_analysis": "..."
  }},
  "reasons": ["...", "..."]
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

        # NEW: Enhanced evaluation metrics
        enhanced = enhanced_evaluation(case_id, simulated_transcripts, artifact)

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
                    "enhanced_metrics": enhanced,
                },
            )
            behavior = apply_behavior_judge(behavior, llm_judge)
            goal = apply_goal_judge(goal, llm_judge)
            cooperation = apply_cooperation_judge(cooperation, llm_judge)

        trajectory = trajectory_state_metrics(simulated_transcripts, artifact)
        goal = apply_trajectory_to_goal(goal, trajectory)
        cooperation = apply_trajectory_to_cooperation(cooperation, trajectory)

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
            "trajectory_state": trajectory,
            "enhanced_evaluation": enhanced,  # NEW: Enhanced metrics
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
    normalized = str(value).replace(",", "\n").replace(",", "\n")
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


def trajectory_state_metrics(
    simulated_transcripts: list[Dict[str, Any]],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    if not simulated_transcripts:
        return empty_trajectory_state()

    rows = [trajectory_state_for_session(transcript, artifact) for transcript in simulated_transcripts]
    target_solution_hit_rate = mean([row["target_solution_hit"] for row in rows])
    accepted_target_rate = mean([row["accepted_target"] for row in rows])
    wrong_acceptance_rate = mean([row["wrong_acceptance"] for row in rows])
    leakage_rate = mean([row["knowledge_leakage"] for row in rows])
    action_feedback_use_rate = mean([row["action_feedback_used"] for row in rows])
    repeated_try_rate = mean([row["repeated_try_without_feedback"] for row in rows])
    no_effective_stop_rate = mean([row["no_effective_stop"] for row in rows])

    solution_score = mean([target_solution_hit_rate, accepted_target_rate])
    boundary_score = 1.0 - leakage_rate
    action_feedback_score = 1.0 - min(1.0, max(0.0, repeated_try_rate - action_feedback_use_rate))
    failure_handling_score = 1.0 - wrong_acceptance_rate
    trajectory_score = weighted_average(
        {
            "solution": solution_score,
            "boundary": boundary_score,
            "action_feedback": action_feedback_score,
            "failure_handling": failure_handling_score,
        },
        {"solution": 0.35, "boundary": 0.30, "action_feedback": 0.20, "failure_handling": 0.15},
    )
    return {
        "score": round(trajectory_score, 3),
        "target_solution_hit_rate": round(target_solution_hit_rate, 3),
        "accepted_target_rate": round(accepted_target_rate, 3),
        "wrong_acceptance_rate": round(wrong_acceptance_rate, 3),
        "knowledge_leakage_rate": round(leakage_rate, 3),
        "action_feedback_use_rate": round(action_feedback_use_rate, 3),
        "repeated_try_without_feedback_rate": round(repeated_try_rate, 3),
        "no_effective_stop_rate": round(no_effective_stop_rate, 3),
        "session_details": rows,
    }


def empty_trajectory_state() -> Dict[str, Any]:
    return {
        "score": 0.0,
        "target_solution_hit_rate": 0.0,
        "accepted_target_rate": 0.0,
        "wrong_acceptance_rate": 0.0,
        "knowledge_leakage_rate": 0.0,
        "action_feedback_use_rate": 0.0,
        "repeated_try_without_feedback_rate": 0.0,
        "no_effective_stop_rate": 0.0,
        "session_details": [],
    }


def trajectory_state_for_session(
    transcript: Dict[str, Any],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    messages = transcript.get("messages") or []
    user_texts = [str(item.get("content") or "") for item in messages if item.get("role") == "user"]
    assistant_texts = [str(item.get("content") or "") for item in messages if item.get("role") == "assistant"]
    user_joined = "\n".join(user_texts)
    assistant_joined = "\n".join(assistant_texts)
    target_solution_hit = bool(transcript_solution_accepted(transcript))
    solution_mentioned_by_assistant = False
    solution_leaked_by_user = False
    forbidden_leaked_by_user = False

    if artifact:
        solution_contents = [point.content for point in artifact.roadmap.solution_points]
        solution_mentioned_by_assistant = any(
            text_contains_content_loose(assistant_joined, content) for content in solution_contents
        )
        solution_leaked_by_user = any(text_contains_content_loose(user_joined, content) for content in solution_contents)
        forbidden_leaked_by_user = any(
            text_contains_content_loose(user_joined, content) for content in artifact.roadmap.forbidden_content
        )
        target_solution_hit = target_solution_hit or solution_mentioned_by_assistant

    accepted_target = bool(transcript_solution_accepted(transcript)) and target_solution_hit
    wrong_acceptance = has_acceptance(user_texts) and not target_solution_hit
    action_feedback_used = any(classify_user_act(text) == "action_feedback" for text in user_texts)
    repeated_try_without_feedback = has_repeated_try_without_feedback(user_texts)
    no_effective_stop = transcript.get("stop_reason") == "assistant_unable_to_provide_effective_solution"

    return {
        "target_solution_hit": 1.0 if target_solution_hit else 0.0,
        "accepted_target": 1.0 if accepted_target else 0.0,
        "wrong_acceptance": 1.0 if wrong_acceptance else 0.0,
        "knowledge_leakage": 1.0 if (solution_leaked_by_user or forbidden_leaked_by_user) else 0.0,
        "action_feedback_used": 1.0 if action_feedback_used else 0.0,
        "repeated_try_without_feedback": 1.0 if repeated_try_without_feedback else 0.0,
        "no_effective_stop": 1.0 if no_effective_stop else 0.0,
    }


def transcript_solution_accepted(transcript: Dict[str, Any]) -> bool:
    return transcript.get("solution_status") in {"solved", "accepted", "resolved", "solution_accepted"} or transcript.get(
        "stop_reason"
    ) in {"solved", "solution_accepted", "accepted_actionable_solution"}


def has_acceptance(user_texts: list[str]) -> bool:
    return any(contains_any(text, ACCEPT_MARKERS) for text in user_texts)


def has_repeated_try_without_feedback(user_texts: list[str]) -> bool:
    try_like = [text for text in user_texts if "试" in text or "操作" in text or "按" in text]
    feedback_like = [text for text in user_texts if classify_user_act(text) == "action_feedback"]
    return len(try_like) >= 2 and not feedback_like


def text_contains_content_loose(text: str, content: str) -> bool:
    if not text or not content:
        return False
    normalized_content = str(content).strip().lower()
    normalized_text = str(text).strip().lower()
    if len(normalized_content) >= 4 and normalized_content in normalized_text:
        return True
    content_chars = {char for char in normalized_content if "\u4e00" <= char <= "\u9fff"}
    text_chars = {char for char in normalized_text if "\u4e00" <= char <= "\u9fff"}
    if len(content_chars) < 4:
        return False
    return len(content_chars & text_chars) / len(content_chars) >= 0.7


def apply_trajectory_to_goal(goal: Dict[str, Any], trajectory: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(goal)
    updated["pre_trajectory_score"] = updated.get("score", 0.0)
    updated["trajectory_state_score"] = trajectory.get("score", 0.0)
    updated["score"] = round(
        weighted_average(
            {
                "semantic_goal": float(updated.get("score", 0.0)),
                "trajectory_state": float(trajectory.get("score", 0.0)),
            },
            {"semantic_goal": 0.65, "trajectory_state": 0.35},
        ),
        3,
    )
    return updated


def apply_trajectory_to_cooperation(cooperation: Dict[str, Any], trajectory: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(cooperation)
    wrong_acceptance_penalty = float(trajectory.get("wrong_acceptance_rate", 0.0))
    repeated_try_penalty = float(trajectory.get("repeated_try_without_feedback_rate", 0.0)) * 0.5
    updated["trajectory_overcooperation_penalty"] = round(min(1.0, wrong_acceptance_penalty + repeated_try_penalty), 3)
    updated["pre_trajectory_score"] = updated.get("score", 0.0)
    updated["score"] = round(max(0.0, float(updated.get("score", 0.0)) - updated["trajectory_overcooperation_penalty"] * 0.35), 3)
    return updated


def apply_behavior_judge(rule_behavior: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    behavior = dict(rule_behavior)
    judge_score = judge.get("behavioral_realism_score", 0.0)
    behavior["rule_score"] = rule_behavior.get("score", 0.0)
    behavior["llm_judge_score"] = judge_score
    behavior["score"] = round(fuse_rule_and_judge(rule_behavior.get("score", 0.0), judge_score), 3)
    return behavior


def apply_goal_judge(rule_goal: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    goal = dict(rule_goal)
    judge_score = judge.get("goal_alignment_score", 0.0)
    goal["rule_score"] = rule_goal.get("score", 0.0)
    goal["llm_judge_score"] = judge_score
    goal["score"] = round(fuse_rule_and_judge(rule_goal.get("score", 0.0), judge_score), 3)
    return goal


def apply_cooperation_judge(rule_cooperation: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    cooperation = dict(rule_cooperation)
    judge_score = judge.get("anti_overcooperation_score", 0.0)
    cooperation["rule_score"] = rule_cooperation.get("score", 0.0)
    cooperation["llm_judge_score"] = judge_score
    cooperation["score"] = round(fuse_rule_and_judge(rule_cooperation.get("score", 0.0), judge_score), 3)
    return cooperation


def fuse_rule_and_judge(rule_score: Any, judge_score: Any, judge_weight: float = 0.6) -> float:
    rule = score_value(rule_score, 0.0)
    judge = score_value(judge_score, rule)
    return weighted_average({"rule": rule, "judge": judge}, {"rule": 1.0 - judge_weight, "judge": judge_weight})


def normalize_eval_judge_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    # NEW: Simplified judge payload focusing on three core dimensions
    analysis = payload.get("analysis") or {}
    return {
        "behavioral_realism_score": score_value(payload.get("behavioral_realism_score"), 0.0),
        "goal_alignment_score": score_value(payload.get("goal_alignment_score"), 0.0),
        "anti_overcooperation_score": score_value(payload.get("anti_overcooperation_score"), 0.0),
        "overall_score": score_value(payload.get("overall_score"), 0.0),
        "behavioral_realism_analysis": str(analysis.get("behavioral_realism_analysis", "")),
        "goal_alignment_analysis": str(analysis.get("goal_alignment_analysis", "")),
        "overcooperation_analysis": str(analysis.get("overcooperation_analysis", "")),
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
        lines.append("Scores fuse rule-based metrics, LLM judge scores, and trajectory/state checks for semantic realism, goal alignment, and over-cooperation.")
    else:
        lines.append("Scores are rule-based offline estimates with trajectory/state checks. Re-run with --judge to add LLM semantic judging for realism, goal alignment, and over-cooperation.")
    return "\n".join(lines) + "\n"


def render_case_report(report: Dict[str, Any]) -> str:
    behavior = report["behavioral_realism"]
    goal = report["goal_alignment"]
    coop = report["overly_cooperative"]
    trajectory = report.get("trajectory_state", {})
    enhanced = report.get("enhanced_evaluation", {})
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
        f"- llm_judge_score: {behavior.get('llm_judge_score', '')}",
        f"- dialogue_act_jsd: {behavior['dialogue_act_jsd']:.3f}",
        f"- session_length_wasserstein: {behavior['session_length_wasserstein']:.3f}",
        f"- words_per_turn_wasserstein: {behavior['words_per_turn_wasserstein']:.3f}",
        f"- user_sim_index: {behavior['user_sim_index']['score']:.3f}",
        "",
        "## Goal Alignment",
        "",
        f"- score: {goal['score']:.3f}",
        f"- rule_score: {goal.get('rule_score', goal['score'])}",
        f"- llm_judge_score: {goal.get('llm_judge_score', '')}",
        f"- pre_trajectory_score: {goal.get('pre_trajectory_score', '')}",
        f"- trajectory_state_score: {goal.get('trajectory_state_score', '')}",
        f"- goal_persistence_score: {goal['goal_persistence_score']:.3f}",
        f"- knowledge_boundary_score: {goal['knowledge_boundary_score']:.3f}",
        f"- simulated_solved_rate: {goal['simulated_solved_rate']:.3f}",
        "",
        "## Overly Cooperative",
        "",
        f"- anti_overcooperation_score: {coop['score']:.3f}",
        f"- rule_score: {coop.get('rule_score', coop['score'])}",
        f"- llm_judge_score: {coop.get('llm_judge_score', '')}",
        f"- pre_trajectory_score: {coop.get('pre_trajectory_score', '')}",
        f"- trajectory_overcooperation_penalty: {coop.get('trajectory_overcooperation_penalty', '')}",
        f"- overcooperation_risk: {coop.get('overcooperation_risk', '')}",
        f"- real_accept_rate: {coop['real_accept_rate']:.3f}",
        f"- simulated_accept_rate: {coop['simulated_accept_rate']:.3f}",
        f"- real_resistance_rate: {coop['real_resistance_rate']:.3f}",
        f"- simulated_resistance_rate: {coop['simulated_resistance_rate']:.3f}",
        "",
        "## Trajectory State",
        "",
        f"- score: {trajectory.get('score', 0.0):.3f}",
        f"- target_solution_hit_rate: {trajectory.get('target_solution_hit_rate', 0.0):.3f}",
        f"- accepted_target_rate: {trajectory.get('accepted_target_rate', 0.0):.3f}",
        f"- wrong_acceptance_rate: {trajectory.get('wrong_acceptance_rate', 0.0):.3f}",
        f"- knowledge_leakage_rate: {trajectory.get('knowledge_leakage_rate', 0.0):.3f}",
        f"- action_feedback_use_rate: {trajectory.get('action_feedback_use_rate', 0.0):.3f}",
        f"- repeated_try_without_feedback_rate: {trajectory.get('repeated_try_without_feedback_rate', 0.0):.3f}",
        "",
        "## Enhanced Evaluation",
        "",
        f"- opening_realism_score: {enhanced.get('opening_realism_score', 0.0):.3f}",
        f"- information_rhythm_score: {enhanced.get('information_rhythm_score', 0.0):.3f}",
        "",
        "  **Opening Realism** evaluates the initial question quality:",
        "  - Semantic similarity with target case surface problem",
        "  - Naturalness of the opening statement",
        "  - Risk of information leak in the opening",
        "",
        "  **Information Rhythm** evaluates the information release pattern:",
        "  - Whether diagnostic info is revealed only when asked",
        "  - Logical sequence of information release",
        "  - Accuracy of released information against roadmap",
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


def enhanced_evaluation(
    case_id: str,
    simulated_transcripts: list[Dict[str, Any]],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    """
    Enhanced evaluation focusing on:
    1. Opening realism (initial question quality)
    2. Information rhythm (release pattern, timing, accuracy)
    """
    if not simulated_transcripts:
        return {
            "opening_realism_score": 0.0,
            "information_rhythm_score": 0.0,
        }

    # Aggregate across all simulated sessions
    opening_scores = []
    rhythm_scores = []

    for transcript in simulated_transcripts:
        opening_stats = opening_realism_stats(transcript, artifact)
        rhythm_stats = information_rhythm_stats(transcript, artifact)

        opening_scores.append(opening_stats.get("opening_realism_score", 0.0))
        rhythm_scores.append(rhythm_stats.get("information_rhythm_score", 0.0))

    avg_opening = mean(opening_scores) if opening_scores else 0.0
    avg_rhythm = mean(rhythm_scores) if rhythm_scores else 0.0

    return {
        "opening_realism_score": round(avg_opening, 3),
        "information_rhythm_score": round(avg_rhythm, 3),
    }
