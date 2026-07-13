from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.schemas import model_to_dict
from src.utils.jsonl import append_jsonl


class OutputLogger:
    _write_lock = threading.Lock()

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log(self, filename: str, case_id: str, module: str, input_data: Dict[str, Any], output_data: Any) -> None:
        with self._write_lock:
            append_jsonl(
                self.output_dir / filename,
                {
                    "case_id": case_id,
                    "module": module,
                    "input": model_to_dict(input_data),
                    "output": model_to_dict(output_data),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
