from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.behavior_mining.dialogue_loader import load_dialogues
from src.evaluator_metrics import calculate_text_similarity, information_rhythm_stats, opening_realism_stats
from src.llm.llm_client import LLMClient
from src.metrics_exporter import knowledge_boundary_stats
from src.review_exporter import safe_filename
from src.schemas import HistoricalDialogue, KnowledgeRoadmapArtifact, model_to_dict
from src.transcript_exporter import build_transcript, read_simulation_logs, split_logs_into_sessions
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
DOMAIN_MARKERS = (
    "Outlook",
    "iLearning",
    "WeLink",
    "iDesk",
    "iAuth",
    "xGate",
    "VPN",
    "DNS",
    "WiFi",
    "IP",
    "Office",
    "Windows",
    "Mac",
    "证书",
    "权限",
    "内网",
    "域",
    "客户端",
    "服务器",
)
PERSONAL_CONTEXT_MARKERS = (
    "我",
    "我的",
    "这台",
    "电脑",
    "手机",
    "账号",
    "邮箱",
    "工号",
    "部门",
    "公司",
    "客户",
    "项目",
    "同事",
    "管理员",
)
UNCERTAINTY_MARKERS = ("好像", "可能", "大概", "不确定", "不太确定", "没印象", "记不清", "应该", "似乎")
ERROR_REPORT_MARKERS = ("报错", "错误", "失败", "异常", "打不开", "连不上", "无法", "不能", "不可用", "没反应")


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

请以 LLM judge 作为正式评测裁判,规则统计只作为 evidence。请从以下六个维度评估模拟用户的真实度和合理性（0.0 到 1.0,越高越好）:

1. 行为真实度 (Behavioral Realism)
   重点关注:**整体用户行为是否像真实员工**,初始提问相似度只是低权重辅助诊断项
   - 宏观行为分布:用户轮数、话语长度、接受/拒绝/澄清/困惑/动作反馈/信息提供的分布是否接近真实对话集合
   - 条件行为合理性:被追问信息时是否逐步提供事实,被要求动作时是否执行/追问/反馈结果,无效建议后是否会困惑或拒绝
   - User-Sim Index:交流风格、信息输出模式、澄清行为、错误/失败反应是否像真实用户
   - Opening Similarity:真实开头、模拟开头和 surface problem 是否对齐;该项主要反映 user-facing problem 拆解质量和初始意图对齐,不能作为模拟器总体质量的主要依据

   评分标准:
   - 0.8-1.0:非常真实,整体行为分布、条件反应和信息节奏都接近真实用户
   - 0.5-0.7:基本真实,大部分行为合理,但局部有过于规整或过度配合的问题
   - 0.2-0.4:不够真实,行为分布或条件反应有明显偏差
   - 0.0-0.1:完全不真实,像脚本执行或明显违背真实用户行为

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

4. RealSim-style 行为分布真实性
   重点关注:**模拟用户在八类行为维度上的分布是否像真实用户**
   - user_intent: 接受、拒绝、澄清、困惑、动作反馈、信息提供等意图分布
   - feedback: 是否像真实用户一样接受、拒绝、执行动作并反馈
   - emotion: 是否有合理困惑、挫败、犹豫,而不是机械配合
   - domain_specific_knowledge: 领域词使用是否自然,没有过度专业或完全缺失
   - personal_context_identity: 是否自然表达账号、设备、公司/部门等个人上下文
   - message_length: 长短和节奏是否接近真实对话
   - linguistic_attributes: 口语化、不确定表达、第一人称表达是否自然
   - errors: 报错/失败/异常反馈是否合理

5. C2ST 分布可区分性
   重点关注:**真实对话和模拟对话是否容易被区分**
   规则 C2ST 分数只是参考。你需要结合语义判断:
   - 如果模拟对话明显模板化、过于规整、风格单一,即使规则分高也应降低
   - 如果真实对话很噪声而模拟对话标准化,不要只因开头不完全相同就判低
   - 高分表示你认为两者整体分布难以区分

6. Leakage-aware Success 去泄漏成功
   重点关注:**模拟用户是否靠真实交互走到解决,而不是靠泄漏答案或错误接受**
   - target solution 被 assistant 命中后接受,且用户没有提前泄漏 solution/forbidden content,应高分
   - 用户提前说出答案、暴露 roadmap 内部诊断点、或接受无效方案,应低分
   - assistant 未能有效解决但用户自然结束,不一定是成功,但可作为真实失败处理

返回 JSON:
{{
  "behavioral_realism_score": 0.0,
  "goal_alignment_score": 0.0,
  "anti_overcooperation_score": 0.0,
  "realsim_behavior_score": 0.0,
  "c2st_realism_score": 0.0,
  "leakage_aware_success_score": 0.0,
  "overall_score": 0.0,
  "analysis": {{
    "behavioral_realism_analysis": "...",
    "goal_alignment_analysis": "...",
    "overcooperation_analysis": "...",
    "realsim_behavior_analysis": "...",
    "c2st_realism_analysis": "...",
    "leakage_aware_success_analysis": "..."
  }},
  "failure_modes": ["...", "..."],
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
        session_policy: str = "all",
    ) -> list[Path]:
        if session_policy not in {"all", "latest", "first"}:
            raise ValueError(f"Unsupported session_policy: {session_policy}")
        case_ids_list = [str(case_id) for case_id in case_ids]
        real_dialogues = load_dialogues(dialogues_path, dialogue_fields)
        reports = []
        for case_id in case_ids_list:
            real_transcripts = historical_dialogues_to_transcripts(select_real_dialogues(real_dialogues, case_id))
            simulated_transcripts = load_simulated_sessions(self.output_dir, case_id, session_policy=session_policy)
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
        opening = opening_similarity_alignment(real_transcripts, simulated_transcripts, artifact)
        behavior = behavioral_realism(real_features, sim_features, opening)
        goal = goal_alignment(case_id, simulated_transcripts, sim_features, artifact)
        cooperation = overly_cooperative(real_features, sim_features)

        # NEW: Enhanced evaluation metrics
        enhanced = enhanced_evaluation(case_id, simulated_transcripts, artifact)
        realsim = realsim_behavior_distribution(real_transcripts, simulated_transcripts)
        c2st = c2st_distribution_realism(real_transcripts, simulated_transcripts)
        trajectory = trajectory_state_metrics(simulated_transcripts, artifact)
        leakage_success = leakage_aware_success_metrics(trajectory)
        goal = apply_trajectory_to_goal(goal, trajectory)
        cooperation = apply_trajectory_to_cooperation(cooperation, trajectory)

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
                    "opening_similarity_alignment": opening,
                    "trajectory_state": trajectory,
                    "realsim_behavior_distribution": realsim,
                    "c2st_distribution_realism": c2st,
                    "leakage_aware_success": leakage_success,
                },
            )
            behavior = apply_behavior_judge(behavior, llm_judge)
            goal = apply_goal_judge(goal, llm_judge)
            cooperation = apply_cooperation_judge(cooperation, llm_judge)
            realsim = apply_realsim_judge(realsim, llm_judge)
            c2st = apply_c2st_judge(c2st, llm_judge)
            leakage_success = apply_leakage_success_judge(leakage_success, llm_judge)

        overall = final_overall_score(behavior, goal, cooperation, llm_judge)
        return {
            "case_id": case_id,
            "real_session_count": len(real_transcripts),
            "simulated_session_count": len(simulated_transcripts),
            "evaluation_mode": "llm_judge_primary" if use_judge else "diagnostic_only_rule_based",
            "overall_score": overall,
            "behavioral_realism": behavior,
            "goal_alignment": goal,
            "overly_cooperative": cooperation,
            "trajectory_state": trajectory,
            "leakage_aware_success": leakage_success,
            "realsim_behavior_distribution": realsim,
            "c2st_distribution_realism": c2st,
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


def load_simulated_sessions(output_dir: Path, case_id: str, session_policy: str = "all") -> list[Dict[str, Any]]:
    logs = [record for record in read_simulation_logs(output_dir / "simulation_logs.jsonl") if record["case_id"] == case_id]
    sessions = split_logs_into_sessions(logs)
    selected_sessions = select_sessions_by_policy(sessions, session_policy)
    return [build_transcript(case_id, session) for session in selected_sessions if session]


def select_sessions_by_policy(sessions: list[list[Dict[str, Any]]], session_policy: str) -> list[list[Dict[str, Any]]]:
    if session_policy == "all":
        return sessions
    if session_policy == "latest":
        return sessions[-1:] if sessions else []
    if session_policy == "first":
        return sessions[:1]
    raise ValueError(f"Unsupported session_policy: {session_policy}")


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


def behavioral_realism(
    real_features: list[Dict[str, Any]],
    sim_features: list[Dict[str, Any]],
    opening_alignment: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    real_acts = average_distribution([item["act_distribution"] for item in real_features], all_user_acts())
    sim_acts = average_distribution([item["act_distribution"] for item in sim_features], all_user_acts())
    jsd = jensen_shannon(real_acts, sim_acts, all_user_acts())
    turn_w = wasserstein([item["user_turn_count"] for item in real_features], [item["user_turn_count"] for item in sim_features])
    char_w = wasserstein(flatten([item["user_chars"] for item in real_features]), flatten([item["user_chars"] for item in sim_features]))
    turn_score = distance_score(turn_w, scale=max(1.0, mean([item["user_turn_count"] for item in real_features])))
    char_score = distance_score(char_w, scale=max(1.0, mean(flatten([item["user_chars"] for item in real_features]))))
    act_score = 1.0 - min(1.0, jsd)
    usi = user_sim_index(real_features, sim_features)
    distribution_score = mean([turn_score, char_score, act_score])
    conditional_score = mean(
        [
            usi["information_pattern"],
            usi["clarification_behavior"],
            usi["error_reaction"],
        ]
    )
    opening_score = float((opening_alignment or {}).get("opening_similarity_score", 0.0))
    score = round(
        weighted_average(
            {
                "opening_similarity": opening_score,
                "distribution_realism": distribution_score,
                "conditional_behavior_realism": conditional_score,
                "user_sim_index": usi["score"],
            },
            {
                "opening_similarity": 0.10,
                "distribution_realism": 0.40,
                "conditional_behavior_realism": 0.30,
                "user_sim_index": 0.20,
            },
        ),
        3,
    )
    return {
        "score": score,
        "session_length_wasserstein": round(turn_w, 3),
        "words_per_turn_wasserstein": round(char_w, 3),
        "dialogue_act_jsd": round(jsd, 3),
        "opening_similarity_score": round(opening_score, 3),
        "distribution_alignment_score": round(distribution_score, 3),
        "conditional_behavior_realism_score": round(conditional_score, 3),
        "user_sim_index": usi,
        "opening_similarity_alignment": opening_alignment or empty_opening_similarity_alignment(),
        "score_weights": {
            "opening_similarity": 0.10,
            "distribution_realism": 0.40,
            "conditional_behavior_realism": 0.30,
            "user_sim_index": 0.20,
        },
    }


def opening_similarity_alignment(
    real_transcripts: list[Dict[str, Any]],
    simulated_transcripts: list[Dict[str, Any]],
    artifact: KnowledgeRoadmapArtifact | None,
) -> Dict[str, Any]:
    real_openings = [text for text in (first_user_text(item) for item in real_transcripts) if text]
    simulated_openings = [text for text in (first_user_text(item) for item in simulated_transcripts) if text]
    surface_problem = artifact.roadmap.surface_problem if artifact else ""

    real_sim_scores = [
        calculate_text_similarity(real_opening, sim_opening)
        for real_opening in real_openings
        for sim_opening in simulated_openings
    ]
    real_surface_scores = [
        calculate_text_similarity(real_opening, surface_problem)
        for real_opening in real_openings
    ]
    sim_surface_scores = [
        calculate_text_similarity(sim_opening, surface_problem)
        for sim_opening in simulated_openings
    ]

    real_sim = mean(real_sim_scores)
    real_surface = mean(real_surface_scores)
    sim_surface = mean(sim_surface_scores)
    opening_score = weighted_average(
        {
            "real_sim": real_sim,
            "real_surface": real_surface,
            "sim_surface": sim_surface,
        },
        {
            "real_sim": 0.40,
            "real_surface": 0.30,
            "sim_surface": 0.30,
        },
    )
    return {
        "opening_similarity_score": round(opening_score, 3),
        "real_sim_opening_similarity": round(real_sim, 3),
        "real_surface_similarity": round(real_surface, 3),
        "sim_surface_similarity": round(sim_surface, 3),
        "real_opening_count": len(real_openings),
        "simulated_opening_count": len(simulated_openings),
        "surface_problem": surface_problem[:200],
        "sample_real_opening": real_openings[0][:200] if real_openings else "",
        "sample_simulated_opening": simulated_openings[0][:200] if simulated_openings else "",
        "interpretation": "Low-weight auxiliary metric for surface problem quality and initial intent alignment, not a standalone simulator quality score.",
    }


def empty_opening_similarity_alignment() -> Dict[str, Any]:
    return {
        "opening_similarity_score": 0.0,
        "real_sim_opening_similarity": 0.0,
        "real_surface_similarity": 0.0,
        "sim_surface_similarity": 0.0,
        "real_opening_count": 0,
        "simulated_opening_count": 0,
        "surface_problem": "",
        "sample_real_opening": "",
        "sample_simulated_opening": "",
        "interpretation": "Low-weight auxiliary metric for surface problem quality and initial intent alignment, not a standalone simulator quality score.",
    }


def first_user_text(transcript: Dict[str, Any]) -> str:
    for message in transcript.get("messages") or []:
        if message.get("role") == "user":
            return str(message.get("content") or "").strip()
    return ""


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


def realsim_behavior_distribution(
    real_transcripts: list[Dict[str, Any]],
    simulated_transcripts: list[Dict[str, Any]],
) -> Dict[str, Any]:
    real_profiles = [realsim_profile(transcript) for transcript in real_transcripts]
    sim_profiles = [realsim_profile(transcript) for transcript in simulated_transcripts]
    real_acts = average_distribution([item["intent_distribution"] for item in real_profiles], all_user_acts())
    sim_acts = average_distribution([item["intent_distribution"] for item in sim_profiles], all_user_acts())
    intent_jsd = jensen_shannon(real_acts, sim_acts, all_user_acts())
    intent_score = 1.0 - min(1.0, intent_jsd)

    dimension_scores = {
        "user_intent": intent_score,
        "feedback": profile_pair_score(real_profiles, sim_profiles, "feedback_signal_rate"),
        "emotion": profile_pair_score(real_profiles, sim_profiles, "emotion_signal_rate"),
        "domain_specific_knowledge": profile_pair_score(real_profiles, sim_profiles, "domain_term_rate"),
        "personal_context_identity": profile_pair_score(real_profiles, sim_profiles, "personal_context_rate"),
        "message_length": profile_pair_score(real_profiles, sim_profiles, "avg_user_chars"),
        "linguistic_attributes": profile_pair_score(real_profiles, sim_profiles, "linguistic_signal_rate"),
        "errors": profile_pair_score(real_profiles, sim_profiles, "error_report_rate"),
    }
    return {
        "score": round(mean(dimension_scores.values()), 3),
        "dimension_scores": {key: round(value, 3) for key, value in dimension_scores.items()},
        "intent_jsd": round(intent_jsd, 3),
        "real_profile": summarize_realsim_profiles(real_profiles),
        "simulated_profile": summarize_realsim_profiles(sim_profiles),
    }


def realsim_profile(transcript: Dict[str, Any]) -> Dict[str, Any]:
    user_texts = transcript_user_texts(transcript)
    acts = [classify_user_act(text) for text in user_texts]
    question_rate = marker_turn_rate(user_texts, USER_QUESTION_MARKERS)
    uncertainty_rate = marker_turn_rate(user_texts, UNCERTAINTY_MARKERS)
    first_person_rate = marker_turn_rate(user_texts, ("我", "我的", "这边", "这台"))
    return {
        "intent_distribution": distribution(acts, all_user_acts()),
        "feedback_signal_rate": marker_turn_rate(user_texts, ACCEPT_MARKERS + REJECT_MARKERS + ACTION_MARKERS),
        "emotion_signal_rate": marker_turn_rate(user_texts, CONFUSION_MARKERS + FRUSTRATION_MARKERS),
        "domain_term_rate": marker_turn_rate(user_texts, DOMAIN_MARKERS),
        "personal_context_rate": marker_turn_rate(user_texts, PERSONAL_CONTEXT_MARKERS),
        "avg_user_chars": mean([len(text) for text in user_texts]),
        "linguistic_signal_rate": mean([question_rate, uncertainty_rate, first_person_rate]),
        "error_report_rate": marker_turn_rate(user_texts, ERROR_REPORT_MARKERS),
    }


def profile_pair_score(real_profiles: list[Dict[str, Any]], sim_profiles: list[Dict[str, Any]], key: str) -> float:
    real_value = mean([float(item.get(key) or 0.0) for item in real_profiles])
    sim_value = mean([float(item.get(key) or 0.0) for item in sim_profiles])
    scale = max(0.15, abs(real_value))
    if key == "avg_user_chars":
        scale = max(8.0, abs(real_value))
    return distance_score(abs(real_value - sim_value), scale=scale)


def summarize_realsim_profiles(profiles: list[Dict[str, Any]]) -> Dict[str, float]:
    keys = [
        "feedback_signal_rate",
        "emotion_signal_rate",
        "domain_term_rate",
        "personal_context_rate",
        "avg_user_chars",
        "linguistic_signal_rate",
        "error_report_rate",
    ]
    return {key: round(mean([float(item.get(key) or 0.0) for item in profiles]), 3) for key in keys}


def c2st_distribution_realism(
    real_transcripts: list[Dict[str, Any]],
    simulated_transcripts: list[Dict[str, Any]],
) -> Dict[str, Any]:
    real_vectors = [c2st_feature_vector(transcript) for transcript in real_transcripts]
    sim_vectors = [c2st_feature_vector(transcript) for transcript in simulated_transcripts]
    if not real_vectors or not sim_vectors:
        return {
            "available": False,
            "score": 0.0,
            "classifier_accuracy": 0.0,
            "balanced_accuracy": 0.0,
            "reason": "C2ST requires both real and simulated transcripts.",
        }

    labels = [0] * len(real_vectors) + [1] * len(sim_vectors)
    vectors = standardize_vectors(real_vectors + sim_vectors)
    real_centroid = centroid(vectors[: len(real_vectors)])
    sim_centroid = centroid(vectors[len(real_vectors) :])
    predictions = [predict_by_centroid(vector, real_centroid, sim_centroid) for vector in vectors]
    real_accuracy = safe_rate(sum(1 for pred in predictions[: len(real_vectors)] if pred == 0), len(real_vectors))
    sim_accuracy = safe_rate(sum(1 for pred in predictions[len(real_vectors) :] if pred == 1), len(sim_vectors))
    balanced_accuracy = mean([real_accuracy, sim_accuracy])
    classifier_accuracy = safe_rate(sum(1 for pred, label in zip(predictions, labels) if pred == label), len(labels))
    separability = abs(balanced_accuracy - 0.5) * 2
    return {
        "available": True,
        "score": round(1.0 - min(1.0, separability), 3),
        "classifier_accuracy": round(classifier_accuracy, 3),
        "balanced_accuracy": round(balanced_accuracy, 3),
        "real_sample_count": len(real_vectors),
        "simulated_sample_count": len(sim_vectors),
        "interpretation": "Higher score means a simple classifier has difficulty separating real and simulated dialogues.",
    }


def c2st_feature_vector(transcript: Dict[str, Any]) -> list[float]:
    features = extract_features(transcript)
    user_texts = transcript_user_texts(transcript)
    return [
        float(features["user_turn_count"]),
        float(features["avg_user_chars"]),
        float(features["user_question_rate"]),
        float(features["accept_rate"]),
        float(features["reject_rate"]),
        float(features["clarification_rate"]),
        float(features["confusion_rate"]),
        float(features["frustration_rate"]),
        float(features["action_feedback_rate"]),
        float(features["provide_info_rate"]),
        marker_turn_rate(user_texts, DOMAIN_MARKERS),
        marker_turn_rate(user_texts, PERSONAL_CONTEXT_MARKERS),
        marker_turn_rate(user_texts, UNCERTAINTY_MARKERS),
        marker_turn_rate(user_texts, ERROR_REPORT_MARKERS),
    ]


def standardize_vectors(vectors: list[list[float]]) -> list[list[float]]:
    if not vectors:
        return []
    columns = list(zip(*vectors))
    means = [mean(column) for column in columns]
    stds = [
        math.sqrt(mean([(value - column_mean) ** 2 for value in column])) or 1.0
        for column, column_mean in zip(columns, means)
    ]
    return [[(value - means[index]) / stds[index] for index, value in enumerate(vector)] for vector in vectors]


def centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    return [mean(column) for column in zip(*vectors)]


def predict_by_centroid(vector: list[float], real_centroid: list[float], sim_centroid: list[float]) -> int:
    real_distance = euclidean_distance(vector, real_centroid)
    sim_distance = euclidean_distance(vector, sim_centroid)
    return 1 if sim_distance < real_distance else 0


def euclidean_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((left_value - right_value) ** 2 for left_value, right_value in zip(left, right)))


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


def leakage_aware_success_metrics(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    rows = trajectory.get("session_details") or []
    if not rows:
        return {
            "raw_success_rate": 0.0,
            "leakage_adjusted_success_rate": 0.0,
            "false_success_rate": 0.0,
            "solution_leakage_rate": 0.0,
        }
    raw_success = [1.0 if row.get("target_solution_hit") and row.get("accepted_target") else 0.0 for row in rows]
    leakage = [1.0 if row.get("knowledge_leakage") else 0.0 for row in rows]
    adjusted_success = [
        1.0 if success and not row.get("knowledge_leakage") else 0.0 for success, row in zip(raw_success, rows)
    ]
    false_success = [
        1.0 if row.get("wrong_acceptance") or (success and row.get("knowledge_leakage")) else 0.0
        for success, row in zip(raw_success, rows)
    ]
    return {
        "raw_success_rate": round(mean(raw_success), 3),
        "leakage_adjusted_success_rate": round(mean(adjusted_success), 3),
        "false_success_rate": round(mean(false_success), 3),
        "solution_leakage_rate": round(mean(leakage), 3),
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
    behavior["diagnostic_rule_score"] = rule_behavior.get("score", 0.0)
    behavior["llm_judge_score"] = judge_score
    behavior["score"] = score_value(judge_score, rule_behavior.get("score", 0.0))
    behavior["scoring_mode"] = "llm_judge_primary"
    return behavior


def apply_goal_judge(rule_goal: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    goal = dict(rule_goal)
    judge_score = judge.get("goal_alignment_score", 0.0)
    goal["diagnostic_rule_score"] = rule_goal.get("score", 0.0)
    goal["llm_judge_score"] = judge_score
    goal["score"] = score_value(judge_score, rule_goal.get("score", 0.0))
    goal["scoring_mode"] = "llm_judge_primary"
    return goal


def apply_cooperation_judge(rule_cooperation: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    cooperation = dict(rule_cooperation)
    judge_score = judge.get("anti_overcooperation_score", 0.0)
    cooperation["diagnostic_rule_score"] = rule_cooperation.get("score", 0.0)
    cooperation["llm_judge_score"] = judge_score
    cooperation["score"] = score_value(judge_score, rule_cooperation.get("score", 0.0))
    cooperation["scoring_mode"] = "llm_judge_primary"
    return cooperation


def apply_realsim_judge(realsim: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(realsim)
    judge_score = judge.get("realsim_behavior_score", realsim.get("score", 0.0))
    updated["diagnostic_rule_score"] = realsim.get("score", 0.0)
    updated["llm_judge_score"] = score_value(judge_score, realsim.get("score", 0.0))
    updated["score"] = updated["llm_judge_score"]
    updated["scoring_mode"] = "llm_judge_primary"
    return updated


def apply_c2st_judge(c2st: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(c2st)
    judge_score = judge.get("c2st_realism_score", c2st.get("score", 0.0))
    updated["diagnostic_rule_score"] = c2st.get("score", 0.0)
    updated["llm_judge_score"] = score_value(judge_score, c2st.get("score", 0.0))
    updated["score"] = updated["llm_judge_score"]
    updated["scoring_mode"] = "llm_judge_primary"
    return updated


def apply_leakage_success_judge(leakage_success: Dict[str, Any], judge: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(leakage_success)
    rule_score = leakage_success.get("leakage_adjusted_success_rate", 0.0)
    judge_score = judge.get("leakage_aware_success_score", rule_score)
    updated["diagnostic_rule_score"] = rule_score
    updated["llm_judge_score"] = score_value(judge_score, rule_score)
    updated["score"] = updated["llm_judge_score"]
    updated["scoring_mode"] = "llm_judge_primary"
    return updated


def final_overall_score(
    behavior: Dict[str, Any],
    goal: Dict[str, Any],
    cooperation: Dict[str, Any],
    judge: Dict[str, Any] | None,
) -> float:
    if judge and "overall_score" in judge:
        return score_value(judge.get("overall_score"), 0.0)
    return round(
        weighted_average(
            {
                "behavioral_realism": score_value(behavior.get("score"), 0.0),
                "goal_alignment": score_value(goal.get("score"), 0.0),
                "anti_overcooperation": score_value(cooperation.get("score"), 0.0),
            },
            {"behavioral_realism": 0.45, "goal_alignment": 0.35, "anti_overcooperation": 0.20},
        ),
        3,
    )


def normalize_eval_judge_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    analysis = payload.get("analysis") or {}
    behavioral = score_value(payload.get("behavioral_realism_score"), 0.0)
    goal = score_value(payload.get("goal_alignment_score"), 0.0)
    anti_overcoop = score_value(payload.get("anti_overcooperation_score"), 0.0)
    overall_default = weighted_average(
        {
            "behavioral_realism": behavioral,
            "goal_alignment": goal,
            "anti_overcooperation": anti_overcoop,
        },
        {"behavioral_realism": 0.40, "goal_alignment": 0.35, "anti_overcooperation": 0.25},
    )
    result = {
        "behavioral_realism_score": behavioral,
        "goal_alignment_score": goal,
        "anti_overcooperation_score": anti_overcoop,
        "overall_score": score_value(payload.get("overall_score"), overall_default),
        "behavioral_realism_analysis": str(analysis.get("behavioral_realism_analysis", "")),
        "goal_alignment_analysis": str(analysis.get("goal_alignment_analysis", "")),
        "overcooperation_analysis": str(analysis.get("overcooperation_analysis", "")),
        "realsim_behavior_analysis": str(analysis.get("realsim_behavior_analysis", "")),
        "c2st_realism_analysis": str(analysis.get("c2st_realism_analysis", "")),
        "leakage_aware_success_analysis": str(analysis.get("leakage_aware_success_analysis", "")),
        "failure_modes": normalize_string_list(payload.get("failure_modes")),
        "reasons": normalize_string_list(payload.get("reasons")),
    }
    if "realsim_behavior_score" in payload:
        result["realsim_behavior_score"] = score_value(payload.get("realsim_behavior_score"), 0.0)
    if "c2st_realism_score" in payload:
        result["c2st_realism_score"] = score_value(payload.get("c2st_realism_score"), 0.0)
    if "leakage_aware_success_score" in payload:
        result["leakage_aware_success_score"] = score_value(payload.get("leakage_aware_success_score"), 0.0)
    return result


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
        "| case_id | real | simulated | overall | behavioral | opening_aux | realsim | c2st | leak_adj_success | goal | anti-overcoop |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for report in reports:
        lines.append(
            "| {case_id} | {real} | {sim} | {overall:.3f} | {behavior:.3f} | {opening:.3f} | {realsim:.3f} | {c2st:.3f} | {leak_adj:.3f} | {goal:.3f} | {coop:.3f} |".format(
                case_id=report["case_id"],
                real=report["real_session_count"],
                sim=report["simulated_session_count"],
                overall=report["overall_score"],
                behavior=report["behavioral_realism"]["score"],
                opening=report["behavioral_realism"].get("opening_similarity_score", 0.0),
                realsim=report.get("realsim_behavior_distribution", {}).get("score", 0.0),
                c2st=report.get("c2st_distribution_realism", {}).get("score", 0.0),
                leak_adj=report.get("leakage_aware_success", {}).get(
                    "score",
                    report.get("leakage_aware_success", {}).get("leakage_adjusted_success_rate", 0.0),
                ),
                goal=report["goal_alignment"]["score"],
                coop=report["overly_cooperative"]["score"],
            )
        )
    lines.append("")
    if any(report.get("llm_judge") for report in reports):
        lines.append("Final scores are LLM-judge primary. Rule-based metrics, distribution checks, and trajectory/state checks are supporting diagnostics/evidence.")
    else:
        lines.append("Diagnostic-only mode: scores are rule-based offline estimates. Use --judge for formal LLM-judge primary evaluation.")
    lines.append("")
    lines.append("`opening_aux` is a low-weight auxiliary signal for surface-problem quality and initial-intent alignment; it is not a standalone simulator-quality score.")
    lines.append("`realsim` is an eight-dimension behavior-distribution diagnostic. `c2st` is a classifier two-sample test proxy: higher means real and simulated sessions are harder to separate. `leak_adj_success` counts accepted target solutions only when no user-side knowledge leakage is detected.")
    return "\n".join(lines) + "\n"


def render_case_report(report: Dict[str, Any]) -> str:
    behavior = report["behavioral_realism"]
    opening = behavior.get("opening_similarity_alignment", empty_opening_similarity_alignment())
    goal = report["goal_alignment"]
    coop = report["overly_cooperative"]
    trajectory = report.get("trajectory_state", {})
    leakage_success = report.get("leakage_aware_success", {})
    realsim = report.get("realsim_behavior_distribution", {})
    c2st = report.get("c2st_distribution_realism", {})
    enhanced = report.get("enhanced_evaluation", {})
    lines = [
        f"# Simulator Evaluation {report['case_id']}",
        "",
        f"- real_session_count: {report['real_session_count']}",
        f"- simulated_session_count: {report['simulated_session_count']}",
        f"- evaluation_mode: {report.get('evaluation_mode', 'diagnostic_only_rule_based')}",
        f"- overall_score: {report['overall_score']:.3f}",
        "",
        "## Behavioral Realism",
        "",
        f"- score: {behavior['score']:.3f}",
        f"- diagnostic_rule_score: {behavior.get('diagnostic_rule_score', behavior.get('rule_score', behavior['score']))}",
        f"- llm_judge_score: {behavior.get('llm_judge_score', '')}",
        f"- scoring_mode: {behavior.get('scoring_mode', 'diagnostic_only_rule_based')}",
        f"- dialogue_act_jsd: {behavior['dialogue_act_jsd']:.3f}",
        f"- session_length_wasserstein: {behavior['session_length_wasserstein']:.3f}",
        f"- words_per_turn_wasserstein: {behavior['words_per_turn_wasserstein']:.3f}",
        f"- opening_similarity_score: {behavior.get('opening_similarity_score', 0.0):.3f}",
        f"- distribution_alignment_score: {behavior.get('distribution_alignment_score', 0.0):.3f}",
        f"- conditional_behavior_realism_score: {behavior.get('conditional_behavior_realism_score', 0.0):.3f}",
        f"- user_sim_index: {behavior['user_sim_index']['score']:.3f}",
        f"- score_weights: opening=0.10, distribution=0.40, conditional=0.30, user_sim_index=0.20",
        "",
        "### Opening Similarity Auxiliary",
        "",
        f"- opening_similarity_score: {opening.get('opening_similarity_score', 0.0):.3f}",
        f"- real_sim_opening_similarity: {opening.get('real_sim_opening_similarity', 0.0):.3f}",
        f"- real_surface_similarity: {opening.get('real_surface_similarity', 0.0):.3f}",
        f"- sim_surface_similarity: {opening.get('sim_surface_similarity', 0.0):.3f}",
        f"- sample_real_opening: {opening.get('sample_real_opening', '')}",
        f"- sample_simulated_opening: {opening.get('sample_simulated_opening', '')}",
        f"- surface_problem: {opening.get('surface_problem', '')}",
        "",
        "Opening similarity is a low-weight auxiliary metric for user-facing problem quality and initial intent alignment. A low score may reflect standardized roadmap wording or noisy real openings, not necessarily poor simulator behavior.",
        "",
        "## RealSim-Style Distribution",
        "",
        f"- score: {realsim.get('score', 0.0):.3f}",
        f"- diagnostic_rule_score: {realsim.get('diagnostic_rule_score', realsim.get('score', 0.0))}",
        f"- llm_judge_score: {realsim.get('llm_judge_score', '')}",
        f"- intent_jsd: {realsim.get('intent_jsd', 0.0):.3f}",
        "",
        "```json",
        json.dumps(realsim.get("dimension_scores", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## C2ST Distribution Check",
        "",
        f"- score: {c2st.get('score', 0.0):.3f}",
        f"- diagnostic_rule_score: {c2st.get('diagnostic_rule_score', c2st.get('score', 0.0))}",
        f"- llm_judge_score: {c2st.get('llm_judge_score', '')}",
        f"- classifier_accuracy: {c2st.get('classifier_accuracy', 0.0):.3f}",
        f"- balanced_accuracy: {c2st.get('balanced_accuracy', 0.0):.3f}",
        f"- available: {c2st.get('available', False)}",
        "",
        "## Goal Alignment",
        "",
        f"- score: {goal['score']:.3f}",
        f"- diagnostic_rule_score: {goal.get('diagnostic_rule_score', goal.get('rule_score', goal['score']))}",
        f"- llm_judge_score: {goal.get('llm_judge_score', '')}",
        f"- scoring_mode: {goal.get('scoring_mode', 'diagnostic_only_rule_based')}",
        f"- pre_trajectory_score: {goal.get('pre_trajectory_score', '')}",
        f"- trajectory_state_score: {goal.get('trajectory_state_score', '')}",
        f"- goal_persistence_score: {goal['goal_persistence_score']:.3f}",
        f"- knowledge_boundary_score: {goal['knowledge_boundary_score']:.3f}",
        f"- simulated_solved_rate: {goal['simulated_solved_rate']:.3f}",
        "",
        "## Overly Cooperative",
        "",
        f"- anti_overcooperation_score: {coop['score']:.3f}",
        f"- diagnostic_rule_score: {coop.get('diagnostic_rule_score', coop.get('rule_score', coop['score']))}",
        f"- llm_judge_score: {coop.get('llm_judge_score', '')}",
        f"- scoring_mode: {coop.get('scoring_mode', 'diagnostic_only_rule_based')}",
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
        "## Leakage-Aware Success",
        "",
        f"- score: {leakage_success.get('score', leakage_success.get('leakage_adjusted_success_rate', 0.0)):.3f}",
        f"- diagnostic_rule_score: {leakage_success.get('diagnostic_rule_score', leakage_success.get('leakage_adjusted_success_rate', 0.0))}",
        f"- llm_judge_score: {leakage_success.get('llm_judge_score', '')}",
        f"- raw_success_rate: {leakage_success.get('raw_success_rate', 0.0):.3f}",
        f"- leakage_adjusted_success_rate: {leakage_success.get('leakage_adjusted_success_rate', 0.0):.3f}",
        f"- false_success_rate: {leakage_success.get('false_success_rate', 0.0):.3f}",
        f"- solution_leakage_rate: {leakage_success.get('solution_leakage_rate', 0.0):.3f}",
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
        analysis_fields = [
            ("behavioral_realism", "behavioral_realism_analysis"),
            ("goal_alignment", "goal_alignment_analysis"),
            ("overcooperation", "overcooperation_analysis"),
            ("realsim_behavior", "realsim_behavior_analysis"),
            ("c2st_realism", "c2st_realism_analysis"),
            ("leakage_aware_success", "leakage_aware_success_analysis"),
        ]
        for label, key in analysis_fields:
            value = report["llm_judge"].get(key, "")
            if value:
                lines.append(f"- {label}: {value}")
        lines.extend(f"- {reason}" for reason in report["llm_judge"].get("reasons", []))
        if report["llm_judge"].get("failure_modes"):
            lines.append("")
            lines.append("Failure modes:")
            lines.extend(f"- {item}" for item in report["llm_judge"].get("failure_modes", []))
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


def transcript_user_texts(transcript: Dict[str, Any]) -> list[str]:
    return [str(item.get("content") or "") for item in transcript.get("messages") or [] if item.get("role") == "user"]


def marker_turn_rate(texts: list[str], markers: Iterable[str]) -> float:
    return safe_rate(sum(1 for text in texts if contains_any(text, markers)), len(texts))


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
