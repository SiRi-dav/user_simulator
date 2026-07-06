from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.llm.llm_client import LLMClient
from src.retrieval.prompt_templates import QUERY_GENERATION_SYSTEM, QUERY_GENERATION_USER
from src.schemas import Case, RetrievalQuery, model_to_dict
from src.utils.logging import OutputLogger


class RetrievalQueriesOutput(BaseModel):
    queries: List[RetrievalQuery]


class QueryGenerator:
    def __init__(self, llm_client: LLMClient, logger: OutputLogger | None = None):
        self.llm_client = llm_client
        self.logger = logger

    def generate_queries(self, target_case: Case) -> List[RetrievalQuery]:
        user_prompt = QUERY_GENERATION_USER.format(**model_to_dict(target_case))
        payload = self.llm_client.generate_json(QUERY_GENERATION_SYSTEM, user_prompt, schema_name="RetrievalQueries")
        output = RetrievalQueriesOutput(**payload)
        if self.logger:
            self.logger.log(
                "generated_queries.jsonl",
                target_case.case_id,
                "QueryGenerator",
                {"target_case": target_case},
                output,
            )
        return output.queries
