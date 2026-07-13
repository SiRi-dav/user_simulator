from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.v1_current_evaluator import evaluate_v1_outputs_with_current_metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate original main-branch User Simulator outputs with current metric dimensions."
    )
    parser.add_argument("--v1-results", required=True, help="JSONL produced by main branch src.pipelines.run_simulation.")
    parser.add_argument("--dialogues", required=True, help="Real historical dialogue JSON/JSONL file.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for v1_current_eval outputs.")
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Case id to include. Can be repeated.")
    parser.add_argument("--case-ids-file", help="Plain text file with one case_id per line.")
    args = parser.parse_args()

    case_ids = collect_case_ids(args.case_ids or [], args.case_ids_file)
    paths = evaluate_v1_outputs_with_current_metrics(
        v1_results_path=resolve_path(ROOT, args.v1_results),
        real_dialogues_path=resolve_path(ROOT, args.dialogues),
        output_dir=resolve_path(ROOT, args.output_dir),
        case_ids=case_ids or None,
    )
    print("Exported v1-current evaluation files:")
    for path in paths:
        print(path)
    print(resolve_path(ROOT, args.output_dir) / "v1_current_eval")


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


def collect_case_ids(case_ids: list[str], case_ids_file: str | None) -> list[str]:
    selected = [case_id.strip() for case_id in case_ids if case_id.strip()]
    if case_ids_file:
        path = Path(case_ids_file).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                selected.append(text.split()[0])
    return selected


if __name__ == "__main__":
    main()
