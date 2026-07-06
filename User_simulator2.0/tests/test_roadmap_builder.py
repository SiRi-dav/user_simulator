from src.extraction.point_extractor import PointExtractor
from src.llm.mock_llm_client import MockLLMClient
from main import build_case_analysis_artifacts
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


def test_case_analysis_outputs_are_split_for_blind_and_knowledge_modules():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    related = Case(case_id="CASE_002", title="Outlook 登录失败", phenomenon="密码失败", solution="重置密码")
    blind_view, knowledge_artifact = build_case_analysis_artifacts(target, [target, related], llm, logger=None)
    assert blind_view.case_id == "CASE_001"
    assert blind_view.surface_problem
    assert not hasattr(blind_view, "solution_points")
    assert knowledge_artifact.roadmap.target_case_id == "CASE_001"
