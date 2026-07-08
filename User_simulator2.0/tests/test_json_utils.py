from src.utils.json_utils import extract_json_object


def test_extract_json_object_uses_first_valid_object_when_llm_adds_extra_text():
    payload = extract_json_object('{"roadmap": {"case_id": "KT001"}}\n说明：上面是结果 {"extra": true}')

    assert payload == {"roadmap": {"case_id": "KT001"}}


def test_extract_json_object_ignores_text_before_json():
    payload = extract_json_object("好的，JSON如下：\n```json\n{\"ok\": true}\n```")

    assert payload == {"ok": True}
