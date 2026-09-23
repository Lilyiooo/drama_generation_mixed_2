#!/usr/bin/env python3
"""Run the strict all-history baseline paired to the 12 PG-19 candidate stories."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from tools import upstream_matched_history_baseline as core


DATASET = Path(os.environ.get(
    "PG19_SELECTED12_DATASET",
    SCRIPT_ROOT / "results/pg19_selected12/shared_inputs/pipeline_inputs_zh.jsonl",
))
CANDIDATE_ROOT = SCRIPT_ROOT / "output/pg19_selected12_state_hybrid_gate_v1"
BASELINE_ROOT = SCRIPT_ROOT / "output/pg19_selected12_matched_history_baseline_v1"
BUNDLED_ROOT = SCRIPT_ROOT / "results/pg19_selected12"
SAMPLE_ROWS = tuple(
    json.loads(line)
    for line in DATASET.read_text(encoding="utf-8").splitlines()
    if line.strip()
)
SAMPLES = tuple(row["sample_id"] for row in SAMPLE_ROWS)
SAMPLE_BY_ID = {row["sample_id"]: row for row in SAMPLE_ROWS}
PAIRING_MANIFEST = BASELINE_ROOT / "pg19_pairing.json"


def stable_seed(sample_id: str) -> int:
    digest = hashlib.sha256(sample_id.encode("utf-8")).hexdigest()
    return 700000 + int(digest[:8], 16) % 200000


core.ROOT = BASELINE_ROOT
core.RUNS = SAMPLES
core.RUN_SEEDS = {sample_id: stable_seed(sample_id) for sample_id in SAMPLES}
core.PROMPT_VERSION = "pg19-selected12-matched-outline-direct-all-history-v1"
core.source_run_dir = lambda sample_id: CANDIDATE_ROOT / sample_id / "candidate"
core.source_asset_path = lambda sample_id: core.source_run_dir(sample_id) / "generation_assets.json"
core.frozen_asset_path = lambda sample_id: BASELINE_ROOT / "frozen_sources" / sample_id / "generation_assets.json"

_core_prepare = core.prepare
_core_require_prepared = core.require_prepared


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairing_manifest() -> dict:
    candidate_protocol = CANDIDATE_ROOT / "protocol.json"
    if not candidate_protocol.is_file():
        candidate_protocol = BUNDLED_ROOT / "protocols/our_method_protocol.json"
    if not candidate_protocol.is_file():
        raise FileNotFoundError(f"Missing candidate protocol: {candidate_protocol}")
    protocol = core.read_json(candidate_protocol)
    protocol_samples = {row["sample_id"]: row for row in protocol.get("samples", [])}
    if set(protocol_samples) != set(SAMPLES):
        raise ValueError("Candidate protocol samples do not match the selected PG19 dataset")
    samples = []
    for row in SAMPLE_ROWS:
        sample_id = row["sample_id"]
        source = core.source_asset_path(sample_id)
        if not source.is_file():
            source = BUNDLED_ROOT / "shared_inputs" / sample_id / "generation_assets.json"
        candidate = protocol_samples[sample_id]
        if not source.is_file():
            raise FileNotFoundError(f"Missing candidate generation assets: {source}")
        input_path = Path(candidate["input"])
        if not input_path.is_file():
            input_path = BUNDLED_ROOT / "shared_inputs" / sample_id / "input.json"
        if not input_path.is_file() or core.canonical_sha(core.read_json(input_path)) != candidate["input_sha256"]:
            raise ValueError(f"Frozen candidate input changed: {input_path}")
        samples.append({
            "sample_id": sample_id,
            "length_group": row["length_group"],
            "cluster_id": row["cluster_id"],
            "topic": row["topic"],
            "candidate_input": str(input_path),
            "candidate_input_sha256": candidate["input_sha256"],
            "generation_assets": str(source),
            "generation_assets_sha256": file_sha256(source),
        })
    return {
        "comparison": "paired by sample_id; identical world, roles, story outline and episode outlines",
        "dataset": str(DATASET),
        "dataset_sha256": file_sha256(DATASET),
        "candidate_root": str(CANDIDATE_ROOT),
        "candidate_protocol": str(candidate_protocol),
        "candidate_protocol_sha256": file_sha256(candidate_protocol),
        "baseline_root": str(BASELINE_ROOT),
        "samples": samples,
    }


def prepare() -> None:
    _core_prepare()
    expected = pairing_manifest()
    if PAIRING_MANIFEST.is_file() and core.read_json(PAIRING_MANIFEST) != expected:
        raise ValueError(f"PG19 pairing changed; use a new experiment root: {PAIRING_MANIFEST}")
    core.atomic_json(PAIRING_MANIFEST, expected)
    print(f"paired_samples={len(SAMPLES)} pairing={PAIRING_MANIFEST}")


def require_prepared(sample_id: str):
    result = _core_require_prepared(sample_id)
    if not PAIRING_MANIFEST.is_file() or core.read_json(PAIRING_MANIFEST) != pairing_manifest():
        raise ValueError("PG19 pairing manifest is missing or changed")
    return result


def summary(values: list[float]) -> dict:
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "sample_std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def paired_summary(deltas: list[float]) -> dict:
    result = summary(deltas)
    count = len(deltas)
    standard_error = result["sample_std"] / math.sqrt(count) if count else 0.0
    t_critical_95 = {
        2: 12.706205,
        3: 4.302653,
        4: 3.182446,
        5: 2.776445,
        6: 2.570582,
        7: 2.446912,
        8: 2.364624,
        9: 2.306004,
        10: 2.262157,
        11: 2.228139,
        12: 2.200985,
    }.get(count, 1.96)
    margin = t_critical_95 * standard_error
    wins = sum(value > 0 for value in deltas)
    losses = sum(value < 0 for value in deltas)
    non_ties = wins + losses
    tail = min(wins, losses)
    sign_test_p = (
        min(1.0, 2 * sum(math.comb(non_ties, index) for index in range(tail + 1)) / (2 ** non_ties))
        if non_ties else 1.0
    )
    result.update({
        "standard_error": standard_error,
        "mean_95_percent_ci": [result["mean"] - margin, result["mean"] + margin],
        "candidate_wins": wins,
        "ties": sum(value == 0 for value in deltas),
        "baseline_wins": losses,
        "two_sided_exact_sign_test_p": sign_test_p,
    })
    return result


def write_report() -> None:
    manifest = core.read_json(PAIRING_MANIFEST)
    metadata = {row["sample_id"]: row for row in manifest["samples"]}
    rows = []
    for sample_id in SAMPLES:
        baseline_path = BASELINE_ROOT / sample_id / "drama_evaluations_logic_quality_qwen38_v24/full_60_episodes/scores.json"
        candidate_path = core.source_run_dir(sample_id) / "drama_evaluations_logic_quality_qwen38_v24/full_60_episodes/scores.json"
        if not baseline_path.is_file():
            raise ValueError(f"Missing baseline scores: {baseline_path}")
        if not candidate_path.is_file():
            raise ValueError(f"Missing paired candidate scores: {candidate_path}")
        baseline_payload = core.read_json(baseline_path)
        candidate_payload = core.read_json(candidate_path)
        if baseline_payload.get("evaluation_mode") != candidate_payload.get("evaluation_mode"):
            raise ValueError(f"Evaluation mode mismatch for {sample_id}")
        baseline_logic, baseline_quality = core.score_pair(baseline_path)
        candidate_logic, candidate_quality = core.score_pair(candidate_path)
        rows.append({
            **{key: metadata[sample_id][key] for key in ("sample_id", "length_group", "cluster_id", "topic")},
            "baseline": {"logic": baseline_logic, "quality": baseline_quality},
            "candidate": {"logic": candidate_logic, "quality": candidate_quality},
            "candidate_minus_baseline": {
                "logic": round(candidate_logic - baseline_logic, 4),
                "quality": round(candidate_quality - baseline_quality, 4),
            },
            "baseline_score_file": str(baseline_path),
            "candidate_score_file": str(candidate_path),
        })

    def metric(method: str, name: str) -> list[float]:
        return [row[method][name] for row in rows]

    def deltas(name: str) -> list[float]:
        return [row["candidate_minus_baseline"][name] for row in rows]

    by_length_group = {}
    for group in sorted({row["length_group"] for row in rows}):
        selected = [row for row in rows if row["length_group"] == group]
        by_length_group[group] = {
            "count": len(selected),
            "baseline": {
                name: summary([row["baseline"][name] for row in selected])
                for name in ("logic", "quality")
            },
            "candidate": {
                name: summary([row["candidate"][name] for row in selected])
                for name in ("logic", "quality")
            },
            "candidate_minus_baseline": {
                name: paired_summary([row["candidate_minus_baseline"][name] for row in selected])
                for name in ("logic", "quality")
            },
        }

    report = {
        "experiment": str(BASELINE_ROOT),
        "generated_at": core.utc_now(),
        "comparison": "PG19 candidate structured-state hybrid gate minus matched direct-outline all-history baseline",
        "pairing": manifest,
        "baseline_protocol": core.read_json(BASELINE_ROOT / "protocol.json"),
        "samples": rows,
        "overall": {
            "baseline": {name: summary(metric("baseline", name)) for name in ("logic", "quality")},
            "candidate": {name: summary(metric("candidate", name)) for name in ("logic", "quality")},
            "candidate_minus_baseline": {name: paired_summary(deltas(name)) for name in ("logic", "quality")},
        },
        "by_length_group": by_length_group,
    }
    target = BASELINE_ROOT / "reports/pg19_candidate_vs_matched_history_baseline_v24.json"
    core.atomic_json(target, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report={target}")


core.prepare = prepare
core.require_prepared = require_prepared
core.write_report = write_report


def selected_samples(values: list[str] | None) -> list[str]:
    selected = values or list(SAMPLES)
    invalid = sorted(set(selected) - set(SAMPLES))
    if invalid:
        raise ValueError(f"Invalid sample IDs: {invalid}")
    return list(dict.fromkeys(selected))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("prepare")
    subparsers.add_parser("status")
    subparsers.add_parser("report")
    for action in ("generate", "evaluate"):
        child = subparsers.add_parser(action)
        child.add_argument("--sample", action="append", choices=SAMPLES)
        child.add_argument("--workers", type=int, default=0, help="0 means all selected stories concurrently")
        child.add_argument("--execute-api", action="store_true")
        if action == "generate":
            child.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "status":
        core.show_status()
    elif args.action == "report":
        write_report()
    else:
        samples = selected_samples(args.sample)
        workers = args.workers or len(samples)
        if workers < 1:
            parser.error("--workers must be positive or zero")
        if args.action == "generate":
            if args.limit is not None and args.limit < 1:
                parser.error("--limit must be positive")
            core.run_generation(samples, workers, args.limit, args.execute_api)
        else:
            core.run_evaluation(samples, workers, args.execute_api)


if __name__ == "__main__":
    main()
