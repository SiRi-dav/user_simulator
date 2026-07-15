QUERY_GENERATION_SYSTEM = """You are an expert in enterprise IT support case analysis.
Generate compact retrieval queries for related support cases. Cover surface symptom, diagnostic clue, solution action, and plausible confusion path.
Return only valid JSON."""

QUERY_GENERATION_USER = """Target case:
case_id: {case_id}
title: {title}
phenomenon: {phenomenon}
solution: {solution}
Generate exactly 4 retrieval queries, one for each query_type:
{{
  "queries": [
    {{
      "query_type": "surface_query | diagnostic_query | solution_query | confusion_query",
      "query": "...",
      "reason": "..."
    }}
  ]
}}
Requirements:
- surface_query should focus on what the user can observe.
- diagnostic_query should focus on clues needed to distinguish the case.
- solution_query should focus on solution actions, but do not turn the solution into user wording.
- confusion_query should describe a plausible same-system or same-symptom case with a different cause or solution.
- Keep query and reason concise.
- Do not include case_id in the query."""

RELATED_CASE_SYSTEM = """You are an expert in enterprise IT support case retrieval and semantic reranking.
Rank compact candidate cases for building a target/confusion knowledge space around the user's problem.
Return only valid JSON."""

RELATED_CASE_USER = """Target case:
{target_case_json}
Retrieval queries:
{queries_json}
Candidate cases:
{candidate_cases_json}
Score and rank the strongest related cases. Do not make only a binary select/reject decision.
Return JSON:
{{
  "ranked_cases": [
    {{
      "case_id": "...",
      "relation_type": "similar_surface | similar_diagnostic | similar_solution | confusing_wrong_path",
      "surface_score": 0.0,
      "diagnostic_score": 0.0,
      "solution_score": 0.0,
      "confusion_score": 0.0,
      "overall_score": 0.0,
      "reason": "..."
    }}
  ]
}}
Requirements:
- Return up to {rerank_top_n} candidates in descending overall_score.
- Every score must be between 0.0 and 1.0.
- overall_score should reflect usefulness for building target and confusing routes, not just text similarity.
- relation_type must represent the candidate's strongest useful relation.
- Do not select the target case itself.
- Give low scores to cases that only share generic words.
- Include useful confusing_wrong_path cases even when their final solution differs.
- Keep reason short."""
