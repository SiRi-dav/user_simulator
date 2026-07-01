from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_loader import load_dialogues
from local_ai_client import LocalAIClient, MockLocalAIClient, build_local_ai_client
from persona_bank import choose_persona, load_personas, persona_summary
from utils import parse_simple_yaml, read_jsonl, write_jsonl


CLARIFICATION_HINTS = ("请问", "是否", "能否", "提供", "补充", "具体", "哪个", "什么")
SOLUTION_HINTS = ("可以", "建议", "请按", "参考", "解决", "处理", "步骤", "路径")
SCENARIOS = ("replay_like", "vague_user", "difficult_user")
PHONE_RE = re.compile(r"(?<![A-Za-z0-9])(?:\+?\d[\d\- ]{6,}\d)(?![A-Za-z0-9])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://\S+")
LONG_ID_RE = re.compile(r"(?<![A-Za-z0-9])\d{8,}(?![A-Za-z0-9])")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a lightweight user simulator from case-only question patterns.")
    parser.add_argument(
        "--patterns",
        default="outputs_case_only/question_patterns.case_only.jsonl",
        help="Pattern JSONL path. Defaults to case-only analysis output.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output JSONL path. Defaults to outputs/simulated_dialogues.<scenario>[.policy][.llm].jsonl",
    )
    parser.add_argument("--config", default="config.yaml", help="Config file used to load historical dialogues for --agent replay")
    parser.add_argument("--case-id", default="", help="Optional target case_id")
    parser.add_argument("--limit", type=int, default=10, help="Maximum cases to simulate. Use 0 for all.")
    parser.add_argument("--scenario", default="", choices=SCENARIOS, help="Evaluation scenario")
    parser.add_argument("--mode", default="", choices=SCENARIOS, help="Deprecated alias for --scenario")
    parser.add_argument("--persona", default="auto", help="Persona id from the persona bank, or auto")
    parser.add_argument("--persona-bank", default="", help="Optional JSON persona bank path. Defaults to built-in personas.")
    parser.add_argument("--list-personas", action="store_true", help="List available personas and exit")
    parser.add_argument("--max-turns", type=int, default=6, help="Maximum user turns")
    parser.add_argument(
        "--agent",
        default="mock",
        choices=["mock", "replay", "none"],
        help="Use rule mock, replay historical agent turns, or only emit user plan",
    )
    parser.add_argument("--no-mask", action="store_true", help="Do not mask URLs, emails, phones, or long numeric IDs")
    parser.add_argument("--readable-output", default="", help="Optional readable Markdown output path")
    parser.add_argument("--llm-rewrite", action="store_true", help="Shortcut for --rewrite-provider openai-compatible")
    parser.add_argument("--llm-policy", action="store_true", help="Let the local LLM choose user actions and slot reveal timing")
    parser.add_argument("--policy-provider", default="mock", choices=["mock", "openai-compatible"], help="LLM provider for user dialogue policy")
    parser.add_argument("--policy-endpoint", default="http://localhost:8850/v1/chat/completions")
    parser.add_argument("--policy-model", default="qwen3-32b")
    parser.add_argument("--policy-api-key", default="EMPTY")
    parser.add_argument("--policy-api-key-env", default="LOCAL_AI_API_KEY")
    parser.add_argument("--policy-temperature", type=float, default=0.4)
    parser.add_argument("--policy-max-tokens", type=int, default=512)
    parser.add_argument("--policy-timeout", type=int, default=90)
    parser.add_argument("--rewrite-provider", default="mock", choices=["mock", "openai-compatible"], help="LLM provider for user utterance rewriting")
    parser.add_argument("--rewrite-endpoint", default="http://localhost:8850/v1/chat/completions")
    parser.add_argument("--rewrite-model", default="qwen3-32b")
    parser.add_argument("--rewrite-api-key", default="EMPTY")
    parser.add_argument("--rewrite-api-key-env", default="LOCAL_AI_API_KEY")
    parser.add_argument("--rewrite-temperature", type=float, default=0.7)
    parser.add_argument("--rewrite-max-tokens", type=int, default=256)
    parser.add_argument("--rewrite-timeout", type=int, default=60)
    args = parser.parse_args()
    if args.llm_rewrite:
        args.rewrite_provider = "openai-compatible"
    if args.llm_policy:
        args.policy_provider = "openai-compatible"
    scenario = args.scenario or args.mode or "replay_like"
    if args.mode and not args.scenario:
        print("Warning: --mode is deprecated; use --scenario instead.", flush=True)
    personas = load_personas(args.persona_bank)
    if args.list_personas:
        for persona in personas:
            print(f"{persona.get('persona_id')}: {persona.get('name')} - {persona_summary(persona)}")
        return

    patterns = [record for record in read_jsonl(Path(args.patterns)) if not record.get("parse_error")]
    if args.case_id:
        patterns = [record for record in patterns if record.get("case_id") == args.case_id]
    if args.limit > 0:
        patterns = patterns[: args.limit]

    rewrite_client = build_rewrite_client(args)
    policy_client = build_policy_client(args)
    replay_dialogues = load_replay_dialogues(args)
    results = [
        simulate_case(
            pattern,
            scenario=scenario,
            max_turns=args.max_turns,
            agent=args.agent,
            replay_dialogues=replay_dialogues,
            rewrite_client=rewrite_client,
            policy_client=policy_client,
            personas=personas,
            persona_id=args.persona,
        )
        for pattern in patterns
    ]
    if not args.no_mask:
        results = [mask_value(result) for result in results]
    output_path = (
        Path(args.output)
        if args.output
        else default_output_path(scenario, args.rewrite_provider, args.persona, args.policy_provider, args.agent)
    )
    readable_path = Path(args.readable_output) if args.readable_output else default_readable_path(output_path)
    write_jsonl(results, output_path)
    readable_path.parent.mkdir(parents=True, exist_ok=True)
    readable_path.write_text(build_readable_report(results), encoding="utf-8")
    print(f"Simulated cases: {len(results)}")
    print(f"Output written to: {output_path}")
    print(f"Readable output written to: {readable_path}")


def build_rewrite_client(args: argparse.Namespace) -> LocalAIClient:
    if args.rewrite_provider == "mock":
        return MockLocalAIClient()
    return build_local_ai_client(
        {
            "provider": args.rewrite_provider,
            "endpoint": args.rewrite_endpoint,
            "model": args.rewrite_model,
            "api_key": args.rewrite_api_key,
            "api_key_env": args.rewrite_api_key_env,
            "temperature": args.rewrite_temperature,
            "max_tokens": args.rewrite_max_tokens,
            "timeout": args.rewrite_timeout,
            "enable_thinking": False,
            "system_prompt": "你是企业客服场景中的用户话语改写器，只输出用户话语。",
        }
    )


def build_policy_client(args: argparse.Namespace) -> LocalAIClient:
    if args.policy_provider == "mock":
        return MockLocalAIClient()
    return build_local_ai_client(
        {
            "provider": args.policy_provider,
            "endpoint": args.policy_endpoint,
            "model": args.policy_model,
            "api_key": args.policy_api_key,
            "api_key_env": args.policy_api_key_env,
            "temperature": args.policy_temperature,
            "max_tokens": args.policy_max_tokens,
            "timeout": args.policy_timeout,
            "enable_thinking": False,
            "system_prompt": "你是企业客服场景中的用户模拟策略器，只输出 JSON。",
        }
    )


def default_output_path(
    scenario: str,
    rewrite_provider: str,
    persona_id: str = "auto",
    policy_provider: str = "mock",
    agent: str = "mock",
) -> Path:
    suffix = ".policy" if policy_provider != "mock" else ""
    suffix += ".llm" if rewrite_provider != "mock" else ""
    suffix += ".replay" if agent == "replay" else ""
    persona_suffix = "" if not persona_id or persona_id == "auto" else f".{persona_id}"
    return Path("outputs") / f"simulated_dialogues.{scenario}{persona_suffix}{suffix}.jsonl"


def simulate_case(
    pattern: Dict[str, Any],
    scenario: str,
    max_turns: int,
    agent: str,
    replay_dialogues: Dict[str, List[Dict[str, Any]]],
    rewrite_client: LocalAIClient,
    policy_client: LocalAIClient,
    personas: List[Dict[str, Any]],
    persona_id: str,
) -> Dict[str, Any]:
    persona = choose_persona(personas, persona_id, str(pattern.get("case_id") or ""), scenario)
    state = build_initial_state(pattern, scenario, persona)
    turns: List[Dict[str, Any]] = []
    agent_response: Optional[str] = None
    replay_context = choose_replay_context(replay_dialogues, str(pattern.get("case_id") or ""))
    replay_turn_index = 0

    for user_turn_id in range(1, max_turns + 1):
        user_text, user_action = choose_user_turn(
            pattern=pattern,
            state=state,
            agent_response=agent_response,
            scenario=scenario,
            user_turn_id=user_turn_id,
            persona=persona,
            turns=turns,
            policy_client=policy_client,
        )
        user_text = rewrite_user_utterance(
            text=user_text,
            action=user_action,
            pattern=pattern,
            scenario=scenario,
            persona=persona,
            agent_response=agent_response,
            rewrite_client=rewrite_client,
        )
        turns.append(
            {
                "role": "user",
                "turn_id": user_turn_id,
                "text": user_text,
                "action": user_action,
                "revealed_slots": list(state["revealed_slots"]),
            }
        )
        if user_action in {"accept_solution", "give_up"} or agent == "none":
            break

        agent_step, replay_turn_index = agent_step_for_mode(
            pattern=pattern,
            user_turn_id=user_turn_id,
            user_text=user_text,
            state=state,
            agent=agent,
            replay_context=replay_context,
            replay_turn_index=replay_turn_index,
        )
        if agent_step["action"] == "end_replay":
            break
        turns.append(
            {
                "role": "agent",
                "turn_id": user_turn_id,
                "text": agent_step["text"],
                "action": agent_step["action"],
                "recommended_case_id": agent_step.get("recommended_case_id"),
                "replay_dialogue_id": agent_step.get("replay_dialogue_id"),
                "replay_turn_index": agent_step.get("replay_turn_index"),
            }
        )
        agent_response = agent_step["text"]
        if agent != "replay" and agent_step["action"] == "answer" and scenario != "difficult_user":
            final_text, final_action = choose_user_turn(
                pattern=pattern,
                state=state,
                agent_response=agent_response,
                scenario=scenario,
                user_turn_id=user_turn_id + 1,
                persona=persona,
                turns=turns,
                policy_client=policy_client,
            )
            final_text = rewrite_user_utterance(
                text=final_text,
                action=final_action,
                pattern=pattern,
                scenario=scenario,
                persona=persona,
                agent_response=agent_response,
                rewrite_client=rewrite_client,
            )
            turns.append(
                {
                    "role": "user",
                    "turn_id": user_turn_id + 1,
                    "text": final_text,
                    "action": final_action,
                    "revealed_slots": list(state["revealed_slots"]),
                }
            )
            break

    return {
        "case_id": pattern.get("case_id"),
        "scenario": scenario,
        "persona": {
            "persona_id": persona.get("persona_id"),
            "name": persona.get("name"),
            "summary": persona_summary(persona),
            "behavior_rules": persona.get("behavior_rules", []),
        },
        "case_understanding": pattern.get("case_understanding", {}),
        "behavior_model_summary": compact_behavior_model(pattern),
        "simulation_plan_summary": compact_simulation_plan(pattern),
        "turns": turns,
        "final_state": {
            "revealed_slots": state["revealed_slots"],
            "remaining_slots": [slot["slot"] for slot in state["slots"]],
            "used_opening": state["used_opening"],
        },
        "agent_source": {
            "mode": agent,
            "replay_dialogue_id": replay_context.get("dialogue_id") if replay_context else "",
        },
    }


def load_replay_dialogues(args: argparse.Namespace) -> Dict[str, List[Dict[str, Any]]]:
    if args.agent != "replay":
        return {}
    config_path = Path(args.config)
    config = parse_simple_yaml(config_path)
    paths = config.get("paths", {})
    if not paths.get("dialogues"):
        raise ValueError("--agent replay requires paths.dialogues in config")
    dialogues_path = resolve_path(config_path.parent, paths["dialogues"])
    dialogues = load_dialogues(dialogues_path, config.get("dialogue_fields", {}))
    by_case: Dict[str, List[Dict[str, Any]]] = {}
    for dialogue in dialogues:
        if not dialogue.case_id:
            continue
        agent_turns = [turn.text for turn in dialogue.turns if turn.role == "agent" and turn.text.strip()]
        if not agent_turns:
            continue
        by_case.setdefault(dialogue.case_id, []).append(
            {
                "dialogue_id": dialogue.dialogue_id,
                "agent_turns": agent_turns,
            }
        )
    return by_case


def choose_replay_context(
    replay_dialogues: Dict[str, List[Dict[str, Any]]],
    case_id: str,
) -> Dict[str, Any]:
    candidates = replay_dialogues.get(case_id) or []
    if not candidates:
        return {}
    return candidates[0]


def agent_step_for_mode(
    pattern: Dict[str, Any],
    user_turn_id: int,
    user_text: str,
    state: Dict[str, Any],
    agent: str,
    replay_context: Dict[str, Any],
    replay_turn_index: int,
) -> tuple[Dict[str, Any], int]:
    if agent == "replay" and replay_context:
        agent_turns = replay_context.get("agent_turns") or []
        if replay_turn_index < len(agent_turns):
            return (
                {
                    "action": classify_agent_action(str(agent_turns[replay_turn_index])),
                    "text": str(agent_turns[replay_turn_index]),
                    "replay_dialogue_id": replay_context.get("dialogue_id"),
                    "replay_turn_index": replay_turn_index,
                },
                replay_turn_index + 1,
            )
        return {"action": "end_replay", "text": ""}, replay_turn_index
    return mock_agent_step(pattern, user_turn_id, user_text, state), replay_turn_index


def classify_agent_action(text: str) -> str:
    if looks_like_solution(text):
        return "answer"
    if looks_like_clarification(text):
        return "ask_clarification"
    return "historical_agent_reply"


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def choose_user_turn(
    pattern: Dict[str, Any],
    state: Dict[str, Any],
    agent_response: Optional[str],
    scenario: str,
    user_turn_id: int,
    persona: Dict[str, Any],
    turns: List[Dict[str, Any]],
    policy_client: LocalAIClient,
) -> tuple[str, str]:
    state_snapshot = clone_sim_state(state)
    fallback_text, fallback_action = next_user_utterance(
        pattern,
        state,
        agent_response,
        scenario,
        user_turn_id,
        persona,
    )
    fallback_state = clone_sim_state(state)
    if isinstance(policy_client, MockLocalAIClient):
        return fallback_text, fallback_action
    restore_sim_state(state, state_snapshot)

    policy_state = {
        "slots": [dict(slot) for slot in state["slots"]],
        "revealed_slots": list(state["revealed_slots"]),
        "used_opening": state["used_opening"],
        "solution_seen": state["solution_seen"],
        "clarification_count": state["clarification_count"],
        "persona_id": state["persona_id"],
    }
    prompt = build_policy_prompt(
        pattern=pattern,
        state=policy_state,
        agent_response=agent_response,
        scenario=scenario,
        user_turn_id=user_turn_id,
        persona=persona,
        turns=turns,
    )
    try:
        decision = parse_policy_decision(policy_client.generate(prompt))
    except Exception as exc:
        print(f"policy failed for {pattern.get('case_id')}: {exc}", flush=True)
        restore_sim_state(state, fallback_state)
        return fallback_text, fallback_action

    action = str(decision.get("action") or fallback_action).strip() or fallback_action
    text = str(decision.get("text") or "").strip()
    reveal_indices = normalize_reveal_indices(decision.get("reveal_slot_indices"), len(state["slots"]))
    if not text:
        text = fallback_text
    if len(text) > 220:
        restore_sim_state(state, fallback_state)
        return fallback_text, fallback_action

    revealed = pop_revealed_slots(state, reveal_indices)
    if user_turn_id == 1 and not state["used_opening"]:
        state["used_opening"] = text
    if looks_like_solution(agent_response or ""):
        state["solution_seen"] = True
    if looks_like_clarification(agent_response or ""):
        state["clarification_count"] += 1

    if revealed and action in {"opening", "ask_more_detail", "no_more_info"}:
        action = "reveal_slot"
    return text, action


def build_policy_prompt(
    pattern: Dict[str, Any],
    state: Dict[str, Any],
    agent_response: Optional[str],
    scenario: str,
    user_turn_id: int,
    persona: Dict[str, Any],
    turns: List[Dict[str, Any]],
) -> str:
    slots = []
    for index, slot in enumerate(state["slots"]):
        slots.append(
            {
                "index": index,
                "slot": slot.get("slot", ""),
                "ask_label": slot.get("ask_label", ""),
                "example_user_phrase": slot.get("example_user_phrase", ""),
            }
        )
    payload = {
        "case_grounding": {
            "case_id": pattern.get("case_id"),
            "case_to_question_summary": case_understanding(pattern).get("case_to_question_summary", ""),
            "user_visible_problem": case_understanding(pattern).get("user_visible_problem", ""),
            "surface_problem_patterns": str_list(behavior_model(pattern), "surface_problem_patterns")[:5],
            "opening_question_templates": str_list(simulation_plan(pattern), "opening_question_templates")[:5],
        },
        "persona": {
            "persona_id": persona.get("persona_id"),
            "name": persona.get("name"),
            "technical_level": persona.get("technical_level"),
            "clarity": persona.get("clarity"),
            "cooperation": persona.get("cooperation"),
            "patience": persona.get("patience"),
            "disclosure_style": persona.get("disclosure_style"),
            "language_style": persona.get("language_style"),
            "behavior_rules": persona.get("behavior_rules", []),
        },
        "dialogue_context": {
            "scenario": scenario,
            "user_turn_id": user_turn_id,
            "last_agent_response": agent_response or "",
            "recent_turns": compact_turn_history(turns[-6:]),
            "revealed_slots": state["revealed_slots"],
            "available_hidden_slots": slots,
            "solution_seen": state["solution_seen"],
            "clarification_count": state["clarification_count"],
        },
        "strategy_guidance": [
            "高技术、表达清楚、主动配合的用户可以在开场或早期主动透露多个关键槽位。",
            "普通合作用户通常先说主要现象，被追问后透露1个或少量槽位。",
            "模糊、低技术、依赖截图或困难用户应少量透露信息，可能需要多次追问才补充关键事实。",
            "急躁用户会催促，但仍可能提供对定位有帮助的信息。",
            "如果客服反问的内容能对应 available_hidden_slots 中的某些项，用户应根据 persona 透露这些 slot。",
            "如果客服反问的内容不在 available_hidden_slots 中，或该 persona 按设定并不知道，用户应明确说不知道/不清楚，不要编造。",
            "如果客服一次问多个问题，清楚且高技术用户可以回答多个可用 slot；模糊或低技术用户通常只回答一部分。",
            "如果客服已经给出明确方案，用户可根据 persona 接受、追问细节或说明试过无效。",
        ],
        "output_schema": {
            "action": "opening | reveal_slot | proactive_followup | unknown_info | ask_more_detail | accept_solution | solution_failed | no_more_info | give_up",
            "text": "用户本轮自然话语",
            "reveal_slot_indices": "本轮要透露的 available_hidden_slots index 列表；不透露则为空列表",
        },
    }
    return f"""
你是企业客服场景中的用户模拟策略器，需要同时决定“用户本轮说什么”和“本轮透露哪些隐藏信息”。

你有策略自主权，但必须受以下硬约束：
- 只能围绕 case_grounding 中的目标问题，不要换 case。
- 只能从 available_hidden_slots 选择要透露的隐藏信息，不要编造新的具体事实。
- reveal_slot_indices 必须是 available_hidden_slots 中存在的 index。
- 客服问到 available_hidden_slots 中已有的信息时，可以选择对应 index 并在 text 中回答。
- 客服问到用户不知道、看不到、没有被提供的信息时，reveal_slot_indices 为空，action 用 unknown_info，并在 text 中自然表达不知道/不清楚。
- text 必须体现 persona 的技术水平、清晰度、配合程度、耐心和语言风格。
- 不要替客服回答，不要输出电话、邮箱、URL、账号、人员姓名等敏感细节。
- 只输出 JSON，不要代码块，不要解释。

输入：
{json.dumps(payload, ensure_ascii=False, indent=2)}

请输出：
{{"action": "...", "text": "...", "reveal_slot_indices": [0]}}
""".strip()


def parse_policy_decision(raw_response: str) -> Dict[str, Any]:
    text = raw_response.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    left = text.find("{")
    right = text.rfind("}")
    if left < 0 or right < left:
        raise ValueError("policy response is not JSON")
    data = json.loads(text[left : right + 1])
    if not isinstance(data, dict):
        raise ValueError("policy response must be a JSON object")
    return data


def normalize_reveal_indices(value: Any, slot_count: int) -> List[int]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= index < slot_count and index not in result:
            result.append(index)
    return result


def pop_revealed_slots(state: Dict[str, Any], reveal_indices: List[int]) -> List[str]:
    revealed = []
    for index in sorted(reveal_indices, reverse=True):
        slot = state["slots"].pop(index)
        slot_name = str(slot.get("slot") or slot.get("example_user_phrase") or "unknown_slot")
        state["revealed_slots"].append(slot_name)
        revealed.append(slot_name)
    return list(reversed(revealed))


def compact_turn_history(turns: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    history = []
    for turn in turns:
        history.append(
            {
                "role": str(turn.get("role") or ""),
                "action": str(turn.get("action") or ""),
                "text": str(turn.get("text") or "")[:180],
            }
        )
    return history


def clone_sim_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "slots": [dict(slot) for slot in state["slots"]],
        "revealed_slots": list(state["revealed_slots"]),
        "used_opening": state["used_opening"],
        "solution_seen": state["solution_seen"],
        "clarification_count": state["clarification_count"],
        "persona_id": state["persona_id"],
    }


def restore_sim_state(state: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    state["slots"] = [dict(slot) for slot in snapshot["slots"]]
    state["revealed_slots"] = list(snapshot["revealed_slots"])
    state["used_opening"] = snapshot["used_opening"]
    state["solution_seen"] = snapshot["solution_seen"]
    state["clarification_count"] = snapshot["clarification_count"]
    state["persona_id"] = snapshot["persona_id"]


def rewrite_user_utterance(
    text: str,
    action: str,
    pattern: Dict[str, Any],
    scenario: str,
    persona: Dict[str, Any],
    agent_response: Optional[str],
    rewrite_client: LocalAIClient,
) -> str:
    if isinstance(rewrite_client, MockLocalAIClient):
        return text
    prompt = build_rewrite_prompt(text, action, pattern, scenario, persona, agent_response)
    try:
        rewritten = rewrite_client.generate(prompt).strip()
    except Exception as exc:
        print(f"rewrite failed for {pattern.get('case_id')}: {exc}", flush=True)
        return text
    rewritten = strip_wrapping_quotes(rewritten)
    if not rewritten:
        return text
    if len(rewritten) > 160:
        return text
    return rewritten


def build_rewrite_prompt(
    text: str,
    action: str,
    pattern: Dict[str, Any],
    scenario: str,
    persona: Dict[str, Any],
    agent_response: Optional[str],
) -> str:
    payload = {
        "case_grounding_line": {
            "case_id": pattern.get("case_id"),
            "case_to_question_summary": case_understanding(pattern).get("case_to_question_summary", ""),
            "surface_problem_patterns": str_list(behavior_model(pattern), "surface_problem_patterns")[:5],
            "opening_examples": str_list(behavior_model(pattern), "initial_question_patterns")[:3],
            "evaluation_focus": str_list(simulation_plan(pattern), "evaluation_focus")[:5],
        },
        "persona_behavior_line": {
            "scenario": scenario,
            "persona_id": persona.get("persona_id"),
            "persona_name": persona.get("name"),
            "technical_level": persona.get("technical_level"),
            "clarity": persona.get("clarity"),
            "cooperation": persona.get("cooperation"),
            "patience": persona.get("patience"),
            "disclosure_style": persona.get("disclosure_style"),
            "language_style": persona.get("language_style"),
            "behavior_rules": persona.get("behavior_rules", []),
            "dialogue_observed_expression_style": str_list(behavior_model(pattern), "expression_style_patterns"),
        },
        "current_turn": {
            "user_action": action,
            "agent_response": agent_response or "",
            "selected_user_content": text,
        },
        "constraints": [
            "只输出一句用户会说的话",
            "不要替客服回答",
            "不要新增具体电话、邮箱、URL、账号、人员姓名",
            "不要改变 selected_user_content 必须表达的信息",
            "必须保持 case_grounding_line 中的目标问题，不要转移到其他 case",
            "按照 persona_behavior_line 的技术水平、配合程度、耐心和语言风格表达",
            "长度控制在80个中文字符以内",
        ],
    }
    return f"""
你是企业内部客服问答场景中的用户话语改写器。

任务：根据两条主线改写用户下一句话。

主线1：Case Grounding 决定用户遇到什么问题、最终通向哪个 case。
主线2：Persona / Behavior 决定用户怎么表达、是否配合、是否容易困惑。

你只能润色 selected_user_content，不允许改变用户状态，不允许新增事实。

输入：
{json.dumps(payload, ensure_ascii=False, indent=2)}

请只输出改写后的用户话语，不要输出 JSON、解释或代码块。
""".strip()


def strip_wrapping_quotes(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:text|json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    if text.startswith("{") and text.endswith("}"):
        return ""
    return text.strip('"“”')


def case_understanding(pattern: Dict[str, Any]) -> Dict[str, Any]:
    value = pattern.get("case_understanding")
    return value if isinstance(value, dict) else {}


def behavior_model(pattern: Dict[str, Any]) -> Dict[str, Any]:
    value = pattern.get("behavior_model")
    return value if isinstance(value, dict) else {}


def simulation_plan(pattern: Dict[str, Any]) -> Dict[str, Any]:
    value = pattern.get("simulation_plan")
    return value if isinstance(value, dict) else {}


def str_list(record: Dict[str, Any], key: str) -> List[str]:
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def dict_list(record: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def compact_behavior_model(pattern: Dict[str, Any]) -> Dict[str, Any]:
    behavior = behavior_model(pattern)
    return {
        "surface_problem_patterns": str_list(behavior, "surface_problem_patterns")[:5],
        "initial_question_patterns": str_list(behavior, "initial_question_patterns")[:5],
        "common_missing_slots": str_list(behavior, "common_missing_slots")[:8],
        "expression_style_patterns": str_list(behavior, "expression_style_patterns")[:5],
    }


def compact_simulation_plan(pattern: Dict[str, Any]) -> Dict[str, Any]:
    plan = simulation_plan(pattern)
    return {
        "opening_question_templates": str_list(plan, "opening_question_templates")[:5],
        "evaluation_focus": str_list(plan, "evaluation_focus")[:8],
    }


def build_initial_state(pattern: Dict[str, Any], scenario: str, persona: Dict[str, Any]) -> Dict[str, Any]:
    slots = normalize_slots(pattern)
    persona_id = str(persona.get("persona_id") or "")
    if scenario == "vague_user" or persona_id in {"vague_low_context", "screenshot_dependent"}:
        slots = slots + slots[:1]
    if scenario == "difficult_user" or persona_id == "low_tech_confused":
        slots = slots + [
            {
                "slot": "用户不理解术语",
                "ask_label": "用户是否理解操作步骤",
                "example_user_phrase": "这个我不太懂，能说简单点吗？",
            }
        ]
    if persona_id == "tried_and_failed":
        slots = slots + [
            {
                "slot": "用户已尝试常规方案但失败",
                "ask_label": "是否已经尝试过常规处理",
                "example_user_phrase": "我刚才其实已经试过一次了，但还是不行。",
            }
        ]
    return {
        "slots": slots,
        "revealed_slots": [],
        "used_opening": "",
        "solution_seen": False,
        "clarification_count": 0,
        "persona_id": persona.get("persona_id"),
    }


def next_user_utterance(
    pattern: Dict[str, Any],
    state: Dict[str, Any],
    agent_response: Optional[str],
    scenario: str,
    user_turn_id: int,
    persona: Dict[str, Any],
) -> tuple[str, str]:
    persona_id = str(persona.get("persona_id") or "")
    if user_turn_id == 1:
        opening = choose_opening(pattern, scenario, persona)
        if persona_id == "high_tech_diagnostic" and state["slots"]:
            early_phrases = []
            for _ in range(min(2, len(state["slots"]))):
                slot = state["slots"].pop(0)
                state["revealed_slots"].append(str(slot.get("slot") or "unknown_slot"))
                phrase = str(slot.get("example_user_phrase") or slot.get("slot") or "").strip()
                if phrase:
                    early_phrases.append(phrase)
            if early_phrases:
                opening = append_suffix_once(opening, "我把信息也补一下：" + "；".join(early_phrases))
        state["used_opening"] = opening
        return opening, "opening"

    agent_response = agent_response or ""
    if looks_like_solution(agent_response):
        state["solution_seen"] = True
        if (scenario == "difficult_user" or persona_id in {"low_tech_confused", "tried_and_failed"}) and state["slots"]:
            if persona_id == "tried_and_failed":
                return "这个方法我好像已经试过了，还是没解决。", "solution_failed"
            return "我还是不太确定该点哪里，能不能再具体一点？", "ask_more_detail"
        if persona_id == "impatient_user":
            return "行，我先试。要是还不行我再反馈。", "accept_solution"
        return "好的，那我先按这个试一下，谢谢。", "accept_solution"

    if looks_like_clarification(agent_response) and state["slots"]:
        state["clarification_count"] += 1
        slot = state["slots"].pop(0)
        state["revealed_slots"].append(str(slot.get("slot") or "unknown_slot"))
        phrase = str(slot.get("example_user_phrase") or "").strip()
        if phrase:
            return apply_persona_style(apply_scenario_style(phrase, scenario), persona, "reveal_slot"), "reveal_slot"
        label = slot.get("slot") or "相关信息"
        return apply_persona_style(apply_scenario_style(f"我补充一下，{label} 是这样的。", scenario), persona, "reveal_slot"), "reveal_slot"

    if state["slots"]:
        slot = state["slots"].pop(0)
        state["revealed_slots"].append(str(slot.get("slot") or "unknown_slot"))
        return apply_persona_style(apply_scenario_style(str(slot.get("example_user_phrase") or slot.get("slot")), scenario), persona, "proactive_followup"), "proactive_followup"

    if persona_id == "impatient_user":
        return "我这边比较急，能不能直接告诉我下一步怎么处理？", "ask_more_detail"
    if scenario == "difficult_user" or persona_id == "low_tech_confused":
        return "我这边还是没弄好，是不是还缺什么信息？", "ask_more_detail"
    return "我这边能提供的信息就这些了。", "no_more_info"


def choose_opening(pattern: Dict[str, Any], scenario: str, persona: Dict[str, Any]) -> str:
    openings = str_list(simulation_plan(pattern), "opening_question_templates") or str_list(
        behavior_model(pattern), "initial_question_patterns"
    )
    surfaces = str_list(behavior_model(pattern), "surface_problem_patterns")
    persona_id = str(persona.get("persona_id") or "")
    if scenario == "vague_user" or persona_id == "vague_low_context":
        if surfaces:
            return apply_persona_style(make_vague_opening(surfaces[0]), persona, "opening")
        return "我这边有个问题，帮我看一下。"
    if persona_id == "screenshot_dependent":
        base = surfaces[0] if surfaces else (openings[0] if openings else "这里有个报错。")
        return apply_persona_style(make_vague_opening(base), persona, "opening")
    if scenario == "difficult_user" or persona_id == "low_tech_confused":
        base = openings[0] if openings else (surfaces[0] if surfaces else "这个功能用不了。")
        return apply_persona_style(apply_scenario_style(base, scenario), persona, "opening")
    if persona_id == "impatient_user":
        base = openings[0] if openings else (surfaces[0] if surfaces else "你好，帮我看一个问题。")
        return apply_persona_style(base, persona, "opening")
    return apply_persona_style(openings[0] if openings else (surfaces[0] if surfaces else "你好，帮我看一个问题。"), persona, "opening")


def normalize_slots(pattern: Dict[str, Any]) -> List[Dict[str, str]]:
    slots: List[Dict[str, str]] = []
    for item in dict_list(simulation_plan(pattern), "slot_reveal_plan"):
        if isinstance(item, dict):
            slot_name = str(item.get("slot") or "").strip()
            phrase = str(item.get("example_user_phrase") or "").strip()
            if slot_name or phrase:
                slots.append(
                    {
                        "slot": slot_name or phrase,
                        "ask_label": slot_name or "相关信息",
                        "example_user_phrase": phrase,
                    }
                )
    for value in str_list(behavior_model(pattern), "hidden_facts"):
        slots.append({"slot": value, "ask_label": "相关细节", "example_user_phrase": hidden_fact_to_user_phrase(value)})
    for value in str_list(behavior_model(pattern), "common_missing_slots"):
        slots.append(
            {
                "slot": value,
                "ask_label": value,
                "example_user_phrase": f"这个我一开始没说，{value}我还不太确定。",
            }
        )
    return dedupe_slots(slots)


def mock_agent_step(pattern: Dict[str, Any], user_turn_id: int, user_text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    if user_turn_id == 1 and state["slots"]:
        missing = state["slots"][0].get("ask_label") or "具体信息"
        return {
            "action": "ask_clarification",
            "text": f"请问能否补充一下{missing}？",
        }
    if state["slots"] and state["clarification_count"] < 2:
        missing = state["slots"][0].get("ask_label") or "具体信息"
        return {
            "action": "ask_clarification",
            "text": f"还需要确认一下{missing}，方便定位问题。",
        }
    return {
        "action": "answer",
        "text": f"可以参考知识 {pattern.get('case_id')} 的处理步骤，我建议你先按对应流程操作。",
        "recommended_case_id": pattern.get("case_id"),
    }


def clean_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def dedupe_slots(slots: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result = []
    for slot in slots:
        key = slot.get("slot") or slot.get("example_user_phrase")
        if key in seen:
            continue
        seen.add(key)
        result.append(slot)
    return result


def make_vague_opening(text: str) -> str:
    text = text.strip("。；;，, ")
    if len(text) > 24:
        text = text[:24]
    return f"{text}，帮我看下。"


def apply_scenario_style(text: str, scenario: str) -> str:
    text = text.strip()
    if scenario == "difficult_user":
        text = text.rstrip("。！？；，,.!?; ")
        if len(text) < 50:
            return f"{text}，我不太懂这个怎么处理"
        return f"{text}。我不太懂这个怎么处理"
    return text


def apply_persona_style(text: str, persona: Dict[str, Any], action: str) -> str:
    text = text.strip()
    persona_id = str(persona.get("persona_id") or "")
    if not text:
        return text

    if persona_id == "impatient_user":
        if action == "opening":
            return append_suffix_once(text, "这个挺影响我工作的，能尽快看下吗？")
        if action in {"reveal_slot", "proactive_followup"}:
            return append_suffix_once(text, "能不能快点定位一下？")

    if persona_id == "low_tech_confused":
        if "不太懂" not in text and action != "opening":
            return append_suffix_once(text, "我不太懂这个要怎么看。")

    if persona_id == "vague_low_context":
        if action == "opening":
            return make_vague_opening(text)
        if "不太清楚" not in text and len(text) < 55:
            return append_suffix_once(text, "其他我也不太清楚。")

    if persona_id == "screenshot_dependent":
        if action == "opening":
            return append_suffix_once(text, "我这边像是有个提示，如图那种。")
        if len(text) < 55 and "截图" not in text and "图" not in text:
            return append_suffix_once(text, "我这边截图里就是这样显示的。")

    if persona_id == "tried_and_failed":
        if action in {"reveal_slot", "proactive_followup"} and "试过" not in text and len(text) < 55:
            return append_suffix_once(text, "我刚才也试过一次。")

    if persona_id == "high_tech_diagnostic":
        if action == "opening" and "环境" not in text and len(text) < 80:
            return append_suffix_once(text, "我可以把环境和复现步骤一起提供。")

    return text


def append_suffix_once(text: str, suffix: str) -> str:
    text = text.rstrip("。！？；，,.!?; ")
    suffix = suffix.strip()
    if suffix in text:
        return text
    return f"{text}，{suffix}" if not suffix.startswith(("。", "！", "？")) else f"{text}{suffix}"


def hidden_fact_to_user_phrase(text: str) -> str:
    text = text.strip()
    replacements = (
        ("用户是否", "我还不确定是否"),
        ("用户未主动提及", "我刚才还没说"),
        ("用户未说明是否", "我还没说是否"),
        ("用户未明确提到是否", "我还没说是否"),
        ("用户未提及", "我刚才还没说"),
        ("用户可能不知道", "我不太清楚"),
        ("用户可能不清楚", "我不太清楚"),
        ("用户可能不了解", "我不太了解"),
        ("用户可能未", "我可能还没"),
    )
    for old, new in replacements:
        if text.startswith(old):
            return new + text[len(old) :]
    if text.startswith("是否"):
        return "我还不确定" + text
    if text.startswith("未"):
        return "我还没" + text[1:]
    return text


def mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, list):
        return [mask_value(item) for item in value]
    if isinstance(value, dict):
        return {key: mask_value(item) for key, item in value.items()}
    return value


def mask_text(text: str) -> str:
    text = URL_RE.sub("[URL]", text)
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[NUMBER]", text)
    text = LONG_ID_RE.sub("[NUMBER]", text)
    return text


def default_readable_path(output_path: Path) -> Path:
    if output_path.suffix == ".jsonl":
        return output_path.with_suffix(".readable.md")
    return output_path.with_name(output_path.name + ".readable.md")


def build_readable_report(results: List[Dict[str, Any]]) -> str:
    lines = ["# Simulated Dialogues", ""]
    for index, result in enumerate(results, start=1):
        case_id = result.get("case_id") or "UNKNOWN"
        scenario = result.get("scenario") or result.get("mode") or "unknown"
        lines.append(f"## {index}. {case_id} ({scenario})")
        summary = result.get("case_to_question_summary")
        if not summary:
            summary = (result.get("case_understanding") or {}).get("case_to_question_summary")
        if summary:
            lines.append(f"- case to question: {summary}")
        persona = result.get("persona") or {}
        if persona:
            lines.append(f"- persona: {persona.get('name') or persona.get('persona_id')} ({persona.get('persona_id')})")
            if persona.get("summary"):
                lines.append(f"- persona summary: {persona.get('summary')}")
        focus = (result.get("simulation_plan_summary") or {}).get("evaluation_focus") or []
        if focus:
            lines.append(f"- evaluation focus: {'；'.join(str(item) for item in focus[:3])}")
        lines.append("")
        lines.append("### Dialogue")
        for turn in result.get("turns") or []:
            role = "用户" if turn.get("role") == "user" else "客服"
            turn_id = turn.get("turn_id", "")
            action = turn.get("action", "")
            text = str(turn.get("text") or "")
            lines.append(f"**{role} {turn_id}** [{action}]: {text}")
            if turn.get("recommended_case_id"):
                lines.append(f"> recommended_case_id: {turn.get('recommended_case_id')}")
            if turn.get("replay_dialogue_id"):
                lines.append(
                    f"> replay: {turn.get('replay_dialogue_id')}#{turn.get('replay_turn_index')}"
                )
            revealed = turn.get("revealed_slots") or []
            if revealed and turn.get("role") == "user":
                lines.append(f"> revealed: {'；'.join(str(item) for item in revealed[-3:])}")
            lines.append("")
        final_state = result.get("final_state") or {}
        remaining = final_state.get("remaining_slots") or []
        if remaining:
            lines.append("### Remaining Slots")
            for slot in remaining[:8]:
                lines.append(f"- {slot}")
            lines.append("")
    return "\n".join(lines)


def looks_like_clarification(text: str) -> bool:
    return any(hint in text for hint in CLARIFICATION_HINTS)


def looks_like_solution(text: str) -> bool:
    return any(hint in text for hint in SOLUTION_HINTS)


if __name__ == "__main__":
    main()
