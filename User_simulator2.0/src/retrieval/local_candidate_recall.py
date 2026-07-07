from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, List

from src.schemas import Case, RetrievalQuery


ASCII_TOKEN_RE = re.compile(r"[a-zA-Z0-9_+#.-]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class LocalCandidateRecall:
    def __init__(self, top_n: int = 50):
        self.top_n = top_n

    def recall(self, target_case: Case, queries: List[RetrievalQuery], all_cases: List[Case]) -> List[Case]:
        target_tokens = build_query_tokens(target_case, queries)
        if not target_tokens:
            return [case for case in all_cases if case.case_id != target_case.case_id][: self.top_n]

        scored: list[tuple[float, int, Case]] = []
        for index, case in enumerate(all_cases):
            if case.case_id == target_case.case_id:
                continue
            score = score_case(target_tokens, case)
            if score > 0:
                scored.append((score, index, case))

        scored.sort(key=lambda item: (-item[0], item[1]))
        recalled = [case for _, _, case in scored[: self.top_n]]
        if recalled:
            return recalled
        return [case for case in all_cases if case.case_id != target_case.case_id][: self.top_n]


def build_query_tokens(target_case: Case, queries: List[RetrievalQuery]) -> Counter[str]:
    weighted_texts: list[tuple[str, int]] = [
        (target_case.title, 3),
        (target_case.phenomenon, 2),
        (target_case.solution, 1),
    ]
    for query in queries:
        weight = 3 if query.query_type in {"surface_query", "diagnostic_query"} else 2
        weighted_texts.append((query.query, weight))
    tokens: Counter[str] = Counter()
    for text, weight in weighted_texts:
        for token in tokenize(text):
            tokens[token] += weight
    return tokens


def score_case(query_tokens: Counter[str], case: Case) -> float:
    case_tokens = Counter(tokenize(case_text(case)))
    if not case_tokens:
        return 0.0
    overlap = query_tokens.keys() & case_tokens.keys()
    if not overlap:
        return 0.0
    score = 0.0
    for token in overlap:
        score += query_tokens[token] * (1.0 + math.log1p(case_tokens[token]))
    return score / math.sqrt(sum(case_tokens.values()))


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
