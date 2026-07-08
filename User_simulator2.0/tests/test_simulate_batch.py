import argparse

from main import load_completed_batch_case_ids, select_batch_case_ids, update_batch_status


class ParserStub:
    def error(self, message):
        raise ValueError(message)


def test_select_batch_case_ids_from_all_with_offset_and_limit():
    args = argparse.Namespace(case_ids=None, all=True, offset=1, limit=2)
    selected = select_batch_case_ids(args, {"C": object(), "A": object(), "B": object()}, ParserStub())

    assert selected == ["B", "C"]


def test_select_batch_case_ids_from_explicit_ids():
    args = argparse.Namespace(case_ids=["KT002", "KT001"], all=False, offset=0, limit=0)
    selected = select_batch_case_ids(args, {}, ParserStub())

    assert selected == ["KT002", "KT001"]


def test_batch_status_upsert_tracks_completed_cases(tmp_path):
    path = tmp_path / "simulate_batch_status.jsonl"

    update_batch_status(path, "KT001", "running", {"turn_count": 0})
    update_batch_status(path, "KT001", "completed", {"turn_count": 3})
    update_batch_status(path, "KT002", "failed", {"error": "timeout"})

    assert load_completed_batch_case_ids(path) == {"KT001"}
