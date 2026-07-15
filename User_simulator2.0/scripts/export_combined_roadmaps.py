from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.review_exporter import render_case_review, safe_filename
from src.schemas import KnowledgeRoadmapArtifact, Point, Roadmap, RuntimePoint, RuntimeRelation, RuntimeRoadmap, model_to_dict
from src.utils.jsonl import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Export all knowledge roadmaps into one Markdown/JSON pair.")
    parser.add_argument("--output-dir", default="outputs", help="Directory containing knowledge_roadmaps.jsonl.")
    parser.add_argument("--output", default="all_knowledge_roadmaps", help="Output filename stem under <output-dir>/review/.")
    parser.add_argument("--case-id", action="append", dest="case_ids", help="Case id to include. Can be repeated.")
    parser.add_argument("--case-ids-file", help="Plain text file with one case_id per line.")
    args = parser.parse_args()

    output_dir = resolve_path(ROOT, args.output_dir)
    review_dir = output_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    case_ids = collect_case_ids(args.case_ids or [], args.case_ids_file)

    artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    debug_artifacts = {}
    selected_ids = case_ids or sorted(artifacts)
    missing = [case_id for case_id in selected_ids if case_id not in artifacts]
    if missing:
        raise ValueError(f"case_id not found in knowledge_roadmaps.jsonl: {', '.join(missing)}")

    selected_artifacts = [artifacts[case_id] for case_id in selected_ids]
    safe_stem = safe_filename(args.output or "all_knowledge_roadmaps")
    md_path = review_dir / f"{safe_stem}.md"
    json_path = review_dir / f"{safe_stem}.json"
    md_path.write_text(render_combined_roadmaps(selected_artifacts, debug_artifacts), encoding="utf-8")
    json_path.write_text(
        json.dumps([model_to_dict(item) for item in selected_artifacts], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Exported combined roadmap files:")
    print(md_path)
    print(json_path)


def render_combined_roadmaps(artifacts, debug_artifacts) -> str:
    lines = ["# All Knowledge Roadmaps", "", f"- case_count: {len(artifacts)}", ""]
    for artifact in artifacts:
        lines.extend([f"---", "", render_case_review(artifact, None, debug_artifacts.get(artifact.case_id)).rstrip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def load_knowledge_roadmaps(path: Path) -> dict[str, KnowledgeRoadmapArtifact]:
    artifacts: dict[str, KnowledgeRoadmapArtifact] = {}
    for record in read_jsonl(path):
        artifact = parse_knowledge_roadmap_artifact(record)
        artifacts[artifact.case_id] = artifact
    return artifacts


def parse_knowledge_roadmap_artifact(record: dict) -> KnowledgeRoadmapArtifact:
    if "target_case" in record:
        title = str((record.get("target_case") or {}).get("title") or "")
        roadmap = Roadmap(**record["roadmap"])
        return KnowledgeRoadmapArtifact(
            case_id=str(record["case_id"]),
            title=title,
            roadmap=build_runtime_roadmap(roadmap),
        )
    return KnowledgeRoadmapArtifact(**record)


def build_runtime_roadmap(roadmap: Roadmap) -> RuntimeRoadmap:
    return RuntimeRoadmap(
        target_case_id=roadmap.target_case_id,
        surface_problem=roadmap.surface_problem,
        opening_intent=roadmap.opening_intent,
        user_facing_points=[build_runtime_point(point) for point in roadmap.user_facing_points],
        diagnostic_points=[build_runtime_point(point) for point in roadmap.diagnostic_points],
        solution_points=[build_runtime_point(point) for point in roadmap.solution_points],
        external_points=[build_runtime_point(point) for point in roadmap.external_points],
        relations=[
            RuntimeRelation(
                from_point_id=relation.from_point_id,
                to_point_id=relation.to_point_id,
                relation_type=relation.relation_type,
            )
            for relation in roadmap.relations
        ],
        target_route=roadmap.target_route,
        external_routes=roadmap.external_routes,
        forbidden_content=roadmap.forbidden_content,
    )


def build_runtime_point(point: Point) -> RuntimePoint:
    return RuntimePoint(
        point_id=point.point_id,
        content=point.content,
        point_type=point.point_type,
        trigger=point.trigger,
        visibility=point.visibility,
    )


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
