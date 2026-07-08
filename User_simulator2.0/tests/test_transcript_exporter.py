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
