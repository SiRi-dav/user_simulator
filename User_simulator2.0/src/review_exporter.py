from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.schemas import BehaviorTaxonomy, BlindUserCaseView, CaseAnalysisDebugArtifact, EmployeePersona, KnowledgeRoadmapArtifact, Point, RuntimePoint


class ReviewExporter:
    def __init__(
        self,
        output_dir: Path,
        knowledge_artifacts: dict[str, KnowledgeRoadmapArtifact],
        blind_views: dict[str, BlindUserCaseView],
        employee_personas: list[EmployeePersona],
        behavior_taxonomy: list[BehaviorTaxonomy],
        debug_artifacts: dict[str, CaseAnalysisDebugArtifact] | None = None,
    ):
        self.output_dir = output_dir
        self.review_dir = output_dir / "review"
        self.knowledge_artifacts = knowledge_artifacts
        self.blind_views = blind_views
        self.employee_personas = employee_personas
        self.behavior_taxonomy = behavior_taxonomy
        self.debug_artifacts = debug_artifacts or {}

    def export_case(self, case_id: str) -> Path:
        artifact = self.knowledge_artifacts.get(case_id)
        if artifact is None:
            raise ValueError(f"case_id not found in knowledge_roadmaps.jsonl: {case_id}")
        blind_view = self.blind_views.get(case_id)
        debug_artifact = self.debug_artifacts.get(case_id)
        path = self.review_dir / f"{safe_filename(case_id)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_case_review(artifact, blind_view, debug_artifact), encoding="utf-8")
        return path

    def export_cases(self, case_ids: Iterable[str] | None = None) -> list[Path]:
        selected_ids = list(case_ids) if case_ids else sorted(self.knowledge_artifacts)
        paths = [self.export_case(case_id) for case_id in selected_ids]
        self.export_index()
        self.export_behavior_review()
        return paths

    def export_index(self) -> Path:
        path = self.review_dir / "index.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# User Simulator Review Index",
            "",
            "| case_id | title | surface_problem | user_facing | diagnostic | solution | external | warnings |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
        for case_id in sorted(self.knowledge_artifacts):
            artifact = self.knowledge_artifacts[case_id]
            debug_artifact = self.debug_artifacts.get(case_id)
            roadmap = artifact.roadmap
            lines.append(
                "| {case_id} | {title} | {surface_problem} | {user_facing} | {diagnostic} | {solution} | {external} | {warnings} |".format(
                    case_id=escape_md(case_id),
                    title=escape_md(debug_artifact.target_case.title if debug_artifact else artifact.title),
                    surface_problem=escape_md(roadmap.surface_problem),
                    user_facing=len(roadmap.user_facing_points),
                    diagnostic=len(roadmap.diagnostic_points),
                    solution=len(roadmap.solution_points),
                    external=len(roadmap.external_points),
                    warnings=len(debug_artifact.warnings) if debug_artifact else 0,
                )
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def export_behavior_review(self) -> Path:
        path = self.review_dir / "behavior_assets.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Behavior Assets", ""]
        lines.extend(render_personas(self.employee_personas))
        lines.extend(render_behavior_taxonomy(self.behavior_taxonomy))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


def render_case_review(
    artifact: KnowledgeRoadmapArtifact,
    blind_view: BlindUserCaseView | None,
    debug_artifact: CaseAnalysisDebugArtifact | None = None,
) -> str:
    roadmap = artifact.roadmap
    lines = [
        f"# {artifact.case_id} {debug_artifact.target_case.title if debug_artifact else artifact.title}",
        "",
        "## Target Case",
        "",
        f"- case_id: `{artifact.case_id}`",
        f"- title: {debug_artifact.target_case.title if debug_artifact else artifact.title}",
        "",
        "## Blind User View",
        "",
    ]
    if debug_artifact:
        lines.extend(["### Case Text", "", truncate_block(debug_artifact.target_case.phenomenon), ""])
    if blind_view:
        lines.extend(
            [
                f"- surface_problem: {blind_view.surface_problem}",
                f"- opening_intent: {blind_view.opening_intent}",
                "",
                "### User-Facing Points",
                "",
                render_points(blind_view.user_facing_points),
                "",
                "### Forbidden Content",
                "",
                render_list(blind_view.forbidden_content),
            ]
        )
    else:
        lines.append("_No blind_user_case_views entry found for this case._")
    lines.extend(
        [
            "",
            "## Knowledge Roadmap",
            "",
            f"- surface_problem: {roadmap.surface_problem}",
            f"- opening_intent: {roadmap.opening_intent}",
            "",
            "### Diagnostic Points",
            "",
            render_runtime_points(roadmap.diagnostic_points),
            "",
            "### Solution Points",
            "",
            render_runtime_points(roadmap.solution_points),
            "",
            "### External / Confusing Points",
            "",
            render_runtime_points(roadmap.external_points),
            "",
            "### Target Route",
            "",
            render_list(roadmap.target_route),
            "",
            "### External Routes",
            "",
            render_routes(roadmap.external_routes),
            "",
            "## Debug / Review Details",
            "",
            render_debug_details(debug_artifact),
        ]
    )
    return "\n".join(lines) + "\n"


def render_points(points: list[Point]) -> str:
    if not points:
        return "_None._"
    lines = []
    for point in points:
        lines.extend(
            [
                f"- `{point.point_id}` [{point.point_type} / {point.visibility} / risk={point.leakage_risk}] {point.content}",
                f"  - source: `{point.source_case_id}` {point.source_field}",
                f"  - quote: {single_line(point.source_quote)}",
                f"  - trigger: {', '.join(point.trigger) if point.trigger else 'N/A'}",
                f"  - reason: {point.reason}",
            ]
        )
    return "\n".join(lines)


def render_runtime_points(points: list[RuntimePoint]) -> str:
    if not points:
        return "_None._"
    lines = []
    for point in points:
        trigger = ", ".join(point.trigger) if point.trigger else "N/A"
        lines.append(f"- `{point.point_id}` [{point.point_type} / {point.visibility}] {point.content} trigger={trigger}")
    return "\n".join(lines)


def render_debug_details(debug_artifact: CaseAnalysisDebugArtifact | None) -> str:
    if debug_artifact is None:
        return "_No case_analysis_debug.jsonl entry found. Runtime roadmap is available above._"
    lines = [
        "### Full Verified Points",
        "",
        render_points(debug_artifact.verified_points),
        "",
        "### Related Cases",
        "",
        render_related_cases(debug_artifact),
        "",
        "### Retrieval Queries",
        "",
        render_queries(debug_artifact),
        "",
        "### Warnings",
        "",
        render_list(debug_artifact.warnings),
    ]
    return "\n".join(lines)


def render_related_cases(artifact: CaseAnalysisDebugArtifact) -> str:
    if not artifact.related_cases:
        return "_None._"
    lines = ["| case_id | title | text preview |", "|---|---|---|"]
    for case in artifact.related_cases:
        lines.append(f"| {escape_md(case.case_id)} | {escape_md(case.title)} | {escape_md(single_line(case.phenomenon, 120))} |")
    return "\n".join(lines)


def render_queries(artifact: CaseAnalysisDebugArtifact) -> str:
    if not artifact.retrieval_queries:
        return "_None._"
    lines = ["| type | query | reason |", "|---|---|---|"]
    for query in artifact.retrieval_queries:
        lines.append(f"| {escape_md(query.query_type)} | {escape_md(query.query)} | {escape_md(query.reason)} |")
    return "\n".join(lines)


def render_personas(personas: list[EmployeePersona]) -> list[str]:
    lines = ["## Employee Personas", ""]
    if not personas:
        return lines + ["_None._", ""]
    for persona in personas:
        lines.extend(
            [
                f"### {persona.persona_id} {persona.persona_name}",
                "",
                f"- technical_literacy: {persona.technical_literacy}",
                f"- patience_level: {persona.patience_level}",
                f"- clarity_level: {persona.clarity_level}",
                f"- cooperation_level: {persona.cooperation_level}",
                f"- description: {persona.description}",
                f"- information_release_style: {persona.information_release_style}",
                f"- action_request_behavior: {persona.action_request_behavior}",
                f"- offtrack_reaction_style: {persona.offtrack_reaction_style}",
                f"- solution_acceptance_style: {persona.solution_acceptance_style}",
                "",
            ]
        )
    return lines


def render_behavior_taxonomy(taxonomy: list[BehaviorTaxonomy]) -> list[str]:
    lines = ["## Behavior Taxonomy", ""]
    if not taxonomy:
        return lines + ["_None._", ""]
    for item in taxonomy:
        lines.extend(
            [
                f"### {item.behavior_name}",
                "",
                f"- definition: {item.definition}",
                f"- triggers: {', '.join(item.trigger_assistant_acts)}",
                f"- patterns: {', '.join(item.typical_user_response_patterns)}",
                f"- persona_sensitivity: {item.persona_sensitivity}",
                f"- simulator_policy_hint: {item.simulator_policy_hint}",
                "",
            ]
        )
    return lines


def render_routes(routes: list[list[str]]) -> str:
    if not routes:
        return "_None._"
    return "\n".join(f"- {' -> '.join(route)}" for route in routes)


def render_list(items: list[str]) -> str:
    if not items:
        return "_None._"
    return "\n".join(f"- {item}" for item in items)


def truncate_block(text: str, limit: int = 1200) -> str:
    value = text or ""
    if len(value) > limit:
        value = value[:limit] + "\n..."
    return f"```text\n{value}\n```"


def single_line(text: str, limit: int = 180) -> str:
    value = " ".join((text or "").split())
    if len(value) > limit:
        return value[:limit] + "..."
    return value


def escape_md(value: str) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)
