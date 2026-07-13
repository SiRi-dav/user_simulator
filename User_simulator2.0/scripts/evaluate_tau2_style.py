from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tau2_evaluator import Tau2StyleEvaluator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a tau2-bench-style dual-control proxy evaluation over simulation logs."
    )
    parser.add_argument("--output-dir", default="outputs", help="Directory containing simulation_logs.jsonl and knowledge_roadmaps.jsonl.")
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Case id to include. Can be repeated.")
    parser.add_argument("--case-ids-file", help="Plain text file with one case_id per line.")
    args = parser.parse_args()

    output_dir = resolve_path(ROOT, args.output_dir)
    case_ids = collect_case_ids(args.case_ids or [], args.case_ids_file)
    evaluator = Tau2StyleEvaluator(output_dir)
    paths = evaluator.write_outputs(evaluator.evaluate(case_ids or None))
    print("Exported tau2-style evaluation files:")
    for path in paths:
        print(path)
    print(output_dir / "tau2_eval")


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def collect_case_ids(case_ids: list[str], case_ids_file: str | None) -> list[str]:
    selected = [case_id.strip() for case_id in case_ids if case_id.strip()]
    if case_ids_file:
        path = Path(case_ids_file).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            selected.append(text.split()[0])
    return selected


if __name__ == "__main__":
    main()
