from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from src.llm.llm_client import LLMClient
from src.retrieval.local_candidate_recall import LocalCandidateRecall
from src.retrieval.prompt_templates import RELATED_CASE_SYSTEM, RELATED_CASE_USER
from src.schemas import Case, RelatedCaseSelection, RetrievalQuery, model_to_dict
from src.utils.json_utils import dumps_json
from src.utils.logging import OutputLogger


class RelatedCasesOutput(BaseModel):
    ranked_cases: List[RelatedCaseSelection] = Field(default_factory=list)
    related_cases: List[RelatedCaseSelection] = Field(default_factory=list)


class RelatedCaseRetriever:
    def __init__(
        self,
        llm_client: LLMClient,
        logger: OutputLogger | None = None,
        top_k: int = 5,
        recall_top_n: int = 50,
        per_route_top_n: int = 12,
        rerank_top_n: int = 20,
        minimum_score: float = 0.35,
        fallback_min_cases: int = 2,
        bm25_weight: float = 0.6,
        semantic_weight: float = 0.4,
    ):
        self.llm_client = llm_client
        self.logger = logger
        self.top_k = top_k
        self.recall_top_n = recall_top_n
        self.rerank_top_n = rerank_top_n
        self.minimum_score = minimum_score
        self.fallback_min_cases = min(fallback_min_cases, top_k)
        self.local_recall = LocalCandidateRecall(
            top_n=recall_top_n,
            per_route_top_n=per_route_top_n,
            bm25_weight=bm25_weight,
            semantic_weight=semantic_weight,
        )

    def retrieve(self, target_case: Case, queries: List[RetrievalQuery], all_cases: List[Case]) -> List[Case]:
        recalled = self.local_recall.recall_scored(target_case, queries, all_cases)
        candidate_cases = [item.case for item in recalled]
        candidate_payload = [
            {**model_to_dict(item.case), "retrieval_scores": item.score_payload()}
            for item in recalled
        ]
        user_prompt = RELATED_CASE_USER.format(
            target_case_json=dumps_json(model_to_dict(target_case)),
            queries_json=dumps_json(model_to_dict(queries)),
            candidate_cases_json=dumps_json(candidate_payload),
            rerank_top_n=self.rerank_top_n,
        )
        payload = self.llm_client.generate_json(RELATED_CASE_SYSTEM, user_prompt, schema_name="RelatedCases")
        output = RelatedCasesOutput(**payload)
        rankings = output.ranked_cases or output.related_cases
        if output.related_cases and not output.ranked_cases:
            for item in rankings:
                if item.overall_score <= 0:
                    item.overall_score = 1.0
        rankings = [item for item in rankings if item.case_id in {case.case_id for case in candidate_cases}]
        rankings.sort(key=lambda item: (-item.overall_score, item.case_id))
        selected = select_diverse_rankings(rankings, self.top_k, self.minimum_score)
        selected_ids = {item.case_id for item in selected}
        fallback_used = False
        if len(selected_ids) < self.fallback_min_cases:
            fallback_used = True
            for candidate in recalled:
                if candidate.case.case_id in selected_ids:
                    continue
                if candidate.hybrid_score <= 0:
                    continue
                selected_ids.add(candidate.case.case_id)
                if len(selected_ids) >= self.fallback_min_cases:
                    break
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
                    "multi_route_candidates": [
                        {"case_id": item.case.case_id, **item.score_payload()} for item in recalled
                    ],
                },
                {
                    "ranked": output,
                    "selected_rankings": selected,
                    "fallback_used": fallback_used,
                    "related_cases": related_cases,
                    "funnel": {
                        "all_case_count": len(all_cases),
                        "hybrid_recall_count": len(recalled),
                        "llm_ranked_count": len(rankings),
                        "threshold_selected_count": len(selected),
                        "final_related_count": len(related_cases),
                    },
                },
            )
        return related_cases


def select_diverse_rankings(
    rankings: List[RelatedCaseSelection],
    top_k: int,
    minimum_score: float,
) -> List[RelatedCaseSelection]:
    eligible = [item for item in rankings if item.overall_score >= minimum_score]
    selected: list[RelatedCaseSelection] = []
    selected_ids: set[str] = set()
    representatives: list[RelatedCaseSelection] = []
    for relation_type in (
        "similar_surface",
        "similar_diagnostic",
        "similar_solution",
        "confusing_wrong_path",
    ):
        match = next((item for item in eligible if item.relation_type == relation_type), None)
        if match:
            representatives.append(match)
    for match in sorted(representatives, key=lambda item: (-item.overall_score, item.case_id)):
        if match.case_id not in selected_ids:
            selected.append(match)
            selected_ids.add(match.case_id)
        if len(selected) >= top_k:
            return selected
    for item in eligible:
        if item.case_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.case_id)
        if len(selected) >= top_k:
            break
    return selected
