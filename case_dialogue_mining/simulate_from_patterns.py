from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from local_ai_client import LocalAIClient, MockLocalAIClient, build_local_ai_client
from utils import read_jsonl, write_jsonl


CLARIFICATION_HINTS = ("请问", "是否", "能否", "提供", "补充", "具体", "哪个", "什么")
SOLUTION_HINTS = ("可以", "建议", "请按", "参考", "解决", "处理", "步骤", "路径")
PHONE_RE = re.compile(r"(?<![A-Za-z0-9])(?:\+?\d[\d\- ]{6,}\d)(?![A-Za-z0-9])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://\S+")
LONG_ID_RE = re.compile(r"(?<![A-Za-z0-9])\d{8,}(?![A-Za-z0-9])")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a lightweight user simulator from question_patterns.jsonl.")
    parser.add_argument("--patterns", default="outputs/question_patterns.jsonl", help="question_patterns.jsonl path")
    parser.add_argument("--output", default="outputs/simulated_dialogues.jsonl", help="Output JSONL path")
    parser.add_argument("--case-id", default="", help="Optional target case_id")
    parser.add_argument("--limit", type=int, default=10, help="Maximum cases to simulate. Use 0 for all.")
    parser.add_argument("--mode", default="replay_like", choices=["replay_like", "vague_user", "difficult_user"])
    parser.add_argument("--max-turns", type=int, default=6, help="Maximum user turns")
    parser.add_argument("--agent", default="mock", choices=["mock", "none"], help="Use mock QA opponent or only emit user plan")
    parser.add_argument("--no-mask", action="store_true", help="Do not mask URLs, emails, phones, or long numeric IDs")
    parser.add_argument("--readable-output", default="", help="Optional readable Markdown output path")
    parser.add_argument("--rewrite-provider", default="mock", choices=["mock", "openai-compatible"], help="LLM provider for user utterance rewriting")
    parser.add_argument("--rewrite-endpoint", default="http://localhost:8850/v1/chat/completions")
    parser.add_argument("--rewrite-model", default="qwen3-32b")
    parser.add_argument("--rewrite-api-key", default="EMPTY")
    parser.add_argument("--rewrite-api-key-env", default="LOCAL_AI_API_KEY")
    parser.add_argument("--rewrite-temperature", type=float, default=0.7)
    parser.add_argument("--rewrite-max-tokens", type=int, default=256)
    parser.add_argument("--rewrite-timeout", type=int, default=60)
    args = parser.parse_args()

    patterns = [record for record in read_jsonl(Path(args.patterns)) if not record.get("parse_error")]
    if args.case_id:
        patterns = [record for record in patterns if record.get("case_id") == args.case_id]
    if args.limit > 0:
        patterns = patterns[: args.limit]

    rewrite_client = build_rewrite_client(args)
    results = [
        simulate_case(
            pattern,
            mode=args.mode,
            max_turns=args.max_turns,
            agent=args.agent,
            rewrite_client=rewrite_client,
        )
        for pattern in patterns
    ]
    if not args.no_mask:
        results = [mask_value(result) for result in results]
    output_path = Path(args.output)
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


def simulate_case(
    pattern: Dict[str, Any],
    mode: str,
    max_turns: int,
    agent: str,
    rewrite_client: LocalAIClient,
) -> Dict[str, Any]:
    state = build_initial_state(pattern, mode)
    turns: List[Dict[str, Any]] = []
    agent_response: Optional[str] = None

    for user_turn_id in range(1, max_turns + 1):
        user_text, user_action = next_user_utterance(pattern, state, agent_response, mode, user_turn_id)
        user_text = rewrite_user_utterance(
            text=user_text,
            action=user_action,
            pattern=pattern,
            mode=mode,
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

        agent_step = mock_agent_step(pattern, user_turn_id, user_text, state)
        turns.append(
            {
                "role": "agent",
                "turn_id": user_turn_id,
                "text": agent_step["text"],
                "action": agent_step["action"],
                "recommended_case_id": agent_step.get("recommended_case_id"),
            }
        )
        agent_response = agent_step["text"]
        if agent_step["action"] == "answer" and mode != "difficult_user":
            final_text, final_action = next_user_utterance(pattern, state, agent_response, mode, user_turn_id + 1)
            final_text = rewrite_user_utterance(
                text=final_text,
                action=final_action,
                pattern=pattern,
                mode=mode,
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
        "mode": mode,
        "case_to_question_summary": pattern.get("case_to_question_summary", ""),
        "evaluation_focus": pattern.get("evaluation_focus", []),
        "turns": turns,
        "final_state": {
            "revealed_slots": state["revealed_slots"],
            "remaining_slots": [slot["slot"] for slot in state["slots"]],
            "used_opening": state["used_opening"],
        },
    }


def rewrite_user_utterance(
    text: str,
    action: str,
    pattern: Dict[str, Any],
    mode: str,
    agent_response: Optional[str],
    rewrite_client: LocalAIClient,
) -> str:
    if isinstance(rewrite_client, MockLocalAIClient):
        return text
    prompt = build_rewrite_prompt(text, action, pattern, mode, agent_response)
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
    mode: str,
    agent_response: Optional[str],
) -> str:
    payload = {
        "case_id": pattern.get("case_id"),
        "mode": mode,
        "user_action": action,
        "agent_response": agent_response or "",
        "original_user_text": text,
        "user_style_summary": pattern.get("user_style_summary", ""),
        "opening_examples": pattern.get("initial_question_patterns", [])[:3],
        "constraints": [
            "只输出一句用户会说的话",
            "不要替客服回答",
            "不要新增具体电话、邮箱、URL、账号、人员姓名",
            "不要改变原句必须表达的信息",
            "长度控制在80个中文字符以内",
        ],
    }
    return f"""
你是企业内部客服问答场景中的用户话语改写器。

任务：把 original_user_text 改写得更像真实员工用户说的话。
你只能润色表达，不允许改变用户状态，不允许新增事实。

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


def build_initial_state(pattern: Dict[str, Any], mode: str) -> Dict[str, Any]:
    slots = normalize_slots(pattern)
    if mode == "vague_user":
        slots = slots + slots[:1]
    if mode == "difficult_user":
        slots = slots + [
            {
                "slot": "用户不理解术语",
                "ask_label": "用户是否理解操作步骤",
                "example_user_phrase": "这个我不太懂，能说简单点吗？",
            }
        ]
    return {
        "slots": slots,
        "revealed_slots": [],
        "used_opening": "",
        "solution_seen": False,
        "clarification_count": 0,
    }


def next_user_utterance(
    pattern: Dict[str, Any],
    state: Dict[str, Any],
    agent_response: Optional[str],
    mode: str,
    user_turn_id: int,
) -> tuple[str, str]:
    if user_turn_id == 1:
        opening = choose_opening(pattern, mode)
        state["used_opening"] = opening
        return opening, "opening"

    agent_response = agent_response or ""
    if looks_like_solution(agent_response):
        state["solution_seen"] = True
        if mode == "difficult_user" and state["slots"]:
            return "我还是不太确定该点哪里，能不能再具体一点？", "ask_more_detail"
        return "好的，那我先按这个试一下，谢谢。", "accept_solution"

    if looks_like_clarification(agent_response) and state["slots"]:
        state["clarification_count"] += 1
        slot = state["slots"].pop(0)
        state["revealed_slots"].append(str(slot.get("slot") or "unknown_slot"))
        phrase = str(slot.get("example_user_phrase") or "").strip()
        if phrase:
            return apply_mode_style(phrase, mode), "reveal_slot"
        label = slot.get("slot") or "相关信息"
        return apply_mode_style(f"我补充一下，{label} 是这样的。", mode), "reveal_slot"

    if state["slots"]:
        slot = state["slots"].pop(0)
        state["revealed_slots"].append(str(slot.get("slot") or "unknown_slot"))
        return apply_mode_style(str(slot.get("example_user_phrase") or slot.get("slot")), mode), "proactive_followup"

    if mode == "difficult_user":
        return "我这边还是没弄好，是不是还缺什么信息？", "ask_more_detail"
    return "我这边能提供的信息就这些了。", "no_more_info"


def choose_opening(pattern: Dict[str, Any], mode: str) -> str:
    openings = clean_list(pattern.get("opening_question_templates")) or clean_list(pattern.get("initial_question_patterns"))
    surfaces = clean_list(pattern.get("surface_problem_patterns"))
    if mode == "vague_user":
        if surfaces:
            return make_vague_opening(surfaces[0])
        return "我这边有个问题，帮我看一下。"
    if mode == "difficult_user":
        base = openings[0] if openings else (surfaces[0] if surfaces else "这个功能用不了。")
        return apply_mode_style(base, mode)
    return openings[0] if openings else (surfaces[0] if surfaces else "你好，帮我看一个问题。")


def normalize_slots(pattern: Dict[str, Any]) -> List[Dict[str, str]]:
    slots: List[Dict[str, str]] = []
    for item in pattern.get("slot_reveal_plan") or []:
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
    for value in clean_list(pattern.get("hidden_facts")):
        slots.append({"slot": value, "ask_label": "相关细节", "example_user_phrase": hidden_fact_to_user_phrase(value)})
    for value in clean_list(pattern.get("common_missing_slots")):
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


def apply_mode_style(text: str, mode: str) -> str:
    text = text.strip()
    if mode == "difficult_user":
        text = text.rstrip("。！？；，,.!?; ")
        if len(text) < 50:
            return f"{text}，我不太懂这个怎么处理"
        return f"{text}。我不太懂这个怎么处理"
    return text


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
        mode = result.get("mode") or "unknown"
        lines.append(f"## {index}. {case_id} ({mode})")
        summary = result.get("case_to_question_summary")
        if summary:
            lines.append(f"- case to question: {summary}")
        focus = result.get("evaluation_focus") or []
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
