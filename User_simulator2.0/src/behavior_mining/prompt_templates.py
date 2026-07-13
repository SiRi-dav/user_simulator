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

BEHAVIOR_TAXONOMY_SYSTEM = """You are an expert in dialogue behavior analysis for enterprise IT support user simulation.
Your task is not to create many fine-grained labels.
Your task is to compress observed user behaviors into a small, stable set of runtime behavior policies for a simulated user.
The final taxonomy should help the simulator decide how a real employee user reacts, what information may be released, and what must remain hidden.
Return only valid JSON."""

BEHAVIOR_TAXONOMY_USER = """Historical dialogues:
{dialogues_json}
We are building a user simulator, not an open-ended behavior ontology.
Compress the observed user behaviors into exactly 4 to 6 high-level runtime policies.

Assistant acts that may trigger user behavior:
- clarification_question
- action_request
- solution_output
- generic_advice
- offtrack_question

Preferred canonical policies:
1. 陈述或继续澄清问题
2. 回答客服并释放信息
3. 询问具体操作办法
4. 尝试操作并反馈结果
5. 方向不符时纠正或拉回问题
6. 确认解决或继续求助

You may rename the policies if needed, but do not create more than 6.
Merge fine-grained behaviors when they serve the same simulator decision.

Mandatory merge guidance:
- answer_fact / reveal_new_fact / provide_partial_info -> 回答客服并释放信息
- repeat_surface_problem / restate_issue / clarify_problem -> 陈述或继续澄清问题
- ask_how_to_perform / ask_for_steps / ask_for_guidance -> 询问具体操作办法
- attempt_action / report_action_result -> 尝试操作并反馈结果
- deny_or_correct / reject_wrong_assumption / redirect -> 方向不符时纠正或拉回问题
- accept_solution / reject_solution / ask_next_step -> 确认解决或继续求助
- ignore_or_silence should not be a default policy unless strongly supported; usually merge it into vague/cooperation sensitivity.

For each runtime policy, output:
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
  "simulator_policy_hint": "how this behavior should be implemented in the simulator",
  "decision_rules": [
    "observable condition -> preferred user action"
  ],
  "prohibited_behaviors": [
    "behavior that would be unrealistic under this policy"
  ],
  "state_transitions": {{
    "condition": "state fields that should change"
  }}
}}

The simulator_policy_hint must explicitly mention information boundaries:
- user-facing information may be volunteered when stating the problem.
- diagnostic information may be released only when the assistant asks a relevant question.
- solution information must not be volunteered by the user.
- external/confusing information should only be used to correct or redirect off-track assistant behavior.

The decision rules must make these distinctions explicit:
- relevant clarification versus repeated/unknown clarification;
- vague advice versus a concrete executable action;
- accepting an actionable target solution versus reporting failure for a non-target action;
- immediately accepting a target solution versus executing a non-target diagnostic action and using the resulting world-model feedback in the next decision;
- impatience in wording versus actual escalation;
- continuing troubleshooting versus escalation/termination.
- Escalation must be evidence-driven: use it only when the assistant explicitly cannot continue, confirms a handoff, or repeated no-progress turns have exhausted user-provided information. Never infer escalation solely from an impatient persona.
- Cooperation means willingness to provide known information and try clear steps. It does not mean inventing facts, accepting vague advice, or claiming success without a target solution match.
- Any solution_match=target response should be accepted immediately, even if the solution contains actions; target solutions do not enter pending execution verification.
- For non-target diagnostic actions, a simple action is directly executable, low-risk, and needs no missing path, parameter, permission, or prerequisite. A complex action is multi-step, unfamiliar, risky, permission-dependent, or underspecified.
- Complex diagnostic actions should trigger a how-to question. Simple diagnostic actions should store action-observable feedback, then the next turn should consider that feedback before ordinary new facts while still combining it with the latest assistant reply, persona, and information boundaries. Do not force a fixed report_action_result if another action is more appropriate.

Return JSON:
{{
  "behavior_taxonomy": [...]
}}
Requirements:
- Use the historical dialogues as evidence.
- Return exactly 4 to 6 behavior policies.
- Do not output fine-grained labels such as answer_fact, reveal_new_fact, provide_partial_info, or report_action_result as separate behavior categories.
- Put fine-grained labels only inside typical_user_response_patterns or simulator_policy_hint if they are useful.
- Avoid near-duplicate categories.
- Focus on policies useful for runtime user simulation, not generic dialogue-act taxonomy.
- Every policy must contain at least two decision_rules and one prohibited_behaviors item.
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
