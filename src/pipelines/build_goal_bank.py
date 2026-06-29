from __future__ import annotations

import argparse
from pathlib import Path

from src.simulator.data_loader import load_dialogues, write_jsonl
from src.simulator.goal_extractor import extract_goal_seed
from src.simulator.llm_client import build_llm_client
from src.simulator.schemas import to_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Build user goal/profile seeds from normalized dialogues.")
    parser.add_argument("--input", required=True, help="Normalized dialogue JSONL path")
    parser.add_argument("--output", required=True, help="Output goal bank JSONL path")
    parser.add_argument("--llm-provider", default="mock", choices=["mock", "openai-compatible"])
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--llm-api-key-env", default="LLM_API_KEY")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-timeout", type=int, default=60)
    parser.add_argument("--llm-temperature", type=float, default=0.2)
    args = parser.parse_args()

    llm = None
    if args.llm_provider != "mock":
        llm = build_llm_client(
            provider=args.llm_provider,
            base_url=args.llm_base_url,
            api_key=args.llm_api_key,
            api_key_env=args.llm_api_key_env,
            model=args.llm_model,
            timeout=args.llm_timeout,
            temperature=args.llm_temperature,
        )

    dialogues = load_dialogues(Path(args.input))
    seeds = [to_dict(extract_goal_seed(dialogue, llm=llm)) for dialogue in dialogues]
    write_jsonl(seeds, Path(args.output))
    print(f"Built {len(seeds)} goal seeds -> {args.output}")


if __name__ == "__main__":
    main()
