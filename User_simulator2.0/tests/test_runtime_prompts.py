from src.runtime.prompt_templates import BLIND_USER_REPLY_USER, INITIAL_USER_USER, KNOWLEDGE_DECISION_USER


def test_runtime_prompts_prioritize_answering_latest_question_naturally():
    assert "allowed_content must answer the assistant's latest question first" in KNOWLEDGE_DECISION_USER
    assert "For A/B or category questions" in KNOWLEDGE_DECISION_USER
    assert "identify the focus of the assistant's latest question" in KNOWLEDGE_DECISION_USER
    assert "answer one natural part at a time" in KNOWLEDGE_DECISION_USER
    assert "Answer the assistant's latest question first" in BLIND_USER_REPLY_USER
    assert "answer one natural part that matches allowed_content" in BLIND_USER_REPLY_USER
    assert "Do not simply repeat the previous user message" in BLIND_USER_REPLY_USER


def test_runtime_prompts_forbid_case_library_artifacts_in_user_reply():
    assert "no square-bracket labels" in KNOWLEDGE_DECISION_USER
    assert "no parenthetical document/category suffixes" in KNOWLEDGE_DECISION_USER
    assert "no square brackets like" in BLIND_USER_REPLY_USER
    assert "rewrite \"电路图（原理图）\"" in BLIND_USER_REPLY_USER


def test_initial_user_prompt_requires_short_symptom_opening():
    assert "Start with the visible symptom or failed operation" in INITIAL_USER_USER
    assert "Usually write one short sentence" in INITIAL_USER_USER
    assert "帮忙看下" in INITIAL_USER_USER
    assert "严重影响我的工作" in INITIAL_USER_USER
    assert "安排专家介入" in INITIAL_USER_USER
    assert "Do not over-explain background" in INITIAL_USER_USER


def test_runtime_prompt_allows_stop_when_actionable_solution_is_accepted():
    assert "accept_actionable_solution_and_stop" in KNOWLEDGE_DECISION_USER
    assert "solution_accepted" in KNOWLEDGE_DECISION_USER
    assert "accepted_actionable_solution" in KNOWLEDGE_DECISION_USER
    assert "does not generate unsolicited follow-up" in KNOWLEDGE_DECISION_USER
    assert "matches target solution_points" in KNOWLEDGE_DECISION_USER
    assert "do not say you will come back later with results" in BLIND_USER_REPLY_USER


def test_runtime_prompt_allows_stop_when_assistant_cannot_solve():
    assert "assistant_unable_to_solve_stop" in KNOWLEDGE_DECISION_USER
    assert "assistant_unable_to_provide_effective_solution" in KNOWLEDGE_DECISION_USER
    assert "Do not pretend the problem is solved" in KNOWLEDGE_DECISION_USER
    assert "could not provide an effective solution" in BLIND_USER_REPLY_USER
