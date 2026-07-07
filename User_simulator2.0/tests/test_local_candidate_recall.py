from src.retrieval.local_candidate_recall import LocalCandidateRecall
from src.retrieval.related_case_retriever import RelatedCaseRetriever
from src.schemas import Case, RetrievalQuery


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
