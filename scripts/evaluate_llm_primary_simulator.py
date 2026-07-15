from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parents[1]
USER_SIMULATOR2_ROOT = ROOT / "User_simulator2.0"
if str(USER_SIMULATOR2_ROOT) not in sys.path:
    sys.path.insert(0, str(USER_SIMULATOR2_ROOT))

from src.llm.openai_compatible_client import OpenAICompatibleClient
from src.llm_primary_simulator_evaluator import LLMPrimarySimulatorEvaluator
from src.schemas import KnowledgeRoadmapArtifact, Point, Roadmap, RuntimePoint, RuntimeRelation, RuntimeRoadmap
from src.utils.jsonl import read_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the LLM-primary evaluator from the original simulator repo root."
    )
    parser.add_argument("--config", help="Optional config YAML. Reads llm and paths.dialogues/output_dir.")
    parser.add_argument("--output-dir", help="Directory containing simulation_logs.jsonl and knowledge_roadmaps.jsonl.")
    parser.add_argument("--dialogues", help="Historical real dialogue JSON/JSONL path.")
    parser.add_argument("--case-id")
    parser.add_argument("--case-ids", nargs="*")
    parser.add_argument("--case-ids-file", help="Plain text file with one case_id per line.")
    parser.add_argument("--session-policy", choices=("all", "latest", "first"), default="all")
    args = parser.parse_args()

    config = load_config(resolve_path(args.config)) if args.config else {}
    output_dir = resolve_path(args.output_dir or nested_get(config, ["paths", "output_dir"]) or "outputs_v1")
    dialogues_path_value = args.dialogues or nested_get(config, ["paths", "dialogues"])
    if not dialogues_path_value:
        parser.error("Provide --dialogues or config paths.dialogues.")
    dialogues_path = resolve_path(str(dialogues_path_value))
    if not dialogues_path.exists():
        parser.error(f"Real dialogue file does not exist: {dialogues_path}")

    case_ids = collect_case_ids(args)
    if not case_ids:
        parser.error("Provide --case-id, --case-ids, or --case-ids-file.")

    knowledge_path = output_dir / "knowledge_roadmaps.jsonl"
    simulation_path = output_dir / "simulation_logs.jsonl"
    if not knowledge_path.exists():
        parser.error(f"knowledge_roadmaps.jsonl does not exist: {knowledge_path}")
    if not simulation_path.exists():
        parser.error(f"simulation_logs.jsonl does not exist: {simulation_path}")

    knowledge_artifacts = load_knowledge_roadmaps(knowledge_path)
    llm_client = OpenAICompatibleClient.from_config(config)
    evaluator = LLMPrimarySimulatorEvaluator(output_dir, knowledge_artifacts, llm_client=llm_client)
    paths = evaluator.evaluate(
        case_ids,
        dialogues_path,
        dialogue_fields=config.get("dialogue_fields") if isinstance(config.get("dialogue_fields"), dict) else None,
        session_policy=args.session_policy,
    )
    print(f"Exported LLM-primary simulator evaluation to: {output_dir / 'simulator_eval_llm_primary'}")
    for path in paths:
        print(path)


def load_config(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            return data
        return {}
    except ImportError:
        return parse_simple_yaml(path)


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


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def nested_get(data: Dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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


def parse_simple_yaml(path: Path) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    stack: list[tuple[int, Dict[str, Any]]] = [(-1, root)]
    last_key_at_indent: Dict[int, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            key = last_key_at_indent.get(indent - 2)
            if key is None:
                continue
            parent_list = parent.setdefault(key, [])
            if isinstance(parent_list, list):
                parent_list.append(parse_yaml_scalar(line[2:].strip()))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        last_key_at_indent[indent] = key
        if value == "":
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_yaml_scalar(value)
    return root


def parse_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


if __name__ == "__main__":
    main()
