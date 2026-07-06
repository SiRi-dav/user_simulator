from src.extraction.point_extractor import PointExtractor
from src.llm.mock_llm_client import MockLLMClient
from src.roadmap.relation_builder import RelationBuilder
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.schemas import Case


def test_roadmap_builder_generates_surface_problem_and_target_route():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    points = PointExtractor(llm).extract_points(target, [])
    relations = RelationBuilder(llm).build_relations(points, target.case_id)
    roadmap = RoadmapBuilder(llm).build_roadmap(target, points, relations)
    assert roadmap.surface_problem
    assert roadmap.target_route == ["P1", "P2", "P3"]
    assert roadmap.solution_points[0].visibility == "judge_only"
