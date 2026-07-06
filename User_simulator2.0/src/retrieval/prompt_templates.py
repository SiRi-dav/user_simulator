QUERY_GENERATION_SYSTEM = """You are an expert in enterprise IT support case analysis.
Your task is to generate retrieval queries for finding cases related to a target support case.
The purpose is not to find the exact same case only. The purpose is to build a knowledge space around the user's problem, including:
1. cases with similar surface symptoms,
2. cases with similar diagnostic clues,
3. cases with potentially confusing but different causes,
4. cases with similar solution actions.
Return only valid JSON."""

QUERY_GENERATION_USER = """Target case:
case_id: {case_id}
title: {title}
phenomenon: {phenomenon}
solution: {solution}
Generate retrieval queries in the following JSON format:
{{
  "queries": [
    {{
      "query_type": "surface_query | diagnostic_query | solution_query",
      "query": "...",
      "reason": "..."
    }}
  ]
}}
Requirements:
- Generate 3 to 6 queries.
- surface_query should focus on what the user can observe.
- diagnostic_query should focus on clues needed to distinguish the case.
- solution_query should focus on solution actions, but do not turn the solution into user wording.
- Do not include case_id in the query."""

RELATED_CASE_SYSTEM = """You are an expert in enterprise IT support case retrieval.
Given a target case, retrieval queries, and candidate cases, select cases that are useful for constructing a knowledge space around the target user's problem.
A useful related case can be:
1. similar surface symptom,
2. similar affected system,
3. similar but wrong diagnosis,
4. similar solution action,
5. plausible confusion path.
Return only valid JSON."""

RELATED_CASE_USER = """Target case:
{target_case_json}
Retrieval queries:
{queries_json}
Candidate cases:
{candidate_cases_json}
Select related cases.
Return JSON:
{{
  "related_cases": [
    {{
      "case_id": "...",
      "relation_type": "similar_surface | similar_diagnostic | similar_solution | confusing_wrong_path",
      "reason": "..."
    }}
  ]
}}
Requirements:
- Select up to {top_k} related cases.
- Do not select the target case itself.
- Prefer cases that help distinguish the target case from similar but wrong cases."""
