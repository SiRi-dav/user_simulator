from __future__ import annotations

import argparse
from pathlib import Path

from analyzer import analyze_pairs
from case_dialogue_matcher import match_cases_and_dialogues
from data_loader import load_cases, load_dialogues
from local_ai_client import build_local_ai_client
from output_writer import write_outputs
from utils import parse_simple_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine case-dialogue pairs and analyze user question patterns.")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = parse_simple_yaml(config_path)
    base_dir = config_path.parent

    paths = config.get("paths", {})
    cases_path = resolve_path(base_dir, paths["cases"])
    dialogues_path = resolve_path(base_dir, paths["dialogues"])
    output_dir = resolve_path(base_dir, paths.get("output_dir", "outputs"))

    cases = load_cases(cases_path, config.get("case_fields", {}))
    dialogues = load_dialogues(dialogues_path, config.get("dialogue_fields", {}))
    pairs, stats = match_cases_and_dialogues(cases, dialogues)

    client = build_local_ai_client(config.get("local_ai", {"provider": "mock"}))
    patterns, errors = analyze_pairs(pairs, client, config.get("analysis", {}))
    write_outputs(pairs, patterns, errors, stats, output_dir)

    print(f"Loaded cases: {len(cases)}")
    print(f"Loaded dialogues: {len(dialogues)}")
    print(f"Matched cases: {stats.matched_cases}")
    print(f"Matched dialogues: {stats.matched_dialogues}")
    print(f"Outputs written to: {output_dir}")


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


if __name__ == "__main__":
    main()

