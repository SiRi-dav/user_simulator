POINT_EXTRACTION_SYSTEM = """You are an expert in enterprise IT support case understanding and user simulation.
Extract minimal grounded knowledge points for a simulated user. Do not invent facts. Solution points are judge-only. Related-case points are external/confusing directions.
- Return only valid JSON."""

POINT_EXTRACTION_USER = """Target case:
{target_case_json}
Related cases:
{related_cases_json}
Extract a compact set of points:
- user_facing: directly observable user symptom/opening content.
- diagnostic: hidden fact revealed only when asked.
- solution: target solution/judge-only, never opening content.
- external: related-case confusing direction.
Return JSON:
{{
  "points": [
    {{
      "point_id": "...",
      "source_case_id": "...",
      "content": "...",
      "source_field": "case_name | text",
      "source_quote": "...",
      "point_type": "user_facing | diagnostic | solution | external",
      "grounding_type": "explicit | inferred",
      "trigger": ["..."],
      "visibility": "opening_available | ask_triggered | judge_only | external_only",
      "leakage_risk": "low | medium | high",
      "reason": "..."
    }}
  ]
}}
Requirements:
- Prefer 1-3 user_facing, 1-4 diagnostic, 1-3 solution, and 0-5 external points.
- Explicit points must include source_quote.
- Do not expose solution as user-facing content.
- Keep reason short.
Return only the final JSON. Do not include reasoning text."""

POINT_VERIFICATION_SYSTEM = """You are a strict verifier for grounded support-case knowledge points.
Your task is to verify whether extracted points are valid, grounded, non-conflicting, and safe for user simulation.
Return only valid JSON."""

POINT_VERIFICATION_USER = """Target case:
{target_case_json}
Related cases:
{related_cases_json}
Extracted points:
{points_json}
Verify points with these rules: explicit points need source_quote; target points override related points; solution points must be judge_only and not opening_available; external points should stay external/confusing; drop hallucinations; warn on solution leakage.
Return JSON:
{{
  "verified_points": [...],
  "dropped_points": [...],
  "warnings": [...]
}}
Keep the same Point schema for verified_points and dropped_points.
Return only JSON."""
