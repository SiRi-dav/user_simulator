from src.runtime.prompt_templates import BLIND_USER_ACTION_USER, INITIAL_USER_USER, KNOWLEDGE_ASSESSMENT_USER


def test_runtime_prompts_prioritize_answering_latest_question_naturally():
    assert "identify the focus of the assistant's latest question" in KNOWLEDGE_ASSESSMENT_USER
    assert "allowed_facts should address that focus" in KNOWLEDGE_ASSESSMENT_USER
    assert "Answer the assistant's latest question first" in BLIND_USER_ACTION_USER
    assert "answer one natural part that matches allowed_facts" in BLIND_USER_ACTION_USER
    assert "Do not simply repeat the previous user message" in BLIND_USER_ACTION_USER


def test_runtime_prompts_forbid_case_library_artifacts_in_user_reply():
    assert "no square-bracket labels" in KNOWLEDGE_ASSESSMENT_USER
    assert "no parenthetical document/category suffixes" in KNOWLEDGE_ASSESSMENT_USER
    assert "no square brackets like" in BLIND_USER_ACTION_USER
    assert "rewrite \"电路图（原理图）\"" in BLIND_USER_ACTION_USER


def test_initial_user_prompt_requires_short_symptom_opening():
    assert "Start with the visible symptom or failed operation" in INITIAL_USER_USER
    assert "Usually write one short sentence" in INITIAL_USER_USER
    assert "帮忙看下" in INITIAL_USER_USER
    assert "严重影响我的工作" in INITIAL_USER_USER
    assert "安排专家介入" in INITIAL_USER_USER
    assert "Do not over-explain background" in INITIAL_USER_USER


def test_runtime_prompt_allows_stop_when_actionable_solution_is_accepted():
    assert "solution_match" in KNOWLEDGE_ASSESSMENT_USER
    assert "target" in KNOWLEDGE_ASSESSMENT_USER
    assert "accept_actionable_solution_and_stop" in BLIND_USER_ACTION_USER
    assert "solution_accepted" in BLIND_USER_ACTION_USER
    assert "accepted_actionable_solution" in BLIND_USER_ACTION_USER


def test_runtime_prompt_allows_stop_when_assistant_cannot_solve():
    assert "no_more_user_info" in KNOWLEDGE_ASSESSMENT_USER
    assert "progress_status=\"no_more_user_info\"" in KNOWLEDGE_ASSESSMENT_USER
    assert "stop_no_effective_solution" in BLIND_USER_ACTION_USER
    assert "assistant_unable_to_provide_effective_solution" in BLIND_USER_ACTION_USER
    assert "selected behavior policy's escalation/termination conditions" in BLIND_USER_ACTION_USER


def test_runtime_prompt_accepts_semantically_sufficient_core_solution():
    assert "semantic sufficiency from a real user's perspective" in KNOWLEDGE_ASSESSMENT_USER
    assert "Optional checks, fallback branches" in KNOWLEDGE_ASSESSMENT_USER
    assert "does not cover every solution point" in KNOWLEDGE_ASSESSMENT_USER
    assert 'For solution_match="partial"' in BLIND_USER_ACTION_USER


def test_runtime_prompt_prevents_premature_user_escalation():
    assert "single behavior policy" in BLIND_USER_ACTION_USER
    assert "not itself an automatic escalation action" in BLIND_USER_ACTION_USER
    assert "Do not invent identifiers" in BLIND_USER_ACTION_USER


def test_runtime_prompt_requires_action_result_feedback_after_trying_operation():
    assert "report_action_result" in BLIND_USER_ACTION_USER
    assert "pending_action_result" in BLIND_USER_ACTION_USER
    assert "distinguish simple from complex execution" in BLIND_USER_ACTION_USER
    assert "pending_action_solution_match" in BLIND_USER_ACTION_USER
    assert "pending_action_result_facts" in BLIND_USER_ACTION_USER
    assert 'If solution_match="target"' in BLIND_USER_ACTION_USER
    assert "immediately even when the solution contains actions" in BLIND_USER_ACTION_USER
    assert "report pending_action_result_facts" in BLIND_USER_ACTION_USER
    assert "do not repeat \"I'll try it\"" in BLIND_USER_ACTION_USER
    assert "state transition after reporting" in BLIND_USER_ACTION_USER
