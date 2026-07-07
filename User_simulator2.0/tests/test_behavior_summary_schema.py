from src.schemas import DialogueBehaviorSummary


def test_dialogue_behavior_summary_accepts_null_turn_texts():
    summary = DialogueBehaviorSummary(
        dialogue_id="dialogue_1",
        opening_pattern="user reports a problem",
        user_persona_guess="ordinary employee",
        observed_behaviors=[
            {
                "dialogue_id": "dialogue_1",
                "turn_index": 1,
                "assistant_act": "clarify",
                "user_behavior": "answers question",
                "user_text": None,
                "assistant_text": None,
                "released_information_type": None,
                "behavior_reason": "assistant asked for details",
            }
        ],
        voluntary_information=[],
        ask_triggered_information=[],
        action_request_reactions=[],
        offtrack_reactions=[],
        solution_reactions=[],
        summary="The user cooperates with troubleshooting.",
    )

    assert summary.observed_behaviors[0].user_text == ""
    assert summary.observed_behaviors[0].assistant_text == ""
