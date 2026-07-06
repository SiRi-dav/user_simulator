from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

from src.data_loader import get_case, load_cases
from src.extraction.point_extractor import PointExtractor
from src.extraction.point_verifier import PointVerifier
from src.llm.openai_compatible_client import OpenAICompatibleClient
from src.retrieval.query_generator import QueryGenerator
from src.retrieval.related_case_retriever import RelatedCaseRetriever
from src.roadmap.relation_builder import RelationBuilder
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.runtime.simulator import Simulator
from src.utils.logging import OutputLogger


PERSONAS: Dict[str, Dict[str, Any]] = {
    "low_tech": {"name": "low_tech", "style": "不熟悉技术术语，需要更具体的操作说明", "patience": "medium"},
    "cooperative": {"name": "cooperative", "style": "配合、简洁、愿意补充信息", "patience": "high"},
    "impatient": {"name": "impatient", "style": "略急躁，希望尽快解决", "patience": "low"},
    "vague": {"name": "vague", "style": "描述模糊，除非被问到才补充细节", "patience": "medium"},
}


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-based Knowledge-grounded User Simulator MVP")
    parser.add_argument("--case_id")
    parser.add_argument("--persona", default="low_tech", choices=sorted(PERSONAS))
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--max_turns", type=int, default=6)
    parser.add_argument("--list_cases", type=int, default=0, help="List the first N cases from the configured case library and exit.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    config = load_config(root / args.config)
    cases_config = config.get("paths", {}).get("cases")
    if not cases_config:
        parser.error("Missing paths.cases in config.yaml; it must point to the real case library.")
    cases_path = resolve_path(root, str(cases_config))
    if not cases_path.exists():
        parser.error(f"Configured case library does not exist: {cases_path}")
    output_dir = root / str(config.get("paths", {}).get("output_dir", "outputs"))
    cases = load_cases(cases_path, config.get("case_fields"))
    if args.list_cases:
        for case in cases[: args.list_cases]:
            print(f"{case.case_id}\t{case.title}")
        return
    if not args.case_id:
        parser.error("--case_id is required unless --list_cases is used")

    logger = OutputLogger(output_dir)
    llm_client = OpenAICompatibleClient.from_config(config)
    target_case = get_case(cases, args.case_id)
    persona = PERSONAS[args.persona]

    queries = QueryGenerator(llm_client, logger).generate_queries(target_case)
    related_cases = RelatedCaseRetriever(llm_client, logger).retrieve(target_case, queries, cases)
    points = PointExtractor(llm_client, logger).extract_points(target_case, related_cases)
    verification = PointVerifier(llm_client, logger).verify_points(target_case, related_cases, points)
    relations = RelationBuilder(llm_client, logger).build_relations(verification.verified_points, target_case.case_id)
    roadmap = RoadmapBuilder(llm_client, logger).build_roadmap(target_case, verification.verified_points, relations)
    simulator = Simulator(roadmap, persona, llm_client, logger)

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
