from src.assistant.real_assistant_client import RealAssistantClient


def test_real_assistant_client_calls_pipeline_steps_in_order():
    calls = []

    def fake_post(url, payload, timeout):
        calls.append((url, payload, timeout))
        if url.endswith("/query"):
            return ["用户想修复 Excel", 0.1]
        if url.endswith("/trigger"):
            return ["预案", 0.2]
        if url.endswith("/policy"):
            return ["先确认现象", 0.3]
        if url.endswith("/response"):
            return ["请问所有 Excel 都打不开吗？", 0.4]
        raise AssertionError(url)

    client = RealAssistantClient(
        {
            "base_url": "http://assistant.test",
            "timeout": 9,
            "common_sense_cases": "无需检索案例",
        },
        post_json=fake_post,
    )

    reply = client.reply([{"role": "user", "content": "Excel打不开"}])

    assert reply == "请问所有 Excel 都打不开吗？"
    assert [url for url, _, _ in calls] == [
        "http://assistant.test/query",
        "http://assistant.test/trigger",
        "http://assistant.test/policy",
        "http://assistant.test/response",
    ]
    assert calls[1][1]["query"] == "用户想修复 Excel"
    assert calls[2][1]["cases"] == "无需检索案例"
    assert calls[3][1]["policy"] == "先确认现象"


def test_real_assistant_client_uses_no_rag_fallback_for_case_search_trigger():
    client = RealAssistantClient({"no_rag_cases": "暂无RAG"}, post_json=lambda url, payload, timeout: [])

    cases = client.build_cases([], "query", "需要检索案例")

    assert cases == "暂无RAG"
