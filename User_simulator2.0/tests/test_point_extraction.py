from src.extraction.point_extractor import PointExtractor
from src.extraction.point_verifier import PointVerifier
from src.llm.mock_llm_client import MockLLMClient
from src.schemas import Case


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
