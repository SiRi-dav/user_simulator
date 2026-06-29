from __future__ import annotations

import argparse
from pathlib import Path

from enterprise_user_simulator.src.simulator.data_loader import load_dialogues, write_jsonl
from enterprise_user_simulator.src.simulator.goal_extractor import extract_goal_seed
from enterprise_user_simulator.src.simulator.schemas import to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Build user goal/profile seeds from normalized dialogues.")
    parser.add_argument("--input", required=True, help="Normalized dialogue JSONL path")
    parser.add_argument("--output", required=True, help="Output goal bank JSONL path")
    args = parser.parse_args()

    dialogues = load_dialogues(Path(args.input))
    seeds = [to_dict(extract_goal_seed(dialogue)) for dialogue in dialogues]
    write_jsonl(seeds, Path(args.output))
    print(f"Built {len(seeds)} goal seeds -> {args.output}")


if __name__ == "__main__":
    main()

