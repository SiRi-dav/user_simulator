from src.runtime.prompt_templates import BLIND_USER_REPLY_USER, INITIAL_USER_USER, KNOWLEDGE_DECISION_USER


def test_runtime_prompts_prioritize_answering_latest_question_naturally():
    assert "allowed_content must answer the assistant's latest question first" in KNOWLEDGE_DECISION_USER
    assert "For A/B or category questions" in KNOWLEDGE_DECISION_USER
    assert "Answer the assistant's latest question first" in BLIND_USER_REPLY_USER
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
