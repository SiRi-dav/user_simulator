from main import build_blind_user_view
from src.extraction.point_extractor import PointExtractor
from src.extraction.point_verifier import PointVerifier
from src.llm.mock_llm_client import MockLLMClient
from src.review_exporter import ReviewExporter
from src.roadmap.relation_builder import RelationBuilder
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.schemas import Case, KnowledgeRoadmapArtifact


def test_review_exporter_writes_case_markdown_and_index(tmp_path):
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    related = [Case(case_id="CASE_002", title="Outlook 登录失败", phenomenon="密码失败", solution="重置密码")]
    points = PointExtractor(llm).extract_points(target, related)
    verification = PointVerifier(llm).verify_points(target, related, points)
    relations = RelationBuilder(llm).build_relations(verification.verified_points, target.case_id)
    roadmap = RoadmapBuilder(llm).build_roadmap(target, verification.verified_points, relations)
    artifact = KnowledgeRoadmapArtifact(
        case_id=target.case_id,
        target_case=target,
        retrieval_queries=[],
        related_cases=related,
        verified_points=verification.verified_points,
        dropped_points=verification.dropped_points,
        warnings=["check this case"],
        relations=relations,
        roadmap=roadmap,
    )
    blind_view = build_blind_user_view(roadmap)
    exporter = ReviewExporter(
        tmp_path,
        {target.case_id: artifact},
        {target.case_id: blind_view},
        [],
        [],
    )

    paths = exporter.export_cases()

    case_md = paths[0].read_text(encoding="utf-8")
    index_md = (tmp_path / "review" / "index.md").read_text(encoding="utf-8")
    assert "## Blind User View" in case_md
    assert "## Knowledge Roadmap" in case_md
    assert "### Solution Points" in case_md
    assert "## Related Cases" in case_md
    assert "CASE_001" in index_md
