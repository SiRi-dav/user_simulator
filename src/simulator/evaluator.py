from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import FailureType, UserState


def evaluate_dialogue(
    target_case_id: Optional[str],
    turns: List[Dict[str, Any]],
    final_user_state: UserState,
    max_turns: int,
) -> Dict[str, Any]:
    agent_turns = [turn for turn in turns if turn.get("role") == "agent"]
    user_turns = [turn for turn in turns if turn.get("role") == "user"]
    recommended_ids = [
        turn.get("recommended_case_id")
        for turn in agent_turns
        if turn.get("recommended_case_id")
    ]
    final_recommended_id = recommended_ids[-1] if recommended_ids else None
    success = bool(target_case_id and final_recommended_id == target_case_id)

    clarification_count = sum(
        1 for turn in agent_turns if turn.get("action") in {"ask_clarification", "ask_missing_slot"}
    )
    evidence_count = sum(len(turn.get("evidence", [])) for turn in agent_turns)

    if success:
        failure_type = FailureType.SUCCESS
    elif final_user_state.end_reason == "patience_exhausted":
        failure_type = FailureType.USER_GAVE_UP
    elif len(user_turns) >= max_turns:
        failure_type = FailureType.TIMEOUT
    elif evidence_count == 0 and target_case_id:
        failure_type = FailureType.RETRIEVAL_FAIL
    elif clarification_count >= 3:
        failure_type = FailureType.OVER_CLARIFICATION
    elif final_recommended_id and target_case_id and final_recommended_id != target_case_id:
        failure_type = FailureType.SELECTION_FAIL
    else:
        failure_type = FailureType.UNKNOWN

    return {
        "target_case_id": target_case_id,
        "recommended_case_id": final_recommended_id,
        "success": success,
        "failure_type": failure_type.value,
        "n_user_turns": len(user_turns),
        "n_agent_turns": len(agent_turns),
        "clarification_count": clarification_count,
        "final_patience": final_user_state.patience,
        "user_end_reason": final_user_state.end_reason,
    }

