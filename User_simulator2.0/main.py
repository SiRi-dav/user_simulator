from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Dict

from src.assistant.real_assistant_client import RealAssistantClient
from src.behavior_mining.behavior_miner import DialogueBehaviorMiner
from src.behavior_mining.dialogue_loader import load_dialogues
from src.data_loader import get_case, load_cases
from src.extraction.point_extractor import PointExtractor
from src.extraction.point_verifier import PointVerifier
from src.llm.openai_compatible_client import OpenAICompatibleClient
from src.metrics_exporter import MetricsExporter
from src.retrieval.query_generator import QueryGenerator
from src.retrieval.related_case_retriever import RelatedCaseRetriever
from src.roadmap.relation_builder import RelationBuilder
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.review_exporter import ReviewExporter
from src.runtime.simulator import Simulator
from src.simulator_evaluator import SimulatorEvaluator, collect_real_case_ids
from src.schemas import (
    BehaviorTaxonomy,
    BlindUserCaseView,
    BlindUserRuntimeView,
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
from src.transcript_exporter import TranscriptExporter
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
    if command == "sanitize-blind-views":
        run_sanitize_blind_views(args, output_dir, parser)
        return
    if command == "export-transcripts":
        run_export_transcripts(args, output_dir, parser)
        return
    if command == "simulate-batch":
        run_simulate_batch(args, config, root, output_dir, logger, parser)
        return
    if command == "export-metrics":
        run_export_metrics(args, config, output_dir, parser)
        return
    if command == "evaluate-simulator":
        run_evaluate_simulator(args, config, root, output_dir, parser)
        return
    if command == "select-real-cases":
        run_select_real_cases(args, config, root, output_dir, parser)
        return
    run_simulate(args, config, root, output_dir, logger, parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM-based Knowledge-grounded User Simulator MVP")
    parser.add_argument("--config", default="config.yaml")
    subparsers = parser.add_subparsers(dest="command")

    simulate = subparsers.add_parser("simulate", help="Run target-case user simulation.")
    simulate.add_argument("--config", default="config.yaml")
    add_simulate_args(simulate)

    batch = subparsers.add_parser("simulate-batch", help="Run multiple target-case simulations with resume protection.")
    batch.add_argument("--config", default="config.yaml")
    batch.add_argument("--case_ids", nargs="*")
    batch.add_argument("--case_ids_file", help="Plain text file with one case_id per line.")
    batch.add_argument("--all", action="store_true", help="Simulate all cases in knowledge_roadmaps.jsonl.")
    batch.add_argument("--limit", type=int, default=0, help="Limit selected cases after --all or --offset.")
    batch.add_argument("--offset", type=int, default=0)
    batch.add_argument("--persona", default="low_tech", choices=sorted(PERSONAS))
    batch.add_argument("--persona_id")
    batch.add_argument("--max_turns", type=int, default=6)
    batch.add_argument("--assistant_mode", choices=("api",), default="api", help="Batch mode currently calls the real assistant API.")
    batch.add_argument("--rerun_completed", action="store_true", help="Do not skip cases already marked completed.")

    analyze = subparsers.add_parser("analyze-cases", help="Precompute roadmaps and knowledge artifacts for target cases.")
    analyze.add_argument("--config", default="config.yaml")
    analyze.add_argument("--limit", type=int, default=20)
    analyze.add_argument("--offset", type=int, default=0)
    analyze.add_argument("--case_ids", nargs="*")
    analyze.add_argument("--case_ids_file", help="Plain text file with one case_id per line.")
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

    sanitize = subparsers.add_parser(
        "sanitize-blind-views",
        help="Convert blind_user_case_views.jsonl into minimal blind_user_runtime_views.jsonl without point objects.",
    )
    sanitize.add_argument("--config", default="config.yaml")
    sanitize.add_argument("--case_id")
    sanitize.add_argument("--input", default="blind_user_case_views.jsonl")
    sanitize.add_argument("--output", default="blind_user_runtime_views.jsonl")

    transcripts = subparsers.add_parser("export-transcripts", help="Export simulation logs into readable dialogue transcripts.")
    transcripts.add_argument("--config", default="config.yaml")
    transcripts.add_argument("--case_id")
    transcripts.add_argument("--all", action="store_true", help="Export all cases in simulation_logs.jsonl.")

    metrics = subparsers.add_parser("export-metrics", help="Export user-simulator quality metrics from transcripts/logs.")
    metrics.add_argument("--config", default="config.yaml")
    metrics.add_argument("--case_id")
    metrics.add_argument("--all", action="store_true", help="Evaluate all cases in simulation_logs.jsonl.")
    metrics.add_argument("--judge", action="store_true", help="Also run LLM judge for semantic quality scores.")

    simulator_eval = subparsers.add_parser("evaluate-simulator", help="Compare simulated user sessions against real dialogues.")
    simulator_eval.add_argument("--config", default="config.yaml")
    simulator_eval.add_argument("--case_ids", nargs="*")
    simulator_eval.add_argument("--case_ids_file", help="Plain text file with one case_id per line.")
    simulator_eval.add_argument("--case_id")
    simulator_eval.add_argument("--dialogues", help="Historical dialogue JSON/JSONL path. Defaults to config paths.dialogues.")
    simulator_eval.add_argument("--judge", action="store_true", help="Use LLM judge for semantic realism, goal alignment, and over-cooperation.")

    select_real = subparsers.add_parser("select-real-cases", help="Select case ids that have real historical dialogues.")
    select_real.add_argument("--config", default="config.yaml")
    select_real.add_argument("--dialogues", help="Historical dialogue JSON/JSONL path. Defaults to config paths.dialogues.")
    select_real.add_argument("--limit", type=int, default=20)
    select_real.add_argument("--offset", type=int, default=0)
    select_real.add_argument("--output", default="outputs/real_dialogue_case_ids.txt")

    # Backward-compatible direct invocation: python main.py --case_id ...
    if len(sys.argv) > 1 and sys.argv[1] not in {"simulate", "simulate-batch", "mine-behavior", "analyze-cases", "export-review", "sanitize-blind-views", "export-transcripts", "export-metrics", "evaluate-simulator", "select-real-cases", "-h", "--help"}:
        add_simulate_args(parser)
    return parser


def add_simulate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case_id")
    parser.add_argument("--persona", default="low_tech", choices=sorted(PERSONAS))
    parser.add_argument("--persona_id")
    parser.add_argument("--max_turns", type=int, default=6)
    parser.add_argument(
        "--assistant_mode",
        choices=("manual", "api"),
        help="manual reads Assistant> from terminal; api calls the configured real assistant.",
    )
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
    explicit_case_ids = collect_requested_case_ids(args)
    if explicit_case_ids:
        selected_cases = [get_case(cases, case_id) for case_id in explicit_case_ids]
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
    blind_user_runtime_views: list[BlindUserRuntimeView] = []
    knowledge_artifacts: list[KnowledgeRoadmapArtifact] = []
    debug_artifacts: list[CaseAnalysisDebugArtifact] = []
    failed_cases = 0
    for index, target_case in enumerate(selected_cases, 1):
        print(f"[{index}/{len(selected_cases)}] Analyzing case {target_case.case_id}: {target_case.title}")
        try:
            blind_view, knowledge_artifact, debug_artifact = build_case_analysis_artifacts(
                target_case,
                cases,
                llm_client,
                logger,
                config,
            )
        except Exception as exc:
            failed_cases += 1
            print(f"[ERROR] Skipped case {target_case.case_id}: {exc}")
            logger.log(
                "case_analysis_errors.jsonl",
                target_case.case_id,
                "analyze-cases",
                {"target_case": target_case},
                {"error_type": type(exc).__name__, "error": str(exc)},
            )
            continue
        blind_user_views.append(blind_view)
        blind_user_runtime_views.append(build_blind_user_runtime_view(blind_view))
        knowledge_artifacts.append(knowledge_artifact)
        debug_artifacts.append(debug_artifact)
    if not knowledge_artifacts:
        parser.error(f"All selected cases failed. See: {output_dir / 'case_analysis_errors.jsonl'}")
    blind_view_path = output_dir / "blind_user_case_views.jsonl"
    blind_runtime_path = output_dir / "blind_user_runtime_views.jsonl"
    knowledge_path = output_dir / "knowledge_roadmaps.jsonl"
    debug_path = output_dir / "case_analysis_debug.jsonl"
    total_blind_views = upsert_jsonl_by_key(blind_view_path, [model_to_dict(view) for view in blind_user_views], "case_id")
    total_blind_runtime_views = upsert_jsonl_by_key(
        blind_runtime_path,
        [model_to_dict(view) for view in blind_user_runtime_views],
        "case_id",
    )
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
    print(f"Upserted {len(blind_user_runtime_views)} minimal blind-user runtime views to: {blind_runtime_path}")
    print(f"Total minimal blind-user runtime views: {total_blind_runtime_views}")
    print(f"Upserted {len(knowledge_artifacts)} compact runtime roadmaps to: {knowledge_path}")
    print(f"Total knowledge roadmaps: {total_knowledge_artifacts}")
    print(f"Upserted {len(debug_artifacts)} debug artifacts to: {debug_path}")
    print(f"Total debug artifacts: {total_debug_artifacts}")
    if failed_cases:
        print(f"Skipped {failed_cases} failed case(s). Errors written to: {output_dir / 'case_analysis_errors.jsonl'}")


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
    blind_views = load_blind_user_runtime_views(output_dir / "blind_user_runtime_views.jsonl")
    blind_view = blind_views.get(args.case_id)
    if blind_view is None:
        parser.error(
            f"No minimal blind-user runtime view found for {args.case_id}. "
            "Run: python3 main.py sanitize-blind-views, or rerun: "
            f"python3 main.py analyze-cases --case_ids {args.case_id}"
        )
    knowledge_artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    knowledge_artifact = knowledge_artifacts.get(args.case_id)
    if knowledge_artifact is None:
        parser.error(
            f"No precomputed knowledge roadmap found for {args.case_id}. "
            "Run: python3 main.py analyze-cases --case_ids "
            f"{args.case_id}"
        )
    simulator = build_simulator_for_case(args, blind_view, knowledge_artifact, output_dir, llm_client, logger, parser)
    print(f"User: {simulator.start()}")
    assistant_mode = args.assistant_mode or str(config.get("assistant", {}).get("mode") or "manual")
    assistant_client = build_assistant_client(config) if assistant_mode == "api" else None
    run_simulation_loop(simulator, int(args.max_turns), assistant_client)


def build_assistant_client(config: Dict[str, Any]) -> RealAssistantClient:
    return RealAssistantClient(config.get("assistant", {}))


def build_simulator_for_case(
    args: argparse.Namespace,
    blind_view: BlindUserRuntimeView,
    knowledge_artifact: KnowledgeRoadmapArtifact,
    output_dir: Path,
    llm_client: OpenAICompatibleClient,
    logger: OutputLogger,
    parser: argparse.ArgumentParser,
) -> Simulator:
    employee_personas = load_employee_personas(output_dir / "employee_personas.jsonl")
    behavior_taxonomy = load_behavior_taxonomy(output_dir / "user_behavior_taxonomy.jsonl")
    try:
        employee_persona = select_employee_persona(employee_personas, args.persona_id)
    except ValueError as exc:
        parser.error(str(exc))
    persona = model_to_dict(employee_persona) if employee_persona else PERSONAS[args.persona]
    return Simulator(
        blind_view,
        knowledge_artifact.roadmap,
        persona,
        llm_client,
        logger,
        employee_persona=model_to_dict(employee_persona) if employee_persona else None,
        behavior_taxonomy=[model_to_dict(item) for item in behavior_taxonomy],
    )


def run_simulation_loop(
    simulator: Simulator,
    max_turns: int,
    assistant_client: RealAssistantClient | None = None,
) -> None:
    while not simulator.state.should_stop and simulator.state.turn_count < max_turns:
        if assistant_client:
            assistant_text = assistant_client.reply(simulator.dialogue_history)
            print(f"Assistant> {assistant_text}")
        else:
            assistant_text = input("Assistant> ").strip()
        if not assistant_text:
            continue
        result = simulator.step(assistant_text)
        print(f"User: {result['user_reply']}")
        if simulator.state.should_stop:
            print(f"[STOP: {simulator.state.stop_reason or simulator.state.solution_status}]")
    if not simulator.state.should_stop:
        print(f"[STOP: max_turns={max_turns}]")


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


def run_sanitize_blind_views(args: argparse.Namespace, output_dir: Path, parser: argparse.ArgumentParser) -> None:
    input_path = output_dir / args.input
    output_path = output_dir / args.output
    views = load_blind_user_case_views(input_path)
    if not views:
        parser.error(f"No blind-user case views found: {input_path}")
    if args.case_id and args.case_id not in views:
        parser.error(f"No blind-user case view found for {args.case_id}: {input_path}")
    selected_views = [views[args.case_id]] if args.case_id else list(views.values())
    runtime_views = [build_blind_user_runtime_view(view) for view in selected_views]
    total = upsert_jsonl_by_key(output_path, [model_to_dict(view) for view in runtime_views], "case_id")
    print(f"Upserted {len(runtime_views)} minimal blind-user runtime view(s) to: {output_path}")
    print(f"Total minimal blind-user runtime views: {total}")


def run_export_transcripts(args: argparse.Namespace, output_dir: Path, parser: argparse.ArgumentParser) -> None:
    if not args.case_id and not args.all:
        parser.error("export-transcripts requires --case_id <CASE_ID> or --all")
    exporter = TranscriptExporter(output_dir)
    if args.all:
        paths = exporter.export_cases()
    else:
        paths = exporter.export_case(args.case_id)
    print(f"Exported {len(paths)} transcript file(s) to: {output_dir / 'transcripts'}")


def run_simulate_batch(
    args: argparse.Namespace,
    config: Dict[str, Any],
    root: Path,
    output_dir: Path,
    logger: OutputLogger,
    parser: argparse.ArgumentParser,
) -> None:
    knowledge_artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    if not knowledge_artifacts:
        parser.error(f"No knowledge roadmaps found: {output_dir / 'knowledge_roadmaps.jsonl'}")
    blind_views = load_blind_user_runtime_views(output_dir / "blind_user_runtime_views.jsonl")
    if not blind_views:
        parser.error(
            f"No minimal blind-user runtime views found: {output_dir / 'blind_user_runtime_views.jsonl'}. "
            "Run: python3 main.py sanitize-blind-views"
        )
    case_ids = select_batch_case_ids(args, knowledge_artifacts, parser)
    if not case_ids:
        parser.error("No cases selected for simulation.")
    status_path = output_dir / "simulate_batch_status.jsonl"
    completed = load_completed_batch_case_ids(status_path)
    llm_client = OpenAICompatibleClient.from_config(config)
    assistant_client = build_assistant_client(config)
    exporter = TranscriptExporter(output_dir)
    total = len(case_ids)
    completed_now = 0
    skipped = 0
    failed = 0
    for index, case_id in enumerate(case_ids, 1):
        if case_id in completed and not args.rerun_completed:
            skipped += 1
            print(f"[{index}/{total}] Skipping completed case {case_id}")
            continue
        artifact = knowledge_artifacts.get(case_id)
        blind_view = blind_views.get(case_id)
        if artifact is None:
            failed += 1
            update_batch_status(status_path, case_id, "failed", {"error": "missing knowledge roadmap"})
            print(f"[{index}/{total}] Missing knowledge roadmap for {case_id}")
            continue
        if blind_view is None:
            failed += 1
            update_batch_status(status_path, case_id, "failed", {"error": "missing blind-user case view"})
            print(f"[{index}/{total}] Missing blind-user case view for {case_id}")
            continue
        print(f"[{index}/{total}] Simulating case {case_id}: {artifact.title}")
        update_batch_status(status_path, case_id, "running", {"title": artifact.title, "max_turns": args.max_turns})
        try:
            simulator = build_simulator_for_case(args, blind_view, artifact, output_dir, llm_client, logger, parser)
            print(f"User: {simulator.start()}")
            run_simulation_loop(simulator, int(args.max_turns), assistant_client)
            status = {
                "title": artifact.title,
                "turn_count": simulator.state.turn_count,
                "solution_status": simulator.state.solution_status,
                "stop_reason": simulator.state.stop_reason or "",
            }
            update_batch_status(status_path, case_id, "completed", status)
            try:
                exporter.export_case(case_id)
            except Exception as exc:
                update_batch_status(status_path, case_id, "completed", {**status, "transcript_error": str(exc)})
            completed_now += 1
        except Exception as exc:
            failed += 1
            update_batch_status(status_path, case_id, "failed", {"title": artifact.title, "error_type": type(exc).__name__, "error": str(exc)})
            print(f"[ERROR] Failed case {case_id}: {exc}")
            continue
    print(
        "Batch simulation done: "
        f"completed={completed_now}, skipped={skipped}, failed={failed}, status={status_path}"
    )


def run_export_metrics(args: argparse.Namespace, config: Dict[str, Any], output_dir: Path, parser: argparse.ArgumentParser) -> None:
    if not args.case_id and not args.all:
        parser.error("export-metrics requires --case_id <CASE_ID> or --all")
    knowledge_artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    llm_client = OpenAICompatibleClient.from_config(config) if args.judge else None
    exporter = MetricsExporter(output_dir, knowledge_artifacts, llm_client=llm_client)
    if args.all:
        paths = exporter.export_cases(use_judge=args.judge)
    else:
        paths = exporter.export_case(args.case_id, use_judge=args.judge)
    print(f"Exported {len(paths)} metrics file(s) to: {output_dir / 'metrics'}")


def run_evaluate_simulator(
    args: argparse.Namespace,
    config: Dict[str, Any],
    root: Path,
    output_dir: Path,
    parser: argparse.ArgumentParser,
) -> None:
    case_ids = collect_requested_case_ids(args)
    if args.case_id:
        case_ids.append(args.case_id)
    case_ids = [case_id for case_id in case_ids if case_id]
    if not case_ids:
        parser.error("evaluate-simulator requires --case_id <CASE_ID> or --case_ids <CASE_ID...>")
    dialogues_config = args.dialogues or config.get("paths", {}).get("dialogues")
    if not dialogues_config:
        parser.error("Missing dialogue path. Use --dialogues or set paths.dialogues in config.yaml.")
    dialogues_path = resolve_path(root, str(dialogues_config))
    if not dialogues_path.exists():
        parser.error(f"Configured historical dialogue file does not exist: {dialogues_path}")
    knowledge_artifacts = load_knowledge_roadmaps(output_dir / "knowledge_roadmaps.jsonl")
    llm_client = OpenAICompatibleClient.from_config(config) if args.judge else None
    evaluator = SimulatorEvaluator(output_dir, knowledge_artifacts, llm_client=llm_client)
    paths = evaluator.evaluate(case_ids, dialogues_path, config.get("dialogue_fields"), use_judge=args.judge)
    print(f"Exported simulator evaluation to: {output_dir / 'simulator_eval'}")
    for path in paths:
        print(path)


def run_select_real_cases(
    args: argparse.Namespace,
    config: Dict[str, Any],
    root: Path,
    output_dir: Path,
    parser: argparse.ArgumentParser,
) -> None:
    dialogues_path = resolve_dialogues_path(args, config, root, parser)
    cases = load_configured_cases(config, root, parser)
    valid_case_ids = {case.case_id for case in cases}
    dialogues = load_dialogues(dialogues_path, config.get("dialogue_fields"))
    selected = [case_id for case_id in collect_real_case_ids(dialogues) if case_id in valid_case_ids]
    if args.offset:
        selected = selected[args.offset :]
    if args.limit:
        selected = selected[: args.limit]
    if not selected:
        parser.error("No case ids with real dialogues were found in both dialogue file and case library.")
    output_path = resolve_path(root, str(args.output))
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(selected) + "\n", encoding="utf-8")
    print(f"Selected {len(selected)} case id(s) with real dialogues:")
    for case_id in selected:
        print(case_id)
    print(f"Wrote case id list to: {output_path}")


def select_batch_case_ids(
    args: argparse.Namespace,
    knowledge_artifacts: dict[str, KnowledgeRoadmapArtifact],
    parser: argparse.ArgumentParser,
) -> list[str]:
    requested_case_ids = collect_requested_case_ids(args)
    if requested_case_ids:
        case_ids = requested_case_ids
    elif args.all:
        case_ids = sorted(knowledge_artifacts)
    else:
        parser.error("simulate-batch requires --case_ids <CASE_ID...> or --all")
    if args.offset:
        case_ids = case_ids[args.offset :]
    if args.limit:
        case_ids = case_ids[: args.limit]
    return case_ids


def collect_requested_case_ids(args: argparse.Namespace) -> list[str]:
    case_ids: list[str] = []
    case_ids.extend(str(case_id).strip() for case_id in (getattr(args, "case_ids", None) or []))
    case_ids_file = getattr(args, "case_ids_file", None)
    if case_ids_file:
        case_ids.extend(read_case_ids_file(Path(case_ids_file)))
    return [case_id for case_id in case_ids if case_id]


def read_case_ids_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    case_ids = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        case_ids.append(text.split()[0])
    return case_ids


def resolve_dialogues_path(
    args: argparse.Namespace,
    config: Dict[str, Any],
    root: Path,
    parser: argparse.ArgumentParser,
) -> Path:
    dialogues_config = getattr(args, "dialogues", None) or config.get("paths", {}).get("dialogues")
    if not dialogues_config:
        parser.error("Missing dialogue path. Use --dialogues or set paths.dialogues in config.yaml.")
    dialogues_path = resolve_path(root, str(dialogues_config))
    if not dialogues_path.exists():
        parser.error(f"Configured historical dialogue file does not exist: {dialogues_path}")
    return dialogues_path


def load_completed_batch_case_ids(path: Path) -> set[str]:
    return {str(record.get("case_id")) for record in read_jsonl(path) if record.get("status") == "completed"}


def update_batch_status(path: Path, case_id: str, status: str, payload: Dict[str, Any]) -> None:
    record = {"case_id": str(case_id), "status": status, **payload}
    upsert_jsonl_by_key(path, [record], "case_id")


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
        per_route_top_n=int(retrieval_config.get("per_route_top_n", 12)),
        rerank_top_n=int(retrieval_config.get("rerank_top_n", 20)),
        minimum_score=float(retrieval_config.get("minimum_score", 0.35)),
        fallback_min_cases=int(retrieval_config.get("fallback_min_cases", 2)),
        bm25_weight=float(retrieval_config.get("bm25_weight", 0.6)),
        semantic_weight=float(retrieval_config.get("semantic_weight", 0.4)),
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
    )


def build_blind_user_runtime_view(view: BlindUserCaseView) -> BlindUserRuntimeView:
    return BlindUserRuntimeView(
        case_id=view.case_id,
        surface_problem=view.surface_problem,
        opening_intent=view.opening_intent,
        user_visible_facts=[point.content for point in view.user_facing_points if point.content],
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


def load_blind_user_runtime_views(path: Path) -> dict[str, BlindUserRuntimeView]:
    views: dict[str, BlindUserRuntimeView] = {}
    for record in read_jsonl(path):
        view = BlindUserRuntimeView(**record)
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
    if not fallback_path.exists() and not path.exists():
        return []
    if not fallback_path.exists():
        return [BehaviorTaxonomy(**record) for record in read_jsonl(path)]

    seed_records = read_jsonl(fallback_path)
    if not path.exists():
        return [BehaviorTaxonomy(**record) for record in seed_records]

    mined_by_name = {record["behavior_name"]: record for record in read_jsonl(path)}
    legacy_resolution = mined_by_name.get("确认解决或继续求助")
    if legacy_resolution and "确认解决、继续求助或升级" not in mined_by_name:
        mined_by_name["确认解决、继续求助或升级"] = legacy_resolution

    merged_records = []
    for seed in seed_records:
        mined = mined_by_name.get(seed["behavior_name"], {})
        merged = dict(seed)
        if mined.get("typical_user_response_patterns"):
            merged["typical_user_response_patterns"] = list(
                dict.fromkeys(seed["typical_user_response_patterns"] + mined["typical_user_response_patterns"])
            )
        if mined.get("persona_sensitivity"):
            merged["persona_sensitivity"] = {**seed["persona_sensitivity"], **mined["persona_sensitivity"]}
        merged_records.append(merged)
    return [BehaviorTaxonomy(**record) for record in merged_records]


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
