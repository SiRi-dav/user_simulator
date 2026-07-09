from src.behavior_mining.prompt_templates import BEHAVIOR_TAXONOMY_USER


def test_behavior_taxonomy_prompt_requires_compact_runtime_policies():
    assert "exactly 4 to 6 high-level runtime policies" in BEHAVIOR_TAXONOMY_USER
    assert "Mandatory merge guidance" in BEHAVIOR_TAXONOMY_USER
    assert "Do not output fine-grained labels" in BEHAVIOR_TAXONOMY_USER
    assert "solution information must not be volunteered" in BEHAVIOR_TAXONOMY_USER
    assert '"decision_rules"' in BEHAVIOR_TAXONOMY_USER
    assert '"prohibited_behaviors"' in BEHAVIOR_TAXONOMY_USER
    assert '"state_transitions"' in BEHAVIOR_TAXONOMY_USER
    assert "Never infer escalation solely from an impatient persona" in BEHAVIOR_TAXONOMY_USER
    assert "Cooperation means willingness" in BEHAVIOR_TAXONOMY_USER
    assert "target solutions do not enter pending execution verification" in BEHAVIOR_TAXONOMY_USER
    assert "action-observable diagnostic facts" in BEHAVIOR_TAXONOMY_USER
