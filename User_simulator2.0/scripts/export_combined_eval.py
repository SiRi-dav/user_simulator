from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.review_exporter import safe_filename
from src.simulator_evaluator import render_case_report, render_eval_summary
from src.utils.jsonl import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Export simulator evaluation results into one Markdown/JSON pair.")
    parser.add_argument("--output-dir", default="outputs", help="Directory containing simulator_eval/simulator_eval.jsonl.")
    parser.add_argument("--output", default="all_simulator_eval", help="Output filename stem under <output-dir>/simulator_eval/.")
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Case id to include. Can be repeated.")
    parser.add_argument("--case-ids-file", help="Plain text file with one case_id per line.")
    args = parser.parse_args()

    output_dir = resolve_path(ROOT, args.output_dir)
    eval_dir = output_dir / "simulator_eval"
    eval_path = eval_dir / "simulator_eval.jsonl"
    reports = [record for record in read_jsonl(eval_path)]
    case_ids = collect_case_ids(args.case_ids or [], args.case_ids_file)
    if case_ids:
        selected = set(case_ids)
        reports = [record for record in reports if str(record.get("case_id")) in selected]
        missing = sorted(selected - {str(record.get("case_id")) for record in reports})
        if missing:
            raise ValueError(f"case_id not found in simulator_eval.jsonl: {', '.join(missing)}")
    if not reports:
        raise ValueError(f"No simulator evaluation records found: {eval_path}")

    safe_stem = safe_filename(args.output or "all_simulator_eval")
    md_path = eval_dir / f"{safe_stem}.md"
    json_path = eval_dir / f"{safe_stem}.json"
    md_path.write_text(render_combined_eval(reports), encoding="utf-8")
    json_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Exported combined evaluation files:")
    print(md_path)
    print(json_path)


def render_combined_eval(reports: list[dict]) -> str:
    lines = [render_eval_summary(reports).rstrip(), ""]
    for report in reports:
        lines.extend(["---", "", render_case_report(report).rstrip(), ""])
    return "\n".join(lines).rstrip() + "\n"


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
