from src.extraction.point_extractor import PointExtractor
from src.extraction.point_verifier import PointVerifier
from src.llm.mock_llm_client import MockLLMClient
from src.schemas import Case


class SparsePointLLMClient(MockLLMClient):
    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        if schema_name == "Points":
            return {
                "points": [
                    {"point_id": "user_01", "content": "用户提交单子后显示不在物流专员分组", "visibility": "user_facing"},
                    {"point_id": "diag_01", "content": "需要确认用户权限是否到期", "visibility": "hidden"},
                    {"point_id": "sol_01", "content": "权限正常且新账号数据场景需要等待第一天", "visibility": "judge_only"},
                ]
            }
        return super().generate_json(system_prompt, user_prompt, schema_name, temperature)


def test_point_extraction_returns_four_types():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    related = [Case(case_id="CASE_002", title="Outlook 登录失败", phenomenon="密码失败", solution="重置密码")]
    points = PointExtractor(llm).extract_points(target, related)
    assert {point.point_type for point in points} == {"user_facing", "diagnostic", "solution", "external"}


def test_point_verifier_returns_verified_points():
    llm = MockLLMClient()
    target = Case(case_id="CASE_001", title="Outlook 打开后闪退", phenomenon="打开后退出", solution="结束残留进程")
    related = [Case(case_id="CASE_002", title="Outlook 登录失败", phenomenon="密码失败", solution="重置密码")]
    points = PointExtractor(llm).extract_points(target, related)
    result = PointVerifier(llm).verify_points(target, related, points)
    assert result.verified_points
    assert result.warnings == []


def test_point_extraction_fills_defaults_for_sparse_llm_points():
    llm = SparsePointLLMClient()
    target = Case(case_id="KT00141862", title="无法录单", phenomenon="提交单子显示不在物流专员分组", solution="检查权限或等待数据集成")
    points = PointExtractor(llm).extract_points(target, [])

    assert [point.point_type for point in points] == ["user_facing", "diagnostic", "solution"]
    assert points[0].source_case_id == "KT00141862"
    assert points[0].source_field == "text"
    assert points[0].source_quote == "用户提交单子后显示不在物流专员分组"
    assert points[1].visibility == "hidden"
    assert points[1].grounding_type == "explicit"
    assert points[2].leakage_risk == "high"
