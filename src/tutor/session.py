"""Per-session activity log for tutor modes.

A Session collects timestamped attempts as the user works through a mode,
and writes them to a JSONL file under `results/sessions/` when saved. Keep
it small on purpose: no live dashboard, just enough of a trail to compute
per-letter accuracy or session-over-session improvement later.

Each record looks like:

    {"t": 1731000000.12, "mode": "teach", "letter": "B",
     "passed": true, "score": 0.87}

Usage:

    s = Session(mode="teach")
    s.record("B", passed=True, score=0.87)
    s.save()   # writes results/sessions/YYYY-MM-DD.jsonl (appended)
"""

import json
import time
from datetime import date
from pathlib import Path

from ..config import SESSIONS_DIR as _SESSIONS_DIR

SESSIONS_DIR = Path(_SESSIONS_DIR)


class Session:
    def __init__(self, mode):
        self.mode = mode
        self.started_at = time.time()
        self.records = []

    def record(self, letter, passed, score=0.0):
        self.records.append({
            "t": time.time(),
            "mode": self.mode,
            "letter": letter,
            "passed": bool(passed),
            "score": float(score),
        })

    @property
    def attempts(self):
        return len(self.records)

    @property
    def accuracy(self):
        if not self.records:
            return 0.0
        return sum(r["passed"] for r in self.records) / len(self.records)

    def save(self, dir_path=SESSIONS_DIR):
        """Append all records to today's JSONL file. No-op if empty."""
        if not self.records:
            return None
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        out = dir_path / f"{date.today().isoformat()}.jsonl"
        with out.open("a") as fh:
            for r in self.records:
                fh.write(json.dumps(r) + "\n")
        return out
