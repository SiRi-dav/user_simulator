from src.retrieval.local_candidate_recall import LocalCandidateRecall
from src.retrieval.related_case_retriever import RelatedCaseRetriever, select_diverse_rankings
from src.schemas import Case, RelatedCaseSelection, RetrievalQuery


class CapturingLLMClient:
    def __init__(self):
        self.user_prompt = ""

    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        self.user_prompt = user_prompt
        return {
            "related_cases": [
                {
                    "case_id": "CASE_RELATED",
                    "relation_type": "similar_surface",
                    "reason": "same affected system and symptom",
                }
            ]
        }


def test_local_candidate_recall_prefers_similar_cases():
    target = Case(case_id="CASE_TARGET", title="Outlook 打开后闪退", phenomenon="启动后退出", solution="结束残留进程")
    related = Case(case_id="CASE_RELATED", title="Outlook 启动闪退", phenomenon="打开就退出", solution="重建配置")
    unrelated = Case(case_id="CASE_UNRELATED", title="打印机无法打印", phenomenon="纸张卡住", solution="清理纸盒")
    queries = [RetrievalQuery(query_type="surface_query", query="Outlook 打开后闪退", reason="surface symptom")]

    recalled = LocalCandidateRecall(top_n=1).recall(target, queries, [target, unrelated, related])

    assert [case.case_id for case in recalled] == ["CASE_RELATED"]


def test_related_case_retriever_only_sends_recalled_candidates_to_llm():
    target = Case(case_id="CASE_TARGET", title="Outlook 打开后闪退", phenomenon="启动后退出", solution="结束残留进程")
    related = Case(case_id="CASE_RELATED", title="Outlook 启动闪退", phenomenon="打开就退出", solution="重建配置")
    unrelated = Case(case_id="CASE_UNRELATED", title="打印机无法打印", phenomenon="纸张卡住", solution="清理纸盒")
    queries = [RetrievalQuery(query_type="surface_query", query="Outlook 打开后闪退", reason="surface symptom")]
    llm = CapturingLLMClient()

    selected = RelatedCaseRetriever(llm, recall_top_n=1).retrieve(target, queries, [target, unrelated, related])

    assert [case.case_id for case in selected] == ["CASE_RELATED"]
    assert "CASE_RELATED" in llm.user_prompt
    assert "CASE_UNRELATED" not in llm.user_prompt


def test_multi_route_recall_keeps_surface_and_solution_candidates():
    target = Case(
        case_id="TARGET",
        title="Alpha客户端异常",
        phenomenon="启动后出现红色窗口",
        solution="刷新令牌缓存",
    )
    surface = Case(
        case_id="SURFACE",
        title="Alpha客户端红色窗口",
        phenomenon="启动时显示红色窗口",
        solution="重新安装客户端",
    )
    solution = Case(
        case_id="SOLUTION",
        title="Beta登录失败",
        phenomenon="认证无法通过",
        solution="刷新令牌缓存",
    )
    queries = [
        RetrievalQuery(query_type="surface_query", query="Alpha 红色窗口", reason="surface"),
        RetrievalQuery(query_type="solution_query", query="刷新令牌缓存", reason="solution"),
    ]

    recalled = LocalCandidateRecall(top_n=4, per_route_top_n=1).recall_scored(
        target,
        queries,
        [target, surface, solution],
    )
    by_id = {item.case.case_id: item for item in recalled}

    assert "surface" in by_id["SURFACE"].route_scores
    assert "solution" in by_id["SOLUTION"].route_scores


def test_llm_rankings_are_score_sorted_with_relation_diversity():
    rankings = [
        RelatedCaseSelection(
            case_id="SURFACE",
            relation_type="similar_surface",
            reason="surface",
            overall_score=0.7,
        ),
        RelatedCaseSelection(
            case_id="DIAGNOSTIC",
            relation_type="similar_diagnostic",
            reason="diagnostic",
            overall_score=0.8,
        ),
        RelatedCaseSelection(
            case_id="SOLUTION",
            relation_type="similar_solution",
            reason="solution",
            overall_score=0.9,
        ),
        RelatedCaseSelection(
            case_id="CONFUSION",
            relation_type="confusing_wrong_path",
            reason="confusion",
            overall_score=0.95,
        ),
    ]

    selected = select_diverse_rankings(rankings, top_k=3, minimum_score=0.35)

    assert [item.case_id for item in selected] == ["CONFUSION", "SOLUTION", "DIAGNOSTIC"]


class EmptyRankingLLMClient:
    def generate_json(self, system_prompt, user_prompt, schema_name=None, temperature=0.2):
        return {"ranked_cases": []}


def test_related_case_retriever_falls_back_when_llm_returns_empty():
    target = Case(case_id="TARGET", title="Outlook闪退", phenomenon="打开即退出", solution="结束残留进程")
    first = Case(case_id="FIRST", title="Outlook打开退出", phenomenon="启动闪退", solution="重建配置")
    second = Case(case_id="SECOND", title="Outlook启动失败", phenomenon="无法打开", solution="结束进程")
    queries = [RetrievalQuery(query_type="surface_query", query="Outlook闪退", reason="surface")]

    related = RelatedCaseRetriever(
        EmptyRankingLLMClient(),
        top_k=5,
        recall_top_n=10,
        fallback_min_cases=2,
    ).retrieve(target, queries, [target, first, second])

    assert len(related) == 2
