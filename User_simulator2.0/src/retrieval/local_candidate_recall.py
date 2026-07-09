from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from src.schemas import Case, RetrievalQuery


ASCII_TOKEN_RE = re.compile(r"[a-zA-Z0-9_+#.-]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ROUTE_TYPES = ("surface", "diagnostic", "solution", "confusion")
QUERY_ROUTE = {
    "surface_query": "surface",
    "diagnostic_query": "diagnostic",
    "solution_query": "solution",
    "confusion_query": "confusion",
}


@dataclass
class RecalledCandidate:
    case: Case
    hybrid_score: float
    route_scores: Dict[str, float] = field(default_factory=dict)
    bm25_scores: Dict[str, float] = field(default_factory=dict)
    semantic_scores: Dict[str, float] = field(default_factory=dict)

    def score_payload(self) -> dict:
        return {
            "hybrid_score": round(self.hybrid_score, 4),
            "route_scores": {key: round(value, 4) for key, value in self.route_scores.items()},
            "bm25_scores": {key: round(value, 4) for key, value in self.bm25_scores.items()},
            "semantic_scores": {key: round(value, 4) for key, value in self.semantic_scores.items()},
        }


class LocalCandidateRecall:
    def __init__(
        self,
        top_n: int = 50,
        per_route_top_n: int = 12,
        bm25_weight: float = 0.6,
        semantic_weight: float = 0.4,
    ):
        self.top_n = top_n
        self.per_route_top_n = per_route_top_n
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight

    def recall(self, target_case: Case, queries: List[RetrievalQuery], all_cases: List[Case]) -> List[Case]:
        return [item.case for item in self.recall_scored(target_case, queries, all_cases)]

    def recall_scored(
        self,
        target_case: Case,
        queries: List[RetrievalQuery],
        all_cases: List[Case],
    ) -> List[RecalledCandidate]:
        corpus = [case for case in all_cases if case.case_id != target_case.case_id]
        if not corpus:
            return []

        route_queries = build_route_queries(target_case, queries)
        merged: dict[str, RecalledCandidate] = {}
        route_ranks: dict[str, dict[str, int]] = {}

        for route in ROUTE_TYPES:
            query_tokens = Counter(tokenize(route_queries[route]))
            document_tokens = {case.case_id: Counter(tokenize(route_case_text(case, route))) for case in corpus}
            bm25 = bm25_scores(query_tokens, document_tokens)
            semantic = {
                case_id: cosine_similarity(query_tokens, tokens)
                for case_id, tokens in document_tokens.items()
            }
            normalized_bm25 = normalize_scores(bm25)
            hybrid = {
                case.case_id: (
                    self.bm25_weight * normalized_bm25.get(case.case_id, 0.0)
                    + self.semantic_weight * semantic.get(case.case_id, 0.0)
                )
                for case in corpus
            }
            ranked = sorted(corpus, key=lambda case: (-hybrid[case.case_id], case.case_id))
            ranked = [case for case in ranked if hybrid[case.case_id] > 0][: self.per_route_top_n]
            route_ranks[route] = {case.case_id: index + 1 for index, case in enumerate(ranked)}

            for case in ranked:
                item = merged.setdefault(case.case_id, RecalledCandidate(case=case, hybrid_score=0.0))
                item.route_scores[route] = hybrid[case.case_id]
                item.bm25_scores[route] = normalized_bm25.get(case.case_id, 0.0)
                item.semantic_scores[route] = semantic.get(case.case_id, 0.0)

        if not merged:
            return [RecalledCandidate(case=case, hybrid_score=0.0) for case in corpus[: self.top_n]]

        for case_id, item in merged.items():
            reciprocal_rank = sum(
                1.0 / (60 + ranks[case_id])
                for ranks in route_ranks.values()
                if case_id in ranks
            )
            best_route_score = max(item.route_scores.values(), default=0.0)
            route_coverage = len(item.route_scores) / len(ROUTE_TYPES)
            item.hybrid_score = best_route_score + 0.25 * reciprocal_rank + 0.05 * route_coverage

        return sorted(
            merged.values(),
            key=lambda item: (-item.hybrid_score, item.case.case_id),
        )[: self.top_n]


def build_route_queries(target_case: Case, queries: List[RetrievalQuery]) -> Dict[str, str]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for query in queries:
        route = QUERY_ROUTE.get(query.query_type)
        if route:
            grouped[route].append(query.query)

    return {
        "surface": " ".join([target_case.title, target_case.phenomenon, *grouped["surface"]]),
        "diagnostic": " ".join([target_case.phenomenon, *grouped["diagnostic"]]),
        "solution": " ".join([target_case.solution, *grouped["solution"]]),
        "confusion": " ".join(
            [target_case.title, target_case.phenomenon, *grouped["confusion"], *grouped["diagnostic"]]
        ),
    }


def route_case_text(case: Case, route: str) -> str:
    if route == "surface":
        return " ".join([case.title or "", case.phenomenon or ""])
    if route == "solution":
        return case.solution or ""
    if route == "diagnostic":
        return " ".join([case.phenomenon or "", case.solution or ""])
    return " ".join([case.title or "", case.phenomenon or "", case.solution or ""])


def bm25_scores(
    query_tokens: Counter[str],
    documents: Dict[str, Counter[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> Dict[str, float]:
    if not query_tokens or not documents:
        return {case_id: 0.0 for case_id in documents}
    document_count = len(documents)
    average_length = sum(sum(tokens.values()) for tokens in documents.values()) / max(document_count, 1)
    document_frequency = Counter(
        token
        for tokens in documents.values()
        for token in tokens.keys() & query_tokens.keys()
    )
    scores: dict[str, float] = {}
    for case_id, tokens in documents.items():
        length = sum(tokens.values())
        score = 0.0
        for token, query_weight in query_tokens.items():
            frequency = tokens.get(token, 0)
            if not frequency:
                continue
            frequency_in_docs = document_frequency.get(token, 0)
            inverse_frequency = math.log(1.0 + (document_count - frequency_in_docs + 0.5) / (frequency_in_docs + 0.5))
            denominator = frequency + k1 * (1.0 - b + b * length / max(average_length, 1.0))
            score += query_weight * inverse_frequency * frequency * (k1 + 1.0) / denominator
        scores[case_id] = score
    return scores


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = left.keys() & right.keys()
    numerator = sum(left[token] * right[token] for token in overlap)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    maximum = max(scores.values(), default=0.0)
    if maximum <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / maximum for key, value in scores.items()}


def case_text(case: Case) -> str:
    return " ".join([case.title or "", case.phenomenon or "", case.solution or ""])


def tokenize(text: str) -> list[str]:
    normalized = (text or "").lower()
    tokens: list[str] = []
    tokens.extend(match.group(0) for match in ASCII_TOKEN_RE.finditer(normalized))
    cjk_chars = [char for char in normalized if CJK_RE.match(char)]
    tokens.extend(char_ngrams(cjk_chars, 2))
    tokens.extend(char_ngrams(cjk_chars, 3))
    return [token for token in tokens if len(token.strip()) > 1]


def char_ngrams(chars: Iterable[str], size: int) -> list[str]:
    values = list(chars)
    if len(values) < size:
        return []
    return ["".join(values[index : index + size]) for index in range(len(values) - size + 1)]
