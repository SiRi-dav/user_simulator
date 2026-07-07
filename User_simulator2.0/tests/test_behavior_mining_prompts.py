from src.behavior_mining.prompt_templates import BEHAVIOR_TAXONOMY_USER


def test_behavior_taxonomy_prompt_requires_compact_runtime_policies():
    assert "exactly 4 to 6 high-level runtime policies" in BEHAVIOR_TAXONOMY_USER
    assert "Mandatory merge guidance" in BEHAVIOR_TAXONOMY_USER
    assert "Do not output fine-grained labels" in BEHAVIOR_TAXONOMY_USER
    assert "solution information must not be volunteered" in BEHAVIOR_TAXONOMY_USER
