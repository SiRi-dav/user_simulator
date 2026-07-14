from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.openai_compatible_client import OpenAICompatibleClient
from src.schemas import (
    KnowledgeRoadmapArtifact,
    Point,
    Roadmap,
    RuntimePoint,
    RuntimeRelation,
    RuntimeRoadmap,
)
from src.simulator_evaluator import SimulatorEvaluator
from src.utils.jsonl import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the current User Simulator 2.0 evaluator on simulation_logs.jsonl."
    )
    parser.add_argument("--output-dir", default="outputs", help="Directory containing simulation_logs.jsonl and knowledge_roadmaps.jsonl.")
    parser.add_argument("--dialogues", required=True, help="Historical real dialogue JSON/JSONL path.")
    parser.add_argument("--case-id")
    parser.add_argument("--case-ids", nargs="*")
    parser.add_argument("--case-ids-file", help="Plain text file with one case_id per line.")
    parser.add_argument("--judge", action="store_true", help="Use LLM judge as primary score.")
    parser.add_argument("--session-policy", choices=("all", "latest", "first"), default="all")
    args = parser.parse_args()

    output_dir = resolve_path(args.output_dir)
    dialogues_path = resolve_path(args.dialogues)
    case_ids = collect_case_ids(args)
    if not case_ids:
        parser.error("Provide --case-id, --case-ids, or --case-ids-file.")
    if not dialogues_path.exists():
        parser.error(f"Real dialogue file does not exist: {dialogues_path}")

    knowledge_artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    llm_client = OpenAICompatibleClient.from_config({}) if args.judge else None
    evaluator = SimulatorEvaluator(output_dir, knowledge_artifacts, llm_client=llm_client)
    paths = evaluator.evaluate(
        case_ids,
        dialogues_path,
        dialogue_fields=None,
        use_judge=args.judge,
        session_policy=args.session_policy,
    )
    print(f"Exported simulator evaluation to: {output_dir / 'simulator_eval'}")
    for path in paths:
        print(path)


def collect_case_ids(args: argparse.Namespace) -> list[str]:
    case_ids: list[str] = []
    if args.case_id:
        case_ids.append(args.case_id)
    case_ids.extend(str(case_id).strip() for case_id in (args.case_ids or []) if str(case_id).strip())
    if args.case_ids_file:
        for line in resolve_path(args.case_ids_file).read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                case_ids.append(text.split()[0])
    return [case_id for case_id in case_ids if case_id]


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def load_knowledge_roadmaps(path: Path) -> dict[str, KnowledgeRoadmapArtifact]:
    artifacts: dict[str, KnowledgeRoadmapArtifact] = {}
    for record in read_jsonl(path):
        artifact = parse_knowledge_roadmap_artifact(record)
        artifacts[artifact.case_id] = artifact
    return artifacts


def parse_knowledge_roadmap_artifact(record: Dict[str, Any]) -> KnowledgeRoadmapArtifact:
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


if __name__ == "__main__":
    main()
