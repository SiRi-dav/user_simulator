from src.extraction.point_extractor import PointExtractor
from src.llm.mock_llm_client import MockLLMClient
from main import build_case_analysis_artifacts
from src.roadmap.relation_builder import RelationBuilder
from src.roadmap.roadmap_builder import RoadmapBuilder
from src.schemas import Case


class SparseRoadmapLLMClient(MockLLMClient):
    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        if schema_name == "Roadmap":
            return {
                "target_case_id": "KT001",
                "surface_problem": "提交单子后显示不在物流专员分组",
                "opening_intent": "希望恢复正常录单",
                "user_facing_points": [{"point_id": "P1", "content": "显示不在物流专员分组"}],
                "diagnostic_points": [{"point_id": "P2", "content": "需要检查权限"}],
                "solution_points": [{"point_id": "P3", "content": "等待数据集成", "visibility": "judge_only"}],
                "external_points": [],
                "relations": [],
                "target_route": ["P1", "P2", "P3"],
                "external_routes": [],
                "forbidden_content": ["不要泄露解决方案"],
            }
        return super().generate_json(system_prompt, user_prompt, schema_name, temperature)


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
    blind_view, knowledge_artifact, debug_artifact = build_case_analysis_artifacts(target, [target, related], llm, logger=None)
    assert blind_view.case_id == "CASE_001"
    assert blind_view.surface_problem
    assert not hasattr(blind_view, "solution_points")
    assert knowledge_artifact.roadmap.target_case_id == "CASE_001"
    assert knowledge_artifact.roadmap.solution_points[0].content
    assert not hasattr(knowledge_artifact.roadmap.solution_points[0], "source_quote")
    assert debug_artifact.related_cases[0].case_id == "CASE_002"


def test_roadmap_builder_fills_sparse_point_groups_from_verified_points():
    llm = SparseRoadmapLLMClient()
    target = Case(case_id="KT001", title="无法录单", phenomenon="提交单子显示不在物流专员分组", solution="等待数据集成")
    points = PointExtractor(MockLLMClient()).extract_points(target, [])

    roadmap = RoadmapBuilder(llm).build_roadmap(target, points, [])

    assert roadmap.user_facing_points[0].source_case_id == "CASE_001"
    assert roadmap.user_facing_points[0].source_field
    assert roadmap.solution_points[0].leakage_risk == "high"
