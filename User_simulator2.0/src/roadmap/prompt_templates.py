RELATION_BUILDING_SYSTEM = """You are an expert in constructing lightweight reasoning relations for user simulation.
Build only the useful relations needed for dialogue progress.
Return only valid JSON."""

RELATION_BUILDING_USER = """Points:
{points_json}
Build relations among points.
Allowed relation types: specifies, asks_for, supports_target, solution_addresses, similar_but_wrong, rules_out, out_of_scope.
Return JSON:
{{
  "relations": [
    {{
      "from_point_id": "...",
      "to_point_id": "...",
      "relation_type": "...",
      "reason": "..."
    }}
  ]
}}
Requirements:
- Build a minimal useful relation set, not a dense graph.
- Connect user_facing points to diagnostic points.
- Connect diagnostic points to solution points.
- Connect external points to target points if they are similar but wrong.
- Do not invent new points.
Return only JSON."""

ROADMAP_BUILDING_SYSTEM = """You are an expert in building a problem-centered roadmap for a simulated user in enterprise IT support.
Build a compact roadmap for the Knowledge Module: surface problem, hidden diagnostics, external confusion, judge-only solutions, routes, and forbidden content.
Return only valid JSON."""

ROADMAP_BUILDING_USER = """Target case:
{target_case_json}
Verified points:
{points_json}
Relations:
{relations_json}
Build a roadmap. Keep surface_problem natural and user-facing; solution_points are judge-only; target_route links user-facing/diagnostic/solution points; external_routes capture confusion paths.
Return JSON:
{{
  "target_case_id": "...",
  "surface_problem": "...",
  "opening_intent": "...",
  "user_facing_points": [complete Point objects from Verified points],
  "diagnostic_points": [complete Point objects from Verified points],
  "solution_points": [complete Point objects from Verified points],
  "external_points": [complete Point objects from Verified points],
  "relations": [complete Relation objects from Relations],
  "target_route": ["point_id", "..."],
  "external_routes": [["point_id", "..."]],
  "forbidden_content": [...]
}}
Requirements:
- Reuse the complete Point objects from Verified points. Do not invent a shorter point schema.
- Reuse the complete Relation objects from Relations. Do not invent a shorter relation schema.
- Do not put solution content into surface_problem.
- solution_points must be judge-only.
- surface_problem should sound like a real user problem, not a case title.
- target_route should include at least one user_facing point and one solution point if available.
- external_routes are for detecting off-track assistant behavior.
Return only JSON."""
