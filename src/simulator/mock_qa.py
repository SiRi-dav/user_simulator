from __future__ import annotations

from typing import Dict, List, Optional

from .schemas import AgentStep


class MockEnterpriseQA:
    """Small deterministic QA opponent for local Phase-1 validation."""

    def __init__(self, target_case_id: Optional[str] = None, target_title: Optional[str] = None):
        self.target_case_id = target_case_id
        self.target_title = target_title
        self.turn_id = 0
        self.seen_text: List[str] = []

    def step(self, user_utterance: str) -> AgentStep:
        self.turn_id += 1
        self.seen_text.append(user_utterance)
        merged = " ".join(self.seen_text)

        if self.turn_id == 1 and not self._has_specific_signal(merged):
            return AgentStep(
                response="请问具体有什么报错、编号或者系统页面提示吗？",
                action="ask_clarification",
            )

        if self.target_case_id and (self.turn_id >= 2 or self._has_specific_signal(merged)):
            return AgentStep(
                response=f"可以参考知识 {self.target_case_id}：{self.target_title or '相关处理流程'}。",
                recommended_case_id=self.target_case_id,
                action="respond",
                evidence=[{"case_id": self.target_case_id, "title": self.target_title}],
            )

        return AgentStep(
            response="我先记录一下，请再补充一下发生问题的系统和具体操作。",
            action="ask_clarification",
        )

    @staticmethod
    def _has_specific_signal(text: str) -> bool:
        return any(token in text for token in ("报错", "错误", "ID", "账号", "密码", "VPN", "链接", "流程"))

