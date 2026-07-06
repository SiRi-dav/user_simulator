RELATION_BUILDING_SYSTEM = """You are an expert in constructing lightweight reasoning relations for user simulation.
Given extracted support-case points, build relations that help the Knowledge Module decide how a dialogue should progress.
Return only valid JSON."""

RELATION_BUILDING_USER = """Points:
{points_json}
Build relations among points.
Allowed relation types:
1. specifies
2. asks_for
3. supports_target
4. solution_addresses
5. similar_but_wrong
6. rules_out
7. out_of_scope
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
- Add rules_out relations when target diagnostic points clearly reject external points.
- Do not invent new points.
Return only JSON."""

ROADMAP_BUILDING_SYSTEM = """You are an expert in building a problem-centered roadmap for a simulated user in enterprise IT support.
The roadmap is used by a Knowledge Module, not directly by the Blind User.
The roadmap should organize:
- surface problem,
- hidden diagnostic facts,
- external confused facts,
- judge-only solution points,
- target route,
- external routes,
- forbidden content.
Return only valid JSON."""

ROADMAP_BUILDING_USER = """Target case:
{target_case_json}
Verified points:
{points_json}
Relations:
{relations_json}
Build a roadmap.
Definitions:
- surface_problem: natural user-facing problem extracted from user_facing points.
- opening_intent: what the user wants to achieve.
- user_facing_points: points available for initial user problem.
- diagnostic_points: hidden facts to reveal when assistant asks.
- solution_points: judge-only points used to check if assistant solved the case.
- external_points: confused facts from related cases.
- target_route: a point_id chain from user-facing to diagnostic to solution.
- external_routes: point_id chains involving external points.
- forbidden_content: anything Blind User must not reveal, especially solution and case id.
Return JSON:
{{
  "target_case_id": "...",
  "surface_problem": "...",
  "opening_intent": "...",
  "user_facing_points": [...],
  "diagnostic_points": [...],
  "solution_points": [...],
  "external_points": [...],
  "relations": [...],
  "target_route": ["point_id", "..."],
  "external_routes": [["point_id", "..."]],
  "forbidden_content": [...]
}}
Requirements:
- Do not put solution content into surface_problem.
- solution_points must be judge-only.
- surface_problem should sound like a real user problem, not a case title.
- target_route should include at least one user_facing point and one solution point if available.
- external_routes are for detecting off-track assistant behavior.
Return only JSON."""
