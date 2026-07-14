from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.review_exporter import safe_filename
from src.utils.jsonl import read_jsonl


class TranscriptExporter:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.transcript_dir = output_dir / "transcripts"

    def export_case(self, case_id: str) -> list[Path]:
        logs = [record for record in read_simulation_logs(self.output_dir / "simulation_logs.jsonl") if record["case_id"] == case_id]
        if not logs:
            raise ValueError(f"case_id not found in simulation_logs.jsonl: {case_id}")
        transcript = build_transcript(case_id, logs)
        return self.write_transcript(transcript)

    def export_cases(self, case_ids: Iterable[str] | None = None) -> list[Path]:
        logs_by_case: dict[str, list[Dict[str, Any]]] = {}
        selected = set(case_ids or [])
        for record in read_simulation_logs(self.output_dir / "simulation_logs.jsonl"):
            case_id = record["case_id"]
            if selected and case_id not in selected:
                continue
            logs_by_case.setdefault(case_id, []).append(record)
        if selected:
            missing = sorted(selected - set(logs_by_case))
            if missing:
                raise ValueError(f"case_id not found in simulation_logs.jsonl: {', '.join(missing)}")
        paths: list[Path] = []
        for case_id in sorted(logs_by_case):
            paths.extend(self.write_transcript(build_transcript(case_id, logs_by_case[case_id])))
        return paths

    def export_combined(self, case_ids: Iterable[str] | None = None, stem: str = "all_simulation_transcripts") -> list[Path]:
        transcripts = self.build_all_transcripts(case_ids)
        if not transcripts:
            raise ValueError("No simulation logs found for selected cases.")
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        safe_stem = safe_filename(stem or "all_simulation_transcripts")
        md_path = self.transcript_dir / f"{safe_stem}.md"
        json_path = self.transcript_dir / f"{safe_stem}.json"
        md_path.write_text(render_combined_transcript_markdown(transcripts), encoding="utf-8")
        json_path.write_text(json.dumps(transcripts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return [md_path, json_path]

    def build_all_transcripts(self, case_ids: Iterable[str] | None = None) -> list[Dict[str, Any]]:
        selected = set(case_ids or [])
        logs_by_case: dict[str, list[Dict[str, Any]]] = {}
        for record in read_simulation_logs(self.output_dir / "simulation_logs.jsonl"):
            case_id = record["case_id"]
            if selected and case_id not in selected:
                continue
            logs_by_case.setdefault(case_id, []).append(record)
        if selected:
            missing = sorted(selected - set(logs_by_case))
            if missing:
                raise ValueError(f"case_id not found in simulation_logs.jsonl: {', '.join(missing)}")
        transcripts: list[Dict[str, Any]] = []
        for case_id in sorted(logs_by_case):
            sessions = split_logs_into_sessions(logs_by_case[case_id])
            for session_index, session in enumerate(sessions, 1):
                transcript = build_transcript(case_id, session)
                transcript["session_index"] = session_index
                transcript["session_id"] = f"{case_id}#{session_index}"
                transcripts.append(transcript)
        return transcripts

    def write_transcript(self, transcript: Dict[str, Any]) -> list[Path]:
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        case_id = str(transcript["case_id"])
        stem = safe_filename(case_id)
        json_path = self.transcript_dir / f"{stem}.json"
        md_path = self.transcript_dir / f"{stem}.md"
        json_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_transcript_markdown(transcript), encoding="utf-8")
        return [md_path, json_path]


def read_simulation_logs(path: Path) -> list[Dict[str, Any]]:
    records = []
    for record in read_jsonl(path):
        if record.get("module") != "Simulator.step":
            continue
        case_id = str(record.get("case_id") or "").strip()
        if not case_id:
            continue
        records.append(record)
    records.sort(key=lambda item: (item["case_id"], int((item.get("output") or {}).get("turn") or 0), str(item.get("timestamp") or "")))
    return records


def build_transcript(case_id: str, logs: list[Dict[str, Any]]) -> Dict[str, Any]:
    sorted_logs = sorted(logs, key=lambda item: int((item.get("output") or {}).get("turn") or 0))
    messages: list[Dict[str, Any]] = []
    for record in sorted_logs:
        output = record.get("output") or {}
        turn = int(output.get("turn") or 0)
        history = ((record.get("input") or {}).get("history_before_reply") or [])
        history_messages = [
            {"role": str(item.get("role") or "").strip(), "content": str(item.get("content") or "").strip(), "turn": turn}
            for item in history
            if str(item.get("role") or "").strip() and str(item.get("content") or "").strip()
        ]
        if len(history_messages) > len(messages):
            messages = history_messages
        add_message(messages, "user", output.get("user_reply"), turn)
    final_output = (sorted_logs[-1].get("output") or {}) if sorted_logs else {}
    final_state = final_output.get("state") or {}
    return {
        "case_id": case_id,
        "turn_count": final_output.get("turn") or len(sorted_logs),
        "stop_reason": final_state.get("stop_reason") or final_state.get("solution_status") or "",
        "solution_status": final_state.get("solution_status") or "",
        "messages": messages,
    }


def split_logs_into_sessions(logs: list[Dict[str, Any]]) -> list[list[Dict[str, Any]]]:
    sessions: list[list[Dict[str, Any]]] = []
    current: list[Dict[str, Any]] = []
    previous_turn = 0
    ordered = sorted(enumerate(logs), key=lambda item: (str(item[1].get("timestamp") or ""), item[0]))
    for _, record in ordered:
        turn = int((record.get("output") or {}).get("turn") or 0)
        if current and (turn <= previous_turn or turn == 1):
            sessions.append(current)
            current = []
        current.append(record)
        previous_turn = turn
    if current:
        sessions.append(current)
    return sessions


def add_message(messages: list[Dict[str, Any]], role: Any, content: Any, turn: int) -> None:
    role_text = str(role or "").strip()
    content_text = str(content or "").strip()
    if not role_text or not content_text:
        return
    key = (role_text, content_text)
    if messages and (messages[-1]["role"], messages[-1]["content"]) == key:
        return
    messages.append({"role": role_text, "content": content_text, "turn": turn})


def render_transcript_markdown(transcript: Dict[str, Any]) -> str:
    lines = [
        f"# Transcript {transcript['case_id']}",
        "",
        f"- turn_count: {transcript.get('turn_count', '')}",
        f"- solution_status: {transcript.get('solution_status', '')}",
        f"- stop_reason: {transcript.get('stop_reason', '')}",
        "",
        "## Dialogue",
        "",
    ]
    for message in transcript.get("messages", []):
        role = str(message.get("role") or "").capitalize()
        content = str(message.get("content") or "")
        lines.append(f"**{role}:** {content}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_combined_transcript_markdown(transcripts: list[Dict[str, Any]]) -> str:
    lines = [
        "# All Simulation Transcripts",
        "",
        f"- session_count: {len(transcripts)}",
        "",
    ]
    for transcript in transcripts:
        session_id = transcript.get("session_id") or transcript.get("case_id")
        lines.extend(
            [
                f"## {session_id}",
                "",
                f"- case_id: {transcript.get('case_id', '')}",
                f"- session_index: {transcript.get('session_index', '')}",
                f"- turn_count: {transcript.get('turn_count', '')}",
                f"- solution_status: {transcript.get('solution_status', '')}",
                f"- stop_reason: {transcript.get('stop_reason', '')}",
                "",
            ]
        )
        for message in transcript.get("messages", []):
            role = str(message.get("role") or "").capitalize()
            content = str(message.get("content") or "")
            lines.append(f"**{role}:** {content}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
