from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from analyzer import append_jsonl, parse_pattern, pattern_from_dict
from data_loader import load_cases
from local_ai_client import build_local_ai_client
from output_writer import build_readable_patterns_report
from prompt_templates import build_case_only_question_pattern_prompt
from schemas import CaseQuestionPattern, to_dict
from utils import parse_simple_yaml, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze cases without dialogue history.")
    parser.add_argument("--config", default="config.yaml", help="Config file with case path and local_ai settings")
    parser.add_argument("--output-dir", default="outputs_case_only", help="Output directory")
    parser.add_argument("--max-cases", type=int, default=20, help="Maximum cases to analyze. Use 0 for all.")
    parser.add_argument("--case-id", default="", help="Optional single case_id")
    parser.add_argument("--resume", action="store_true", help="Resume from existing output JSONL")
    parser.add_argument("--retries", type=int, default=2, help="Retries per case after a failed local AI request")
    parser.add_argument("--retry-delay", type=float, default=5.0, help="Seconds to wait between retries")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = parse_simple_yaml(config_path)
    base_dir = config_path.parent
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "question_patterns.case_only.jsonl"
    readable_path = output_dir / "question_patterns.case_only.readable.md"
    error_path = output_dir / "analysis_errors.case_only.jsonl"

    paths = config.get("paths", {})
    cases_path = resolve_path(base_dir, paths["cases"])
    case_fields = config.get("case_fields", {})
    cases = load_cases(cases_path, case_fields)
    if args.case_id:
        cases = [case for case in cases if case.case_id == args.case_id]
    if args.max_cases > 0:
        cases = cases[: args.max_cases]

    completed_ids = load_completed_case_ids(output_path) if args.resume else set()
    ai_client = build_local_ai_client(config.get("local_ai", {"provider": "mock"}))

    patterns: List[CaseQuestionPattern] = []
    errors: List[Dict[str, Any]] = []
    if args.resume and output_path.exists():
        for record in read_jsonl(output_path):
            patterns.append(pattern_from_dict(record))

    for index, case in enumerate(cases, start=1):
        if case.case_id in completed_ids:
            continue
        print(f"[{index}/{len(cases)}] Analyzing case-only {case.case_id}", flush=True)
        prompt = build_case_only_question_pattern_prompt(case)
        try:
            raw_response = generate_with_retries(
                ai_client,
                prompt,
                case_id=case.case_id,
                retries=args.retries,
                retry_delay=args.retry_delay,
            )
            pattern = parse_pattern(case.case_id, raw_response)
            patterns.append(pattern)
            append_jsonl(output_path, to_dict(pattern))
            if pattern.parse_error:
                errors.append({"case_id": case.case_id, "error": pattern.parse_error, "raw_response": raw_response})
                append_jsonl(error_path, errors[-1])
        except Exception as exc:
            error = {"case_id": case.case_id, "error": str(exc)}
            errors.append(error)
            append_jsonl(error_path, error)
            print(f"case-only analysis failed for {case.case_id}: {exc}", flush=True)

    write_jsonl([to_dict(pattern) for pattern in patterns], output_path)
    write_jsonl(errors, error_path)
    readable_path.write_text(build_readable_patterns_report(patterns), encoding="utf-8")
    print(f"Analyzed cases: {len(patterns)}")
    print(f"Output written to: {output_path}")
    print(f"Readable output written to: {readable_path}")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_completed_case_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(record.get("case_id")) for record in read_jsonl(path) if record.get("case_id")}


def generate_with_retries(ai_client, prompt: str, case_id: str, retries: int, retry_delay: float) -> str:
    max_attempts = max(1, retries + 1)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return ai_client.generate(prompt)
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            print(
                f"case-only analysis retry {attempt}/{retries} for {case_id}: {exc}",
                flush=True,
            )
            time.sleep(max(0.0, retry_delay))
    raise RuntimeError(str(last_error))


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


if __name__ == "__main__":
    main()
