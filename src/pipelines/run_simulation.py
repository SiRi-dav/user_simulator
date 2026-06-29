from __future__ import annotations

import argparse
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List

from enterprise_user_simulator.src.simulator.data_loader import read_jsonl, write_jsonl
from enterprise_user_simulator.src.simulator.evaluator import evaluate_dialogue
from enterprise_user_simulator.src.simulator.mock_qa import MockEnterpriseQA
from enterprise_user_simulator.src.simulator.perturbation import apply_difficulty
from enterprise_user_simulator.src.simulator.runtime import EnterpriseUserSimulator
from enterprise_user_simulator.src.simulator.schemas import (
    DialogueTurn,
    DifficultyConfig,
    RevealSchedule,
    UserGoalSeed,
    UserPersona,
    to_dict,
)


def _filter_dataclass_kwargs(cls: type, obj: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {field.name for field in fields(cls)}
    return {key: value for key, value in obj.items() if key in allowed}


def seed_from_dict(obj: Dict[str, Any]) -> UserGoalSeed:
    schedule = RevealSchedule(**_filter_dataclass_kwargs(RevealSchedule, obj.get("reveal_schedule", {})))
    persona = UserPersona(**_filter_dataclass_kwargs(UserPersona, obj.get("persona", {})))
    source_turns = [
        DialogueTurn(**_filter_dataclass_kwargs(DialogueTurn, turn))
        for turn in obj.get("source_turns", [])
    ]
    return UserGoalSeed(
        dialogue_id=obj["dialogue_id"],
        target_case_id=obj.get("target_case_id"),
        target_title=obj.get("target_title"),
        user_goal=obj.get("user_goal", ""),
        known_facts=obj.get("known_facts", []),
        hidden_facts=obj.get("hidden_facts", []),
        reveal_schedule=schedule,
        persona=persona,
        noise=obj.get("noise", []),
        source_turns=source_turns,
        metadata=obj.get("metadata", {}),
    )


def difficulty_from_name(name: str) -> DifficultyConfig:
    if name == "easy":
        return DifficultyConfig.easy()
    if name == "hard":
        return DifficultyConfig.hard()
    return DifficultyConfig.medium()


def run_one(seed: UserGoalSeed, difficulty: DifficultyConfig, max_turns: int) -> Dict[str, Any]:
    seed = apply_difficulty(seed, difficulty)
    user = EnterpriseUserSimulator(seed)
    qa = MockEnterpriseQA(target_case_id=seed.target_case_id, target_title=seed.target_title)

    turns: List[Dict[str, Any]] = []
    agent_response = None

    for _ in range(max_turns):
        user_step = user.step(agent_response)
        turns.append(
            {
                "role": "user",
                "turn_id": user_step.turn_id,
                "text": user_step.utterance,
                "should_end": user_step.should_end,
                "end_reason": user_step.end_reason,
                "state": to_dict(user_step.state),
            }
        )
        if user_step.should_end:
            break

        agent_step = qa.step(user_step.utterance)
        turns.append(
            {
                "role": "agent",
                "turn_id": user_step.turn_id,
                "text": agent_step.response,
                "recommended_case_id": agent_step.recommended_case_id,
                "action": agent_step.action,
                "evidence": agent_step.evidence,
                "metadata": agent_step.metadata,
            }
        )
        agent_response = agent_step.response
        if agent_step.recommended_case_id == seed.target_case_id and seed.target_case_id:
            break

    metrics = evaluate_dialogue(
        target_case_id=seed.target_case_id,
        turns=turns,
        final_user_state=user.state,
        max_turns=max_turns,
    )
    return {
        "dialogue_id": seed.dialogue_id,
        "target_case_id": seed.target_case_id,
        "difficulty": to_dict(difficulty),
        "turns": turns,
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase-1 user simulator against mock QA.")
    parser.add_argument("--goal-bank", required=True, help="Goal bank JSONL path")
    parser.add_argument("--output", required=True, help="Simulation output JSONL path")
    parser.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of seeds")
    args = parser.parse_args()

    difficulty = difficulty_from_name(args.difficulty)
    seeds = [seed_from_dict(obj) for obj in read_jsonl(Path(args.goal_bank))]
    if args.limit:
        seeds = seeds[: args.limit]

    results = [run_one(seed, difficulty, args.max_turns) for seed in seeds]
    write_jsonl(results, Path(args.output))
    success_count = sum(1 for result in results if result["metrics"]["success"])
    print(f"Ran {len(results)} simulations -> {args.output}")
    print(f"Success: {success_count}/{len(results)}")


if __name__ == "__main__":
    main()

