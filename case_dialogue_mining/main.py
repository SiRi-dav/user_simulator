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
    parser.add_argument("--skip-analysis", action="store_true", help="Only mine pairs and write reports, without calling AI")
    parser.add_argument("--resume-analysis", action="store_true", help="Resume from outputs/question_patterns.partial.jsonl")
    parser.add_argument("--max-cases", type=int, default=None, help="Override analysis.max_cases from config")
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
    analysis_config = config.get("analysis", {})
    max_cases = args.max_cases if args.max_cases is not None else int(analysis_config.get("max_cases", 0))
    analysis_pairs = select_pairs_for_analysis(pairs, max_cases)

    if args.skip_analysis:
        patterns, errors = [], []
    else:
        client = build_local_ai_client(config.get("local_ai", {"provider": "mock"}))
        patterns, errors = analyze_pairs(
            analysis_pairs,
            client,
            analysis_config,
            checkpoint_path=output_dir / "question_patterns.partial.jsonl",
            error_checkpoint_path=output_dir / "analysis_errors.partial.jsonl",
            resume=args.resume_analysis,
        )
    write_outputs(pairs, patterns, errors, stats, output_dir)

    print(f"Loaded cases: {len(cases)}")
    print(f"Loaded dialogues: {len(dialogues)}")
    print(f"Matched cases: {stats.matched_cases}")
    print(f"Matched dialogues: {stats.matched_dialogues}")
    print(f"Analyzed cases: {0 if args.skip_analysis else len(analysis_pairs)}")
    print(f"Outputs written to: {output_dir}")


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def select_pairs_for_analysis(pairs, max_cases: int):
    ranked = sorted(pairs, key=lambda pair: len(pair.dialogues), reverse=True)
    if max_cases and max_cases > 0:
        return ranked[:max_cases]
    return ranked


if __name__ == "__main__":
    main()
