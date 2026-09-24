"""Persist per-attempt wall-clock timings without changing generation behavior."""

from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from drama_local.runtime import atomic_json


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class StageTiming:
    def __init__(self, output_root, episode_number):
        self.path = (
            Path(output_root) / "stage_timing" / f"E{episode_number:03d}"
            / f"{uuid4().hex}.json"
        )
        self.data = {
            "episode_number": episode_number,
            "attempt_started_at": utc_now(),
            "stages": {},
        }
        self.started = {}

    def start(self, stage):
        self.started[stage] = time.perf_counter()
        self.data["stages"][stage] = {"started_at": utc_now(), "status": "running"}
        atomic_json(self.path, self.data)

    def finish(self, stage):
        elapsed = time.perf_counter() - self.started.pop(stage)
        self.data["stages"][stage].update(
            {"finished_at": utc_now(), "seconds": elapsed, "status": "complete"}
        )
        atomic_json(self.path, self.data)
