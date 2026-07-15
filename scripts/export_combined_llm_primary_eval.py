from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_SIMULATOR2_ROOT = ROOT / "User_simulator2.0"
TARGET = USER_SIMULATOR2_ROOT / "scripts" / "export_combined_llm_primary_eval.py"

if str(USER_SIMULATOR2_ROOT) not in sys.path:
    sys.path.insert(0, str(USER_SIMULATOR2_ROOT))

runpy.run_path(str(TARGET), run_name="__main__")
