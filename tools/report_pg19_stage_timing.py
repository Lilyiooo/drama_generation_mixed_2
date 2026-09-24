#!/usr/bin/env python3
"""Summarize gate and post-gate script-writing time for a PG19 study."""

import argparse
from datetime import datetime
import json
from pathlib import Path


def summarize(root):
    rows = []
    for sample in sorted(root.iterdir()):
        if not (sample / "candidate/stage_timing").is_dir():
            continue
        attempts = []
        for path in sorted((sample / "candidate/stage_timing").glob("E*/*.json")):
            attempt = json.loads(path.read_text(encoding="utf-8"))
            attempts.append(attempt)
        gate_seconds = sum(
            attempt["stages"]["gate"]["seconds"] for attempt in attempts
            if attempt["stages"].get("gate", {}).get("status") == "complete"
        )
        script_seconds = sum(
            attempt["stages"]["script"]["seconds"] for attempt in attempts
            if attempt["stages"].get("script", {}).get("status") == "complete"
        )
        completed = {
            attempt["episode_number"] for attempt in attempts
            if attempt["stages"].get("script", {}).get("status") == "complete"
        }
        unfinished = sum(
            any(stage.get("status") != "complete" for stage in attempt["stages"].values())
            for attempt in attempts
        )
        rows.append({
            "sample_id": sample.name,
            "attempts": len(attempts),
            "episodes_with_saved_script": len(completed),
            "unfinished_attempts": unfinished,
            "gate_seconds": round(gate_seconds, 2),
            "script_seconds": round(script_seconds, 2),
        })
    starts = [
        datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["attempt_started_at"])
        for path in root.glob("*/candidate/stage_timing/E*/*.json")
    ]
    ends = [
        datetime.fromisoformat(stage["finished_at"])
        for path in root.glob("*/candidate/stage_timing/E*/*.json")
        for stage in json.loads(path.read_text(encoding="utf-8"))["stages"].values()
        if stage.get("status") == "complete"
    ]
    return {
        "scope": "gate.apply and post-gate script writing through script save; excludes scene-outline generation, planning, and memory update",
        "sum_of_per_attempt_wall_seconds_not_parallel_elapsed": {
            "gate": round(sum(row["gate_seconds"] for row in rows), 2),
            "script": round(sum(row["script_seconds"] for row in rows), 2),
        },
        "parallel_wall_seconds_first_attempt_to_last_completed_stage": (
            round((max(ends) - min(starts)).total_seconds(), 2) if starts and ends else None
        ),
        "samples": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    report = summarize(args.root)
    target = args.root / "reports/stage_timing.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report={target}")


if __name__ == "__main__":
    main()
