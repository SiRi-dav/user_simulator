from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.llm.llm_client import LLMClient
from src.retrieval.local_candidate_recall import LocalCandidateRecall
from src.retrieval.prompt_templates import RELATED_CASE_SYSTEM, RELATED_CASE_USER
from src.schemas import Case, RelatedCaseSelection, RetrievalQuery, model_to_dict
from src.utils.json_utils import dumps_json
from src.utils.logging import OutputLogger


class RelatedCasesOutput(BaseModel):
    related_cases: List[RelatedCaseSelection]


class RelatedCaseRetriever:
    def __init__(
        self,
        llm_client: LLMClient,
        logger: OutputLogger | None = None,
        top_k: int = 5,
        recall_top_n: int = 50,
    ):
        self.llm_client = llm_client
        self.logger = logger
        self.top_k = top_k
        self.recall_top_n = recall_top_n
        self.local_recall = LocalCandidateRecall(top_n=recall_top_n)

    def retrieve(self, target_case: Case, queries: List[RetrievalQuery], all_cases: List[Case]) -> List[Case]:
        candidate_cases = self.local_recall.recall(target_case, queries, all_cases)
        user_prompt = RELATED_CASE_USER.format(
            target_case_json=dumps_json(model_to_dict(target_case)),
            queries_json=dumps_json(model_to_dict(queries)),
            candidate_cases_json=dumps_json(model_to_dict(candidate_cases)),
            top_k=self.top_k,
        )
        payload = self.llm_client.generate_json(RELATED_CASE_SYSTEM, user_prompt, schema_name="RelatedCases")
        output = RelatedCasesOutput(**payload)
        selected_ids = {item.case_id for item in output.related_cases}
        related_cases = [case for case in candidate_cases if case.case_id in selected_ids]
        if self.logger:
            self.logger.log(
                "related_cases.jsonl",
                target_case.case_id,
                "RelatedCaseRetriever",
                {
                    "target_case": target_case,
                    "queries": queries,
                    "candidate_cases": candidate_cases,
                    "recall_top_n": self.recall_top_n,
                    "all_case_count": len(all_cases),
                    "llm_candidate_count": len(candidate_cases),
                },
                {"selected": output, "related_cases": related_cases},
            )
        return related_cases
