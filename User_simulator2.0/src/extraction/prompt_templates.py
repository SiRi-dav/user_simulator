POINT_EXTRACTION_SYSTEM = """You are an expert in enterprise IT support case understanding and user simulation.
Your task is to extract grounded knowledge points from a target case and its related cases.
These points will be used by a Knowledge Module to control what a simulated user can reveal during a dialogue.
Important:
- Do not freely invent facts.
- Each point must be grounded in a source_quote from the case text, unless grounding_type is "inferred".
- Solution points are judge-only and must not be used as user opening content.
- Related case points are external points. They represent plausible but potentially wrong or confusing directions.
- Return only valid JSON."""

POINT_EXTRACTION_USER = """Target case:
{target_case_json}
Related cases:
{related_cases_json}
Extract four types of points:
1. user_facing
Meaning:
- A fact or symptom the user can directly observe.
- It can be used to generate the initial surface problem.
2. diagnostic
Meaning:
- A fact that helps distinguish the target case.
- Usually revealed only when the assistant asks.
- Similar to hidden fact.
3. solution
Meaning:
- A solution action or final handling step from the target case.
- Used only by the Knowledge Module to judge whether assistant solved the case.
- Must not be leaked to Blind User as normal content.
4. external
Meaning:
- A point from related cases.
- It represents a similar but potentially wrong direction.
- Used to detect if assistant goes off-track.
For each point, output the Point schema.
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
Reasoning steps to follow internally:
1. Identify what the user can directly observe in the target case.
2. Identify what information should be hidden until the assistant asks.
3. Identify solution-only information from the target case.
4. Identify related-case information that may confuse the diagnosis.
5. Assign visibility and leakage risk carefully.
6. Ensure every explicit point has a source_quote.
7. Do not expose solution as user-facing content.
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
Verify the points.
Rules:
1. Explicit points must have source_quote.
2. Points from the target case have priority over points from related cases.
3. Related case points must not override target case points.
4. Solution points must be judge_only and high or medium leakage risk.
5. Solution points must not be opening_available.
6. External points should be external_only unless they are used for clarification.
7. If an external point conflicts with a target point, keep the target point and mark the external point as confusing or drop it if unsafe.
8. Drop hallucinated points.
9. Warn if a point might leak the target solution to Blind User.
Return JSON:
{{
  "verified_points": [...],
  "dropped_points": [...],
  "warnings": [...]
}}
Keep the same Point schema for verified_points and dropped_points.
Return only JSON."""
