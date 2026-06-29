from __future__ import annotations

from copy import deepcopy

from .schemas import DifficultyConfig, UserGoalSeed


def apply_difficulty(seed: UserGoalSeed, difficulty: DifficultyConfig) -> UserGoalSeed:
    result = deepcopy(seed)

    if difficulty.info_density <= 1:
        all_facts = (
            result.reveal_schedule.initial
            + result.reveal_schedule.on_clarification
            + result.reveal_schedule.deep_followup
        )
        result.reveal_schedule.initial = all_facts
        result.reveal_schedule.on_clarification = []
        result.reveal_schedule.deep_followup = []
    elif difficulty.info_density >= 4 and len(result.reveal_schedule.initial) > 1:
        result.reveal_schedule.on_clarification = (
            result.reveal_schedule.initial[1:] + result.reveal_schedule.on_clarification
        )
        result.reveal_schedule.initial = result.reveal_schedule.initial[:1]

    if difficulty.precision >= 4:
        result.persona.tech_level = "low"
    elif difficulty.precision <= 1:
        result.persona.tech_level = "high"

    if difficulty.cooperation >= 4:
        result.persona.cooperation = "low"
        result.persona.patience = "low"
    elif difficulty.cooperation <= 1:
        result.persona.cooperation = "high"

    if difficulty.emotion >= 4:
        result.persona.emotion = "impatient"

    result.metadata["difficulty"] = {
        "info_density": difficulty.info_density,
        "precision": difficulty.precision,
        "noise": difficulty.noise,
        "cooperation": difficulty.cooperation,
        "consistency": difficulty.consistency,
        "emotion": difficulty.emotion,
    }
    return result

