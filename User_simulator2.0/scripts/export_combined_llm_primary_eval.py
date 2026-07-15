from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.review_exporter import safe_filename
from src.utils.jsonl import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine LLM-primary evaluation case Markdown files into one document.")
    parser.add_argument("--output-dir", default="outputs", help="Directory containing simulator_eval_llm_primary/.")
    parser.add_argument("--output", default="all_llm_primary_eval", help="Output filename stem under simulator_eval_llm_primary/.")
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Case id to include. Can be repeated.")
    parser.add_argument("--case-ids-file", help="Plain text file with one case_id per line.")
    args = parser.parse_args()

    output_dir = resolve_path(ROOT, args.output_dir)
    eval_dir = output_dir / "simulator_eval_llm_primary"
    if not eval_dir.exists():
        raise FileNotFoundError(f"LLM-primary eval directory does not exist: {eval_dir}")

    reports = load_reports(eval_dir / "simulator_eval_llm_primary.jsonl")
    selected_case_ids = collect_case_ids(args.case_ids or [], args.case_ids_file)
    if selected_case_ids:
        selected = set(selected_case_ids)
        reports = [report for report in reports if str(report.get("case_id")) in selected]
        missing = sorted(selected - {str(report.get("case_id")) for report in reports})
        if missing:
            raise ValueError(f"case_id not found in simulator_eval_llm_primary.jsonl: {', '.join(missing)}")

    case_ids = [str(report.get("case_id")) for report in reports if str(report.get("case_id") or "").strip()]
    if not case_ids:
        case_ids = discover_case_ids_from_markdown(eval_dir, selected_case_ids)
    if not case_ids:
        raise ValueError(f"No case reports found under: {eval_dir}")

    safe_stem = safe_filename(args.output or "all_llm_primary_eval")
    md_path = eval_dir / f"{safe_stem}.md"
    json_path = eval_dir / f"{safe_stem}.json"
    md_path.write_text(render_combined_markdown(eval_dir, case_ids), encoding="utf-8")
    json_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("Exported combined LLM-primary evaluation files:")
    print(md_path)
    print(json_path)


def load_reports(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [record for record in read_jsonl(path)]


def render_combined_markdown(eval_dir: Path, case_ids: list[str]) -> str:
    lines: list[str] = ["# Combined LLM-Primary Simulator Evaluation", ""]
    summary_path = eval_dir / "summary.md"
    if summary_path.exists():
        lines.extend(["## Summary", "", strip_top_heading(summary_path.read_text(encoding="utf-8")).rstrip(), ""])
    lines.extend(["## Case Reports", ""])
    for case_id in case_ids:
        case_path = eval_dir / f"{safe_filename(case_id)}.md"
        if not case_path.exists():
            continue
        lines.extend(["---", "", strip_top_heading(case_path.read_text(encoding="utf-8")).rstrip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def strip_top_heading(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).lstrip()
    return text


def discover_case_ids_from_markdown(eval_dir: Path, selected_case_ids: list[str]) -> list[str]:
    if selected_case_ids:
        return selected_case_ids
    ignored = {"summary.md", "all_llm_primary_eval.md"}
    return [
        path.stem
        for path in sorted(eval_dir.glob("*.md"))
        if path.name not in ignored and not path.name.startswith("all_")
    ]


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
