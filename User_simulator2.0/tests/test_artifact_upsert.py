from main import upsert_jsonl_by_key
from src.utils.jsonl import read_jsonl


def test_upsert_jsonl_by_key_preserves_old_records_and_replaces_matching_key(tmp_path):
    path = tmp_path / "artifacts.jsonl"
    first_total = upsert_jsonl_by_key(
        path,
        [
            {"case_id": "CASE_001", "value": "old"},
            {"case_id": "CASE_002", "value": "keep"},
        ],
        "case_id",
    )
    second_total = upsert_jsonl_by_key(
        path,
        [
            {"case_id": "CASE_001", "value": "new"},
            {"case_id": "CASE_003", "value": "add"},
        ],
        "case_id",
    )

    records = {record["case_id"]: record for record in read_jsonl(path)}
    assert first_total == 2
    assert second_total == 3
    assert records["CASE_001"]["value"] == "new"
    assert records["CASE_002"]["value"] == "keep"
    assert records["CASE_003"]["value"] == "add"
