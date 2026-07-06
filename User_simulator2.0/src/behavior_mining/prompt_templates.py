PERSONA_MINING_SYSTEM = """You are an expert in analyzing enterprise IT support dialogue logs.
Your task is to infer common employee user personas from historical support dialogues.
A persona should describe stable user behavior patterns, not just writing style.
Focus on:
- technical literacy,
- patience,
- clarity,
- cooperation,
- willingness to provide details,
- reaction to action requests,
- reaction to off-track questions,
- reaction to solution suggestions.
Return only valid JSON."""

PERSONA_MINING_USER = """Historical dialogues:
{dialogues_json}
Infer common employee personas from these dialogues.
A persona should summarize repeated behavior patterns across dialogues.
For each persona, output:
{{
  "persona_id": "...",
  "persona_name": "...",
  "description": "...",
  "technical_literacy": "low | medium | high",
  "patience_level": "low | medium | high",
  "clarity_level": "vague | medium | clear",
  "cooperation_level": "low | medium | high",
  "typical_opening_style": ["..."],
  "information_release_style": "...",
  "action_request_behavior": "...",
  "offtrack_reaction_style": "...",
  "solution_acceptance_style": "...",
  "evidence_dialogue_ids": ["..."],
  "reason": "..."
}}
Requirements:
- Do not invent unrealistic personas.
- Each persona must be supported by dialogue evidence.
- Focus on behavior, not demographics.
- Personas will be used to control a simulated user's behavior.
- Return 3 to 6 personas if possible.
Return JSON:
{{
  "personas": [...]
}}
Return only JSON."""

BEHAVIOR_TAXONOMY_SYSTEM = """You are an expert in dialogue behavior analysis for enterprise IT support.
Your task is to analyze historical support dialogues and build a behavior taxonomy for simulated users.
The taxonomy should describe how real employee users react to different assistant acts.
Return only valid JSON."""

BEHAVIOR_TAXONOMY_USER = """Historical dialogues:
{dialogues_json}
We are building a user simulator. We need to know whether user behavior can be categorized by assistant acts such as:
- clarification_question
- action_request
- solution_output
- generic_advice
- offtrack_question
Analyze the dialogues and summarize user behavior categories.
For each behavior category, output:
{{
  "behavior_name": "...",
  "definition": "...",
  "trigger_assistant_acts": ["..."],
  "typical_user_response_patterns": ["..."],
  "persona_sensitivity": {{
    "low_tech": "...",
    "impatient": "...",
    "cooperative": "...",
    "vague": "..."
  }},
  "simulator_policy_hint": "how this behavior should be implemented in the simulator"
}}
Important behavior types to check:
1. answering clarification questions,
2. revealing new diagnostic facts,
3. asking how to perform an action,
4. attempting an action and reporting result,
5. saying the requested information is unavailable,
6. denying or correcting an off-track assumption,
7. repeating the surface problem,
8. accepting a solution,
9. rejecting a solution as not applicable,
10. showing frustration or impatience.
Return JSON:
{{
  "behavior_taxonomy": [...]
}}
Requirements:
- Use the historical dialogues as evidence.
- You may modify, merge, or add behavior categories if the data suggests it.
- Do not force all categories if not observed.
- Focus on behavior useful for runtime user simulation.
Return only JSON."""

DIALOGUE_SUMMARY_SYSTEM = """You are an expert in analyzing one enterprise IT support dialogue.
Your task is to extract user behavior events from the dialogue.
Focus on how the user reacts to assistant questions, action requests, off-track assumptions, and solution suggestions.
Return only valid JSON."""

DIALOGUE_SUMMARY_USER = """Dialogue:
{dialogue_json}
Analyze the user's behavior in this dialogue.
For each assistant-user pair, identify:
- assistant_act,
- user_behavior,
- released_information_type,
- whether the user provided new information,
- whether the user accepted, rejected, or ignored the assistant's direction.
Allowed assistant_act:
- clarification_question
- action_request
- solution_output
- generic_advice
- offtrack_question
- unknown
Allowed user_behavior:
- answer_fact
- reveal_new_fact
- provide_partial_info
- ask_how_to_perform
- attempt_action
- report_action_result
- say_unknown
- deny_or_correct
- repeat_surface_problem
- accept_solution
- reject_solution
- express_frustration
- unknown
Allowed released_information_type:
- surface_problem
- diagnostic_fact
- prior_attempt
- environment
- error_message
- asset_id
- action_result
- none
- unknown
Return JSON:
{{
  "dialogue_id": "...",
  "opening_pattern": "...",
  "user_persona_guess": "...",
  "observed_behaviors": [
    {{
      "dialogue_id": "...",
      "turn_index": 0,
      "assistant_act": "...",
      "user_behavior": "...",
      "user_text": "...",
      "assistant_text": "...",
      "released_information_type": "...",
      "behavior_reason": "..."
    }}
  ],
  "voluntary_information": ["..."],
  "ask_triggered_information": ["..."],
  "action_request_reactions": ["..."],
  "offtrack_reactions": ["..."],
  "solution_reactions": ["..."],
  "summary": "..."
}}
Return only JSON."""
