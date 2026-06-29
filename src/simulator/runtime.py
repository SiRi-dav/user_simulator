from __future__ import annotations

import re
from typing import List, Optional

from .llm_client import LLMClient, MockLLMClient
from .schemas import UserGoalSeed, UserState, UserStep


CLARIFICATION_PATTERNS = ("请问", "能否", "是否", "提供", "确认", "什么", "哪个", "多少")
SOLUTION_PATTERNS = ("可以", "请尝试", "建议", "解决", "修改", "查询", "联系", "参考", "路径", "链接")


class EnterpriseUserSimulator:
    def __init__(self, seed: UserGoalSeed, llm: Optional[LLMClient] = None):
        self.seed = seed
        self.llm = llm or MockLLMClient()
        self.state = UserState(
            pending_initial=list(seed.reveal_schedule.initial),
            pending_clarification=list(seed.reveal_schedule.on_clarification),
            pending_deep=list(seed.reveal_schedule.deep_followup),
            patience=self._initial_patience(seed.persona.patience),
        )

    @staticmethod
    def _initial_patience(label: str) -> int:
        return {"low": 3, "medium": 6, "high": 9}.get(label, 6)

    def step(self, agent_response: Optional[str] = None) -> UserStep:
        self.state.turn_id += 1

        if agent_response is None:
            utterance = self._say_initial()
            return self._wrap(utterance)

        action = self._decide_action(agent_response)
        self._update_patience(agent_response, action)

        if self.state.patience <= 0:
            self.state.should_end = True
            self.state.end_reason = "patience_exhausted"
            return self._wrap("算了，我先自己想办法吧。")

        if action == "confirm_done":
            self.state.should_end = True
            self.state.end_reason = "task_complete"
            return self._wrap("好的，那我先按这个试一下，谢谢。")

        if action == "complain":
            return self._wrap("我刚才已经说过了，能不能直接告诉我怎么处理？")

        facts = self._pick_next_facts(prefer_deep=(action == "deep_followup"))
        if facts:
            self.state.revealed_facts.extend(facts)
            return self._wrap(self._verbalize(facts, agent_response))

        return self._wrap("我这边能看到的就这些了，还是不知道该怎么弄。")

    def _say_initial(self) -> str:
        facts = self._drain(self.state.pending_initial)
        if not facts:
            facts = [self.seed.user_goal]
        self.state.revealed_facts.extend(facts)
        return self._verbalize(facts, None)

    def _decide_action(self, agent_response: str) -> str:
        text = agent_response or ""
        has_pending = bool(self.state.pending_clarification or self.state.pending_deep)
        asks_clarification = any(p in text for p in CLARIFICATION_PATTERNS)
        looks_like_solution = any(p in text for p in SOLUTION_PATTERNS)

        if looks_like_solution and not asks_clarification:
            return "confirm_done"
        if asks_clarification and has_pending:
            return "reveal_more"
        if asks_clarification and not has_pending:
            return "complain"
        if has_pending:
            return "deep_followup"
        return "confirm_done" if looks_like_solution else "clarify"

    def _update_patience(self, agent_response: str, action: str) -> None:
        if action == "complain":
            self.state.patience -= 2
        if any(p in agent_response for p in CLARIFICATION_PATTERNS):
            self.state.repeated_clarifications += 1
            if self.state.repeated_clarifications >= 3:
                self.state.patience -= 1
        else:
            self.state.repeated_clarifications = 0

    def _pick_next_facts(self, prefer_deep: bool = False) -> List[str]:
        if self.seed.persona.cooperation == "low" and self.state.turn_id % 2 == 0:
            return []
        if self.state.pending_clarification and not prefer_deep:
            return self._drain(self.state.pending_clarification, limit=1)
        if self.state.pending_deep:
            return self._drain(self.state.pending_deep, limit=1)
        if self.state.pending_clarification:
            return self._drain(self.state.pending_clarification, limit=1)
        return []

    @staticmethod
    def _drain(values: List[str], limit: Optional[int] = None) -> List[str]:
        if limit is None:
            limit = len(values)
        picked = values[:limit]
        del values[:limit]
        return picked

    def _verbalize(self, facts: List[str], agent_response: Optional[str]) -> str:
        if not facts:
            return "我不太确定。"
        raw = "，".join(facts)
        raw = self._apply_style(raw)
        if agent_response and self.seed.persona.emotion in ("anxious", "impatient"):
            raw = f"{raw}，这个比较急"
        return raw

    def _apply_style(self, text: str) -> str:
        if self.seed.persona.tech_level == "low":
            text = re.sub(r"\bVPN\b", "那个远程连接", text, flags=re.IGNORECASE)
            text = text.replace("错误码", "报错")
        if self.seed.persona.style == "verbose" and len(text) < 30:
            text = f"{text}，我也不太确定是不是这个原因"
        return text

    def _wrap(self, utterance: str) -> UserStep:
        return UserStep(
            turn_id=self.state.turn_id,
            utterance=utterance,
            should_end=self.state.should_end,
            end_reason=self.state.end_reason,
            state=self.state,
        )

