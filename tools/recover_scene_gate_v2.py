"""Recover Scene Gate V2 schema failures without changing semantic decisions."""

from __future__ import annotations

import argparse
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from drama_local.runtime import Context, atomic_json
from service.drama_by_creativity import scene_gate_decision as decision
from service.drama_by_creativity import scene_state_gate as base
from tools.continue_scene_gate_decision import compatible_validate
from tools.quality_preserving_scene_gate import QualityPreservingSceneGate
from tools.recover_full_scene_gate import feedback
from tools.repair_scene_gate_calibration import evidence_catalog
from tools import scene_gate_v2_study as study


VERSION = "v2_schema_feedback_v1"
DOMAIN_ALIASES = {
    "character_state": "other",
    "relationship_state": "relationship",
    "known_information": "knowledge",
    "unknown_information": "knowledge",
    "confirmed_facts": "other",
    "unresolved_threads": "other",
    "resources_and_evidence": "resource",
    "current_goals": "other",
    "timeline": "location",
}
METADATA_RULES = """元数据修复要求：
checks.scene_id必须逐字使用scene_evidence_catalog中所引S编号的scene_id，包括括号说明。
domain只能使用life/object/resource/knowledge/location/relationship/other，不得输出状态字段名。
这两项只修复元数据，不改变state_basis、scene_relation、transition、state_ids、证据或事实判断。
如果memory_conflicts中的M记录并非同一时点真正互斥，就不要声明为memory_conflicts；过时状态应依据时间证据处理。
不得为了通过校验删除真实硬冲突或伪造证据。"""


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pending_directory(root: Path, run: str) -> Path | None:
    identifier = study.identifier(run)
    gate_root = root / study.ARM / run / "scene_state_gate" / identifier
    for directory in sorted(gate_root.glob("E*")):
        if (directory / "input.json").exists() and not (directory / "outcome.json").exists():
            return directory
    return None


def reconstruct_gate(directory: Path) -> QualityPreservingSceneGate:
    frozen = base.read(directory / "input.json")
    binding = frozen["binding"]
    view = {field: [] for field in base.FIELDS}
    for item in binding["catalog"].values():
        view[item["field"]].append(item["text"])
    attempts = sorted((directory / "attempts/check_before").glob("*/*.json"))
    request = base.read(attempts[-1])["request"] if attempts else {}
    gate = QualityPreservingSceneGate(
        directory,
        binding["episode_number"],
        binding["params"],
        view,
        binding["mode"],
        base_url=request.get("base_url"),
    )
    if gate.binding != binding:
        raise ValueError(f"Cannot reconstruct frozen gate binding: {directory}")
    return gate


def normalize_raw(raw: str, scenes: list[dict], catalog: dict) -> tuple[dict, str, list[dict]]:
    value = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
    if not isinstance(value, dict):
        raise ValueError("Require a JSON object")
    normalized = copy.deepcopy(value)
    checks = normalized.get("checks")
    if not isinstance(checks, list):
        raise ValueError("checks must be a list")
    spans = evidence_catalog(scenes)
    changes = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ValueError(f"checks[{index}] must be an object")
        domain = check.get("domain")
        mapped = DOMAIN_ALIASES.get(domain, domain)
        if mapped != domain:
            changes.append({"check_index": index, "field": "domain", "before": domain, "after": mapped})
            check["domain"] = mapped
        selected = check.get("scene_span_ids")
        if not isinstance(selected, list) or not selected:
            raise ValueError(f"checks[{index}].scene_span_ids must be nonempty")
        if any(not isinstance(span, str) or span not in spans for span in selected):
            raise ValueError(f"checks[{index}] cites unknown scene evidence")
        actual = {spans[span]["scene_id"] for span in selected}
        if len(actual) != 1:
            raise ValueError(f"checks[{index}] mixes evidence from multiple scenes")
        scene_id = next(iter(actual))
        if check.get("scene_id") != scene_id:
            changes.append({
                "check_index": index,
                "field": "scene_id",
                "before": check.get("scene_id"),
                "after": scene_id,
                "scene_span_ids": selected,
            })
            check["scene_id"] = scene_id
    normalized_raw = json.dumps(normalized, ensure_ascii=False)
    result = compatible_validate(normalized_raw, scenes, catalog)
    return result, normalized_raw, changes


def failed_attempts(directory: Path) -> list[Path]:
    return sorted(
        (directory / "attempts/check_before").glob("*/*.json"),
        key=lambda path: (path.stat().st_mtime_ns, str(path)),
        reverse=True,
    )


def original_request(directory: Path) -> dict:
    attempts = failed_attempts(directory)
    if not attempts:
        raise ValueError(f"No original failed check attempts: {directory}")
    requests = [base.read(path).get("request") for path in attempts]
    first = requests[0]
    if not isinstance(first, dict) or any(value != first for value in requests):
        raise ValueError(f"Original failed attempts do not share one frozen request: {directory}")
    return first


def write_original_cache(
    directory: Path,
    request: dict,
    raw: str,
    result: dict,
    source: dict,
) -> None:
    path = directory / "check_before.json"
    payload = {
        "fingerprint": base.digest(request),
        "request": request,
        "raw": raw,
        "result": result,
    }
    if path.exists() and base.read(path) != payload:
        raise ValueError(f"Refusing to replace an existing accepted check: {path}")
    atomic_json(path, payload)
    atomic_json(directory / f"check_before_{VERSION}_source.json", {
        "version": VERSION,
        "policy": (
            "Only domain aliases and scene IDs are deterministically rebound. "
            "If another request is needed, the original invalid response and validator diagnostic are supplied; "
            "the frozen checker and strict validator still decide the accepted semantic result."
        ),
        **source,
    })


async def recover_one(root: Path, run: str, execute_api: bool) -> dict:
    directory = pending_directory(root, run)
    if directory is None:
        return {"run": run, "status": "no_pending_gate"}
    cache = directory / "check_before.json"
    if cache.exists():
        return {"run": run, "episode": directory.name, "status": "already_recovered"}
    gate = reconstruct_gate(directory)
    frozen = base.read(directory / "input.json")
    scenes = frozen["scenes"]
    request = original_request(directory)
    packet = {**gate.packet(scenes), "scene_evidence_catalog": evidence_catalog(scenes)}
    expected_user = json.dumps(packet, ensure_ascii=False)
    if (request.get("binding") != gate.binding or request.get("system") != decision.RULES
            or request.get("user") != expected_user or request.get("model") != "Qwen3.6-27B"):
        raise ValueError(f"Frozen original request does not match reconstructed gate: {directory}")

    attempts = failed_attempts(directory)
    for path in attempts:
        record = base.read(path)
        raw = record.get("raw")
        if not isinstance(raw, str):
            continue
        try:
            result, normalized_raw, changes = normalize_raw(raw, scenes, gate.catalog)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        write_original_cache(directory, request, normalized_raw, result, {
            "mode": "deterministic_metadata_normalization",
            "source_attempt": str(path),
            "source_attempt_sha256": file_hash(path),
            "normalization": changes,
        })
        return {"run": run, "episode": directory.name, "status": "recovered_without_api",
                "normalization": changes, "decision": result["status"]}

    if not execute_api:
        return {"run": run, "episode": directory.name, "status": "needs_feedback_api"}

    seed = attempts[0]
    seed_record = base.read(seed)
    seed_raw = seed_record.get("raw")
    if not isinstance(seed_raw, str):
        raise ValueError(f"Latest failed attempt has no model output: {seed}")
    try:
        normalize_raw(seed_raw, scenes, gate.catalog)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        diagnostic = feedback(seed_raw, error)
    else:
        raise AssertionError("A valid seed should have been recovered without API")
    recovery_user = expected_user + "\n" + METADATA_RULES + "\n" + diagnostic

    def validator(raw: str) -> dict:
        try:
            result, _, _ = normalize_raw(raw, scenes, gate.catalog)
            return result
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            raise ValueError(METADATA_RULES + "\n" + feedback(raw, error)) from error

    slot = f"check_before_{VERSION}"
    await gate.request(Context(fields={"episode_number": gate.episode}), slot, decision.RULES,
                       recovery_user, validator)
    recovered = base.read(directory / f"{slot}.json")
    result, normalized_raw, changes = normalize_raw(recovered["raw"], scenes, gate.catalog)
    write_original_cache(directory, request, normalized_raw, result, {
        "mode": "feedback_api_then_metadata_normalization",
        "seed_attempt": str(seed),
        "seed_attempt_sha256": file_hash(seed),
        "recovery_cache": str(directory / f"{slot}.json"),
        "recovery_cache_sha256": file_hash(directory / f"{slot}.json"),
        "normalization": changes,
    })
    return {"run": run, "episode": directory.name, "status": "recovered_with_feedback_api",
            "normalization": changes, "decision": result["status"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "recover"))
    parser.add_argument("--root", type=Path, default=study.ROOT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run", choices=study.RUNS, default="R01")
    group.add_argument("--all-runs", action="store_true")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--execute-api", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    root = args.root.resolve()
    study.load(root)
    runs = study.RUNS if args.all_runs else (args.run,)
    if args.action == "status":
        for run in runs:
            directory = pending_directory(root, run)
            print(json.dumps({
                "run": run,
                "pending": directory.name if directory else None,
                "accepted_check": bool(directory and (directory / "check_before.json").exists()),
            }, ensure_ascii=False))
        return
    with (root / ".recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(asyncio.run, recover_one(root, run, args.execute_api)) for run in runs]
            results = [future.result() for future in as_completed(futures)]
    for result in sorted(results, key=lambda item: item["run"]):
        print(json.dumps(result, ensure_ascii=False))
    pending = [item for item in results if item["status"] == "needs_feedback_api"]
    if pending:
        raise SystemExit("Some gates need Qwen3.6 feedback; rerun with --execute-api")


if __name__ == "__main__":
    main()
