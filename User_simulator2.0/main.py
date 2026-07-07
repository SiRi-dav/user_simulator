from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Dict

from src.behavior_mining.behavior_miner import DialogueBehaviorMiner
from src.behavior_mining.dialogue_loader import load_dialogues
from src.data_loader import get_case, load_cases
from src.extraction.point_extractor import PointExtractor
from src.extraction.point_verifier import PointVerifier
from src.llm.openai_compatible_client import OpenAICompatibleClient
from src.retrieval.query_generator import QueryGenerator
from src.retrieval.related_case_retriever import RelatedCaseRetriever
from src.roadmap.relation_builder import RelationBuilder
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.review_exporter import ReviewExporter
from src.runtime.simulator import Simulator
from src.schemas import (
    BehaviorTaxonomy,
    BlindUserCaseView,
    Case,
    CaseAnalysisDebugArtifact,
    EmployeePersona,
    KnowledgeRoadmapArtifact,
    Point,
    Relation,
    Roadmap,
    RuntimePoint,
    RuntimeRelation,
    RuntimeRoadmap,
    model_to_dict,
)
from src.utils.jsonl import read_jsonl, write_jsonl
from src.utils.logging import OutputLogger


PERSONAS: Dict[str, Dict[str, Any]] = {
    "low_tech": {"name": "low_tech", "style": "不熟悉技术术语，需要更具体的操作说明", "patience": "medium"},
    "cooperative": {"name": "cooperative", "style": "配合、简洁、愿意补充信息", "patience": "high"},
    "impatient": {"name": "impatient", "style": "略急躁，希望尽快解决", "patience": "low"},
    "vague": {"name": "vague", "style": "描述模糊，除非被问到才补充细节", "patience": "medium"},
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "simulate"

    root = Path(__file__).resolve().parent
    config = load_config(root / args.config)
    output_dir = root / str(config.get("paths", {}).get("output_dir", "outputs"))
    logger = OutputLogger(output_dir)

    if command == "mine-behavior":
        run_mine_behavior(args, config, root, output_dir, logger, parser)
        return
    if command == "analyze-cases":
        run_analyze_cases(args, config, root, output_dir, logger, parser)
        return
    if command == "export-review":
        run_export_review(args, output_dir, parser)
        return
    run_simulate(args, config, root, output_dir, logger, parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM-based Knowledge-grounded User Simulator MVP")
    parser.add_argument("--config", default="config.yaml")
    subparsers = parser.add_subparsers(dest="command")

    simulate = subparsers.add_parser("simulate", help="Run target-case user simulation.")
    simulate.add_argument("--config", default="config.yaml")
    add_simulate_args(simulate)

    analyze = subparsers.add_parser("analyze-cases", help="Precompute roadmaps and knowledge artifacts for target cases.")
    analyze.add_argument("--config", default="config.yaml")
    analyze.add_argument("--limit", type=int, default=20)
    analyze.add_argument("--offset", type=int, default=0)
    analyze.add_argument("--case_ids", nargs="*")
    analyze.add_argument("--random", action="store_true", help="Randomly sample --limit cases instead of using offset.")
    analyze.add_argument("--seed", type=int, help="Random seed for --random case sampling.")

    mine = subparsers.add_parser("mine-behavior", help="Mine employee personas and behavior taxonomy from historical dialogues.")
    mine.add_argument("--config", default="config.yaml")
    mine.add_argument("--dialogues", help="Historical dialogue JSON/JSONL path. Defaults to config paths.dialogues.")
    mine.add_argument("--max_dialogues", type=int, default=50)

    review = subparsers.add_parser("export-review", help="Export generated JSONL artifacts into human-readable Markdown.")
    review.add_argument("--config", default="config.yaml")
    review.add_argument("--case_id")
    review.add_argument("--all", action="store_true", help="Export all cases in knowledge_roadmaps.jsonl.")

    # Backward-compatible direct invocation: python main.py --case_id ...
    if len(sys.argv) > 1 and sys.argv[1] not in {"simulate", "mine-behavior", "analyze-cases", "export-review", "-h", "--help"}:
        add_simulate_args(parser)
    return parser


def add_simulate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case_id")
    parser.add_argument("--persona", default="low_tech", choices=sorted(PERSONAS))
    parser.add_argument("--persona_id")
    parser.add_argument("--max_turns", type=int, default=6)
    parser.add_argument("--list_cases", type=int, default=0, help="List the first N cases from the configured case library and exit.")


def run_mine_behavior(
    args: argparse.Namespace,
    config: Dict[str, Any],
    root: Path,
    output_dir: Path,
    logger: OutputLogger,
    parser: argparse.ArgumentParser,
) -> None:
    dialogues_config = args.dialogues or config.get("paths", {}).get("dialogues")
    if not dialogues_config:
        parser.error("Missing dialogue path. Use --dialogues or set paths.dialogues in config.yaml.")
    dialogues_path = resolve_path(root, str(dialogues_config))
    if not dialogues_path.exists():
        parser.error(f"Configured historical dialogue file does not exist: {dialogues_path}")
    llm_client = OpenAICompatibleClient.from_config(config)
    dialogues = load_dialogues(dialogues_path, config.get("dialogue_fields"))
    if args.max_dialogues:
        dialogues = dialogues[: args.max_dialogues]
    if not dialogues:
        parser.error(f"No usable historical dialogues loaded from: {dialogues_path}")
    result = DialogueBehaviorMiner(llm_client, output_dir, logger).mine(dialogues)
    print(f"Mined {len(result['summaries'])} dialogue summaries.")
    print(f"Mined {len(result['personas'])} employee personas.")
    print(f"Mined {len(result['behavior_taxonomy'])} behavior taxonomy items.")
    print(f"Outputs written to: {output_dir}")


def run_analyze_cases(
    args: argparse.Namespace,
    config: Dict[str, Any],
    root: Path,
    output_dir: Path,
    logger: OutputLogger,
    parser: argparse.ArgumentParser,
) -> None:
    cases = load_configured_cases(config, root, parser)
    if args.case_ids:
        selected_cases = [get_case(cases, case_id) for case_id in args.case_ids]
    elif args.random:
        sampler = random.Random(args.seed)
        sample_size = min(args.limit, len(cases))
        selected_cases = sampler.sample(cases, sample_size)
    else:
        selected_cases = cases[args.offset : args.offset + args.limit]
    if not selected_cases:
        parser.error("No cases selected for analysis.")
    llm_client = OpenAICompatibleClient.from_config(config)
    blind_user_views: list[BlindUserCaseView] = []
    knowledge_artifacts: list[KnowledgeRoadmapArtifact] = []
    debug_artifacts: list[CaseAnalysisDebugArtifact] = []
    for index, target_case in enumerate(selected_cases, 1):
        print(f"[{index}/{len(selected_cases)}] Analyzing case {target_case.case_id}: {target_case.title}")
        blind_view, knowledge_artifact, debug_artifact = build_case_analysis_artifacts(
            target_case,
            cases,
            llm_client,
            logger,
            config,
        )
        blind_user_views.append(blind_view)
        knowledge_artifacts.append(knowledge_artifact)
        debug_artifacts.append(debug_artifact)
    blind_view_path = output_dir / "blind_user_case_views.jsonl"
    knowledge_path = output_dir / "knowledge_roadmaps.jsonl"
    debug_path = output_dir / "case_analysis_debug.jsonl"
    total_blind_views = upsert_jsonl_by_key(blind_view_path, [model_to_dict(view) for view in blind_user_views], "case_id")
    total_knowledge_artifacts = upsert_jsonl_by_key(
        knowledge_path,
        [model_to_dict(artifact) for artifact in knowledge_artifacts],
        "case_id",
    )
    total_debug_artifacts = upsert_jsonl_by_key(
        debug_path,
        [model_to_dict(artifact) for artifact in debug_artifacts],
        "case_id",
    )
    print(f"Upserted {len(blind_user_views)} blind-user case views to: {blind_view_path}")
    print(f"Total blind-user case views: {total_blind_views}")
    print(f"Upserted {len(knowledge_artifacts)} compact runtime roadmaps to: {knowledge_path}")
    print(f"Total knowledge roadmaps: {total_knowledge_artifacts}")
    print(f"Upserted {len(debug_artifacts)} debug artifacts to: {debug_path}")
    print(f"Total debug artifacts: {total_debug_artifacts}")


def run_simulate(
    args: argparse.Namespace,
    config: Dict[str, Any],
    root: Path,
    output_dir: Path,
    logger: OutputLogger,
    parser: argparse.ArgumentParser,
) -> None:
    if args.list_cases:
        cases = load_configured_cases(config, root, parser)
        for case in cases[: args.list_cases]:
            print(f"{case.case_id}\t{case.title}")
        return
    if not args.case_id:
        parser.error("--case_id is required unless --list_cases is used")

    llm_client = OpenAICompatibleClient.from_config(config)
    knowledge_artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    knowledge_artifact = knowledge_artifacts.get(args.case_id)
    if knowledge_artifact is None:
        parser.error(
            f"No precomputed knowledge roadmap found for {args.case_id}. "
            "Run: python3 main.py analyze-cases --case_ids "
            f"{args.case_id}"
        )
    employee_personas = load_employee_personas(output_dir / "employee_personas.jsonl")
    behavior_taxonomy = load_behavior_taxonomy(output_dir / "user_behavior_taxonomy.jsonl")
    try:
        employee_persona = select_employee_persona(employee_personas, args.persona_id)
    except ValueError as exc:
        parser.error(str(exc))
    persona = model_to_dict(employee_persona) if employee_persona else PERSONAS[args.persona]

    simulator = Simulator(
        knowledge_artifact.roadmap,
        persona,
        llm_client,
        logger,
        employee_persona=model_to_dict(employee_persona) if employee_persona else None,
        behavior_taxonomy=[model_to_dict(item) for item in behavior_taxonomy],
    )

    user_text = simulator.start()
    print(f"User: {user_text}")
    while not simulator.state.should_stop and simulator.state.turn_count < args.max_turns:
        assistant_text = input("Assistant> ").strip()
        # Real assistant integration point:
        # Replace the manual input above with a call to your enterprise assistant.
        # Recommended shape:
        #   assistant_text = call_real_assistant(
        #       user_text=simulator.dialogue_history[-1]["content"],
        #       dialogue_history=simulator.dialogue_history,
        #       config=config.get("assistant", {}),
        #   )
        #   print(f"Assistant> {assistant_text}")
        if not assistant_text:
            continue
        result = simulator.step(assistant_text)
        print(f"User: {result['user_reply']}")
        if simulator.state.should_stop:
            print(f"[STOP: {simulator.state.stop_reason or simulator.state.solution_status}]")
    if not simulator.state.should_stop:
        print(f"[STOP: max_turns={args.max_turns}]")


def run_export_review(args: argparse.Namespace, output_dir: Path, parser: argparse.ArgumentParser) -> None:
    if not args.case_id and not args.all:
        parser.error("export-review requires --case_id <CASE_ID> or --all")
    knowledge_artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    if not knowledge_artifacts:
        parser.error(f"No knowledge roadmaps found: {output_dir / 'knowledge_roadmaps.jsonl'}")
    blind_views = load_blind_user_case_views(output_dir / "blind_user_case_views.jsonl")
    debug_artifacts = load_case_analysis_debug_artifacts(output_dir / "case_analysis_debug.jsonl")
    employee_personas = load_employee_personas(output_dir / "employee_personas.jsonl")
    behavior_taxonomy = load_behavior_taxonomy(output_dir / "user_behavior_taxonomy.jsonl")
    exporter = ReviewExporter(output_dir, knowledge_artifacts, blind_views, employee_personas, behavior_taxonomy, debug_artifacts)
    if args.all:
        paths = exporter.export_cases()
    else:
        paths = [exporter.export_case(args.case_id)]
        exporter.export_index()
        exporter.export_behavior_review()
    print(f"Exported {len(paths)} case review file(s) to: {output_dir / 'review'}")


def load_configured_cases(config: Dict[str, Any], root: Path, parser: argparse.ArgumentParser) -> list[Case]:
    cases_config = config.get("paths", {}).get("cases")
    if not cases_config:
        parser.error("Missing paths.cases in config.yaml; it must point to the real case library.")
    cases_path = resolve_path(root, str(cases_config))
    if not cases_path.exists():
        parser.error(f"Configured case library does not exist: {cases_path}")
    cases = load_cases(cases_path, config.get("case_fields"))
    if not cases:
        parser.error(f"No usable cases loaded from: {cases_path}")
    return cases


def build_case_analysis_artifacts(
    target_case: Case,
    all_cases: list[Case],
    llm_client: OpenAICompatibleClient,
    logger: OutputLogger,
    config: Dict[str, Any] | None = None,
) -> tuple[BlindUserCaseView, KnowledgeRoadmapArtifact, CaseAnalysisDebugArtifact]:
    queries = QueryGenerator(llm_client, logger).generate_queries(target_case)
    retrieval_config = (config or {}).get("retrieval", {})
    related_cases = RelatedCaseRetriever(
        llm_client,
        logger,
        top_k=int(retrieval_config.get("related_top_k", 5)),
        recall_top_n=int(retrieval_config.get("candidate_top_n", 50)),
    ).retrieve(target_case, queries, all_cases)
    points = PointExtractor(llm_client, logger).extract_points(target_case, related_cases)
    verification = PointVerifier(llm_client, logger).verify_points(target_case, related_cases, points)
    relations = RelationBuilder(llm_client, logger).build_relations(verification.verified_points, target_case.case_id)
    roadmap = RoadmapBuilder(llm_client, logger).build_roadmap(target_case, verification.verified_points, relations)
    runtime_artifact = KnowledgeRoadmapArtifact(
        case_id=target_case.case_id,
        title=target_case.title,
        roadmap=build_runtime_roadmap(roadmap),
    )
    debug_artifact = CaseAnalysisDebugArtifact(
        case_id=target_case.case_id,
        target_case=target_case,
        retrieval_queries=queries,
        related_cases=related_cases,
        verified_points=verification.verified_points,
        dropped_points=verification.dropped_points,
        warnings=verification.warnings,
        relations=relations,
        roadmap=roadmap,
    )
    return build_blind_user_view(roadmap), runtime_artifact, debug_artifact


def build_blind_user_view(roadmap: Roadmap) -> BlindUserCaseView:
    return BlindUserCaseView(
        case_id=roadmap.target_case_id,
        surface_problem=roadmap.surface_problem,
        opening_intent=roadmap.opening_intent,
        user_facing_points=roadmap.user_facing_points,
        forbidden_content=roadmap.forbidden_content,
    )


def build_runtime_roadmap(roadmap: Roadmap) -> RuntimeRoadmap:
    return RuntimeRoadmap(
        target_case_id=roadmap.target_case_id,
        surface_problem=roadmap.surface_problem,
        opening_intent=roadmap.opening_intent,
        user_facing_points=[build_runtime_point(point) for point in roadmap.user_facing_points],
        diagnostic_points=[build_runtime_point(point) for point in roadmap.diagnostic_points],
        solution_points=[build_runtime_point(point) for point in roadmap.solution_points],
        external_points=[build_runtime_point(point) for point in roadmap.external_points],
        relations=[build_runtime_relation(relation) for relation in roadmap.relations],
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


def build_runtime_relation(relation: Relation) -> RuntimeRelation:
    return RuntimeRelation(
        from_point_id=relation.from_point_id,
        to_point_id=relation.to_point_id,
        relation_type=relation.relation_type,
    )


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


def load_blind_user_case_views(path: Path) -> dict[str, BlindUserCaseView]:
    views: dict[str, BlindUserCaseView] = {}
    for record in read_jsonl(path):
        view = BlindUserCaseView(**record)
        views[view.case_id] = view
    return views


def load_case_analysis_debug_artifacts(path: Path) -> dict[str, CaseAnalysisDebugArtifact]:
    artifacts: dict[str, CaseAnalysisDebugArtifact] = {}
    for record in read_jsonl(path):
        artifact = CaseAnalysisDebugArtifact(**record)
        artifacts[artifact.case_id] = artifact
    return artifacts


def upsert_jsonl_by_key(path: Path, new_records: list[Dict[str, Any]], key: str) -> int:
    merged: dict[str, Dict[str, Any]] = {}
    for record in read_jsonl(path):
        record_key = str(record.get(key) or "")
        if record_key:
            merged[record_key] = record
    for record in new_records:
        record_key = str(record.get(key) or "")
        if record_key:
            merged[record_key] = record
    write_jsonl(path, merged.values())
    return len(merged)


def load_employee_personas(path: Path) -> list[EmployeePersona]:
    fallback_path = Path(__file__).resolve().parent / "data" / "manual_seed_employee_personas.jsonl"
    source_path = path if path.exists() else fallback_path
    if not source_path.exists():
        return []
    return [EmployeePersona(**record) for record in read_jsonl(source_path)]


def load_behavior_taxonomy(path: Path) -> list[BehaviorTaxonomy]:
    fallback_path = Path(__file__).resolve().parent / "data" / "manual_seed_user_behavior_taxonomy.jsonl"
    source_path = path if path.exists() else fallback_path
    if not source_path.exists():
        return []
    return [BehaviorTaxonomy(**record) for record in read_jsonl(source_path)]


def select_employee_persona(personas: list[EmployeePersona], persona_id: str | None) -> EmployeePersona | None:
    if not personas:
        return None
    if not persona_id:
        return personas[0]
    for persona in personas:
        if persona.persona_id == persona_id:
            return persona
    raise ValueError(f"persona_id not found in employee_personas.jsonl: {persona_id}")


def load_config(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    except ImportError:
        return parse_minimal_yaml(text)


def resolve_path(root: Path, configured_path: str) -> Path:
    path = Path(configured_path).expanduser()
    if path.is_absolute():
        return path
    return (root / path).resolve()


def parse_minimal_yaml(text: str) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    current: Dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            key = line[:-1]
            current = {}
            config[key] = current
            continue
        if current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip().strip('"')
    return config


if __name__ == "__main__":
    main()
