from src.transcript_exporter import TranscriptExporter, build_transcript
from src.utils.jsonl import append_jsonl


def test_build_transcript_reconstructs_readable_dialogue():
    logs = [
        {
            "case_id": "KT001",
            "input": {
                "history_before_reply": [
                    {"role": "user", "content": "Excel打不开"},
                    {"role": "assistant", "content": "是所有文件都打不开吗？"},
                ]
            },
            "output": {
                "turn": 1,
                "user_reply": "是的，所有Excel都打不开。",
                "state": {"solution_status": "ongoing"},
            },
        },
        {
            "case_id": "KT001",
            "input": {
                "history_before_reply": [
                    {"role": "user", "content": "Excel打不开"},
                    {"role": "assistant", "content": "是所有文件都打不开吗？"},
                    {"role": "user", "content": "是的，所有Excel都打不开。"},
                    {"role": "assistant", "content": "请看任务管理器里有没有EXCEL.EXE。"},
                ]
            },
            "output": {
                "turn": 2,
                "user_reply": "有，像是卡住了。",
                "state": {"solution_status": "ongoing"},
            },
        },
    ]

    transcript = build_transcript("KT001", logs)

    assert [message["role"] for message in transcript["messages"]] == ["user", "assistant", "user", "assistant", "user"]
    assert transcript["messages"][-1]["content"] == "有，像是卡住了。"


def test_transcript_exporter_writes_markdown_and_json(tmp_path):
    output_dir = tmp_path / "outputs"
    append_jsonl(
        output_dir / "simulation_logs.jsonl",
        {
            "case_id": "KT001",
            "module": "Simulator.step",
            "input": {
                "history_before_reply": [
                    {"role": "user", "content": "Excel打不开"},
                    {"role": "assistant", "content": "是所有文件都打不开吗？"},
                ]
            },
            "output": {
                "turn": 1,
                "user_reply": "是的。",
                "state": {"solution_status": "solution_accepted", "stop_reason": "accepted_actionable_solution"},
            },
        },
    )

    paths = TranscriptExporter(output_dir).export_case("KT001")

    assert len(paths) == 2
    md_text = (output_dir / "transcripts" / "KT001.md").read_text(encoding="utf-8")
    assert "**User:** Excel打不开" in md_text
    assert "**Assistant:** 是所有文件都打不开吗？" in md_text
    assert "**User:** 是的。" in md_text


def test_transcript_exporter_writes_combined_markdown_and_json(tmp_path):
    output_dir = tmp_path / "outputs"
    for case_id, timestamp, user_reply in [
        ("KT001", "2026-01-01T00:00:01Z", "是的。"),
        ("KT002", "2026-01-01T00:00:02Z", "我找不到这个入口。"),
    ]:
        append_jsonl(
            output_dir / "simulation_logs.jsonl",
            {
                "case_id": case_id,
                "module": "Simulator.step",
                "input": {
                    "history_before_reply": [
                        {"role": "user", "content": f"{case_id} 有问题"},
                        {"role": "assistant", "content": "请确认一下。"},
                    ]
                },
                "output": {
                    "turn": 1,
                    "user_reply": user_reply,
                    "state": {"solution_status": "not_solved", "stop_reason": ""},
                },
                "timestamp": timestamp,
            },
        )

    paths = TranscriptExporter(output_dir).export_combined()

    assert len(paths) == 2
    md_text = (output_dir / "transcripts" / "all_simulation_transcripts.md").read_text(encoding="utf-8")
    assert "# All Simulation Transcripts" in md_text
    assert "## KT001#1" in md_text
    assert "## KT002#1" in md_text
    assert "**User:** KT001 有问题" in md_text
    json_text = (output_dir / "transcripts" / "all_simulation_transcripts.json").read_text(encoding="utf-8")
    assert '"session_id": "KT001#1"' in json_text


def test_combined_transcripts_split_repeated_case_sessions(tmp_path):
    output_dir = tmp_path / "outputs"
    for timestamp, user_opening, user_reply in [
        ("2026-01-01T00:00:01Z", "第一次打开失败", "还是不行。"),
        ("2026-01-01T00:01:01Z", "第二次打开失败", "可以了。"),
    ]:
        append_jsonl(
            output_dir / "simulation_logs.jsonl",
            {
                "case_id": "KT001",
                "module": "Simulator.step",
                "input": {
                    "history_before_reply": [
                        {"role": "user", "content": user_opening},
                        {"role": "assistant", "content": "请试一下。"},
                    ]
                },
                "output": {
                    "turn": 1,
                    "user_reply": user_reply,
                    "state": {"solution_status": "not_solved", "stop_reason": ""},
                },
                "timestamp": timestamp,
            },
        )

    transcripts = TranscriptExporter(output_dir).build_all_transcripts()

    assert [item["session_id"] for item in transcripts] == ["KT001#1", "KT001#2"]
    assert transcripts[0]["messages"][0]["content"] == "第一次打开失败"
    assert transcripts[1]["messages"][0]["content"] == "第二次打开失败"
