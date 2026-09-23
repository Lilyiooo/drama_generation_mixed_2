#!/usr/bin/env python3
"""Run the current pipeline on the 12 frozen Chinese PG-19 creativity inputs."""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import requests


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(os.environ.get(
    "PG19_SELECTED12_DATASET",
    SCRIPT_ROOT / "results/pg19_selected12/shared_inputs/pipeline_inputs_zh.jsonl",
))
ROOT = SCRIPT_ROOT / "output/pg19_selected12_state_hybrid_gate_v1"
EVALUATOR_ROOT = Path(os.environ.get(
    "DRAMA_EVALUATOR_ROOT",
    SCRIPT_ROOT / "evaluation/drama_evaluator_logic_quality",
))
PYTHON_BIN = os.environ.get(
    "PYTHON_BIN",
    "/inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/"
    "anaconda3/envs/qwen36-vllm/bin/python",
)
EPISODES = 60
GENERATION_MODEL = "Qwen3.6-27B"
EVALUATION_MODEL = "Qwen3.8-27B"
PROTOCOL_VERSION = "pg19-selected12-state-hybrid-conservative-gate-v1"
ASSET_PARTS = (
    "generation_background.json",
    "01_script_proposal",
    "03_story_outline",
    "04_episode_outline",
    "04_episode_outline_review",
    "04_future_map",
    "04_stage_plan",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def canonical_sha(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_samples() -> list[dict]:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 12:
        raise ValueError(f"Expected 12 selected records, found {len(rows)}")
    seen = set()
    for row in rows:
        required = {"sample_id", "length_group", "cluster_id", "topic", "world_view", "role_setting", "core_story"}
        missing = required - set(row)
        if missing:
            raise ValueError(f"{row.get('sample_id', 'unknown')} missing {sorted(missing)}")
        sample_id = row["sample_id"]
        if sample_id in seen or not isinstance(sample_id, str) or not sample_id:
            raise ValueError(f"Invalid or duplicate sample_id: {sample_id!r}")
        seen.add(sample_id)
        for key in ("topic", "world_view", "role_setting", "core_story"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f"{sample_id} has invalid {key}")
        row.setdefault("reference", "")
    return rows


SAMPLES = load_samples()
SAMPLE_BY_ID = {row["sample_id"]: row for row in SAMPLES}


def story_id(sample_id: str) -> str:
    return f"pg19_selected12_{sample_id}_candidate"


def sample_root(sample_id: str) -> Path:
    return ROOT / sample_id


def input_path(sample_id: str) -> Path:
    return sample_root(sample_id) / "input.json"


def asset_dir(sample_id: str) -> Path:
    return sample_root(sample_id) / "assets"


def candidate_dir(sample_id: str) -> Path:
    return sample_root(sample_id) / "candidate"


def score_path(sample_id: str) -> Path:
    return (
        candidate_dir(sample_id)
        / "drama_evaluations_logic_quality_qwen38_v24/full_60_episodes/scores.json"
    )


def prepare() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    frozen = []
    for row in SAMPLES:
        sample_id = row["sample_id"]
        payload = {
            "sample_id": sample_id,
            "length_group": row["length_group"],
            "cluster_id": row["cluster_id"],
            "topic": row["topic"],
            "world_view": row["world_view"],
            "role_setting": row["role_setting"],
            "core_story": row["core_story"],
            "reference": row.get("reference", ""),
        }
        path = input_path(sample_id)
        if path.is_file() and read_json(path) != payload:
            raise ValueError(f"Frozen input changed: {path}")
        atomic_json(path, payload)
        frozen.append(
            {
                "sample_id": sample_id,
                "input": str(path),
                "input_sha256": canonical_sha(payload),
                "length_group": row["length_group"],
                "cluster_id": row["cluster_id"],
                "topic": row["topic"],
            }
        )
    protocol = {
        "protocol_version": PROTOCOL_VERSION,
        "created_at": utc_now(),
        "source_dataset": str(DATASET),
        "sample_count": len(SAMPLES),
        "episodes_per_sample": EPISODES,
        "replicates_per_story": 1,
        "candidate": {
            "model": GENERATION_MODEL,
            "pipeline": "new upstream ScriptDrama",
            "memory": "StructuredStateMemory hybrid retrieval",
            "scene_gate": "conservative_v1 enforce",
            "state_memory_limit": 20,
            "state_memory_budget_characters": 6000,
            "plot_retrieval": False,
            "summary_memory_baseline": False,
            "full_history_baseline": False,
            "world_role_source": "provided selected Chinese creativity input",
        },
        "evaluation": {
            "model": EVALUATION_MODEL,
            "pipeline": str(EVALUATOR_ROOT),
            "version": "v24 logic+quality",
        },
        "samples": frozen,
    }
    existing = ROOT / "protocol.json"
    if existing.is_file():
        previous = read_json(existing)
        previous.pop("created_at", None)
        comparable = dict(protocol)
        comparable.pop("created_at", None)
        if previous != comparable:
            raise ValueError(f"Protocol changed: {existing}")
    else:
        atomic_json(existing, protocol)
    print(f"prepared={len(SAMPLES)} protocol={existing}")


def verify_server(base_url: str, model: str) -> None:
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(base_url.rstrip("/") + "/models", timeout=10)
    response.raise_for_status()
    names = [row.get("id") for row in response.json().get("data", [])]
    if model not in names:
        raise RuntimeError(f"{base_url} serves {names}, not {model}")


def episode_outline_count(directory: Path) -> int:
    outline_dir = directory / "04_episode_outline"
    episodes = []
    for path in sorted(outline_dir.glob("*.json")):
        payload = read_json(path)
        if not isinstance(payload, list):
            raise ValueError(f"Invalid episode outline file: {path}")
        episodes.extend(payload)
    ids = [int(row.get("episode_id", -1)) for row in episodes if isinstance(row, dict)]
    if ids and ids != list(range(1, len(ids) + 1)):
        raise ValueError(f"Non-contiguous episode outlines: {directory}")
    return len(ids)


def assets_complete(sample_id: str) -> bool:
    directory = asset_dir(sample_id)
    return (
        (directory / "pipeline_result.json").is_file()
        and (directory / "generation_background.json").is_file()
        and episode_outline_count(directory) == EPISODES
    )


def memory_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return int(read_json(path).get("last_updated_episode", -1)) + 1


def candidate_state(sample_id: str) -> dict:
    directory = candidate_dir(sample_id)
    sid = story_id(sample_id)
    scripts = len(list((directory / "05_drama").glob("episode_*.json")))
    narrative = memory_count(directory / "narrative_memory" / sid / "memory_state.json")
    structured = memory_count(directory / "structured_state" / sid / "state_memory.json")
    gates = len(list((directory / "scene_state_gate" / sid).glob("E*/outcome.json")))
    return {
        "sample_id": sample_id,
        "assets": assets_complete(sample_id),
        "episodes": scripts,
        "narrative": narrative,
        "structured": structured,
        "gate_outcomes": gates,
        "complete": scripts == narrative == structured == EPISODES,
        "scored": score_path(sample_id).is_file(),
    }


def generation_environment(output: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DRAMA_OUTPUT_DIR": str(output),
            "DRAMA_STATE_LIFECYCLE_HYBRID": "0",
            "DRAMA_SCENE_STATE_GATE": "enforce",
            "DRAMA_SCENE_GATE_POLICY": "conservative_v1",
            "DRAMA_SCENE_GATE_SCHEMA_FALLBACK": "1",
            "DRAMA_STATE_MEMORY_LIMIT": "20",
            "DRAMA_STATE_MEMORY_BUDGET": "6000",
            "DRAMA_DISABLE_PLOT_RETRIEVAL": "1",
            "DRAMA_SUMMARY_MEMORY_BASELINE": "false",
            "DRAMA_FULL_HISTORY_BASELINE": "false",
            "DRAMA_FUTURE_OUTLINE_CONSISTENCY": "false",
            "DRAMA_ADJUST_WORD_COUNT": "false",
            "DRAMA_ADJUST_COHERENCE": "false",
            "DRAMA_REGENERATE_WORLD_ROLE": "0",
            "DRAMA_LLM_BASE_URL": os.environ.get("DRAMA_LLM_BASE_URL", "http://127.0.0.1:8000/v1"),
            "DRAMA_LLM_MODEL": GENERATION_MODEL,
            "DRAMA_LLM_THINKING": "0",
            "DRAMA_LLM_TIMEOUT": os.environ.get("DRAMA_LLM_TIMEOUT", "0"),
            "DRAMA_LLM_MAX_TOKENS": os.environ.get("DRAMA_LLM_MAX_TOKENS", "0"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def run_logged(command: list[str], log: Path, environment: dict[str, str]) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{utc_now()}] command={json.dumps(command, ensure_ascii=False)}\n")
        handle.flush()
        completed = subprocess.run(
            command,
            cwd=SCRIPT_ROOT,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    if completed.returncode:
        raise RuntimeError(f"command failed with exit code {completed.returncode}; log={log}")


def ensure_assets(sample_id: str) -> None:
    if assets_complete(sample_id):
        return
    base = sample_root(sample_id)
    base.mkdir(parents=True, exist_ok=True)
    recoverable = sorted(
        (
            path
            for path in base.glob(".assets-planning-*")
            if (path / "04_episode_outline_review/status.json").is_file()
            and (path / "04_stage_plan/attempts/outline_round_01_rewrite_03.json").is_file()
        ),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if recoverable:
        temporary = recoverable[0]
        run_logged(
            [PYTHON_BIN, "-u", "tools/recover_pg19_outline_assets.py", str(temporary)],
            ROOT / "logs" / f"plan_recovery_{sample_id}.log",
            generation_environment(temporary),
        )
        if episode_outline_count(temporary) != EPISODES:
            raise RuntimeError(f"Recovered planning did not produce {EPISODES} outlines: {temporary}")
        os.replace(temporary, asset_dir(sample_id))
        return
    temporary = Path(tempfile.mkdtemp(prefix=".assets-planning-", dir=base))
    command = [
        PYTHON_BIN,
        "-u",
        "service/drama_by_creativity/tests/run_test.py",
        "--all",
        "--outline-only",
        "--episode_nums",
        str(EPISODES),
        "--story_id",
        f"{story_id(sample_id)}_assets",
        "--creativity-input",
        str(input_path(sample_id)),
    ]
    try:
        run_logged(
            command,
            ROOT / "logs" / f"plan_{sample_id}.log",
            generation_environment(temporary),
        )
        if episode_outline_count(temporary) != EPISODES:
            raise RuntimeError(f"Planning did not produce {EPISODES} outlines: {temporary}")
        destination = asset_dir(sample_id)
        if destination.exists():
            raise RuntimeError(f"Incomplete canonical assets already exist: {destination}")
        os.replace(temporary, destination)
    except BaseException:
        raise


def copy_assets_for_candidate(sample_id: str) -> None:
    source = asset_dir(sample_id)
    destination = candidate_dir(sample_id)
    destination.mkdir(parents=True, exist_ok=True)
    for relative in ASSET_PARTS:
        src = source / relative
        if not src.exists():
            continue
        dst = destination / relative
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif not dst.exists():
            shutil.copy2(src, dst)


def generate_one(sample_id: str, limit: int | None) -> dict:
    lock_path = sample_root(sample_id) / ".candidate.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"{sample_id} is already running") from error
        ensure_assets(sample_id)
        copy_assets_for_candidate(sample_id)
        before = candidate_state(sample_id)
        if before["episodes"] == before["narrative"] == before["structured"] + 1:
            repair_structured_state_lag(sample_id, before["structured"])
            before = candidate_state(sample_id)
        if not (before["episodes"] == before["narrative"] == before["structured"]):
            raise RuntimeError(
                f"progress mismatch for {sample_id}: episodes={before['episodes']} "
                f"narrative={before['narrative']} structured={before['structured']}"
            )
        if before["complete"]:
            return before
        end_episode = EPISODES if limit is None else min(EPISODES, before["episodes"] + limit)
        command = [
            PYTHON_BIN,
            "-u",
            "service/drama_by_creativity/tests/run_from_episode_outline.py",
            "--source-dir",
            str(asset_dir(sample_id)),
            "--output-dir",
            str(candidate_dir(sample_id)),
            "--story-id",
            story_id(sample_id),
            "--resume",
            "--end-episode",
            str(end_episode),
        ]
        future_map = candidate_dir(sample_id) / "04_future_map/future_map.json"
        contributions = candidate_dir(sample_id) / "04_future_map/episode_contributions.json"
        if future_map.is_file() and contributions.is_file():
            command.append("--reuse-future-map")
        run_logged(
            command,
            ROOT / "logs" / f"generate_{sample_id}.log",
            generation_environment(candidate_dir(sample_id)),
        )
        return candidate_state(sample_id)


def repair_structured_state_lag(sample_id: str, episode_id: int) -> None:
    from service.drama_by_creativity.structured_state_memory import (
        StructuredStateMemory,
        validate_extraction,
    )

    directory = candidate_dir(sample_id)
    expected_task = f"更新第{episode_id + 1}集人物关系资产状态"
    expected_story = story_id(sample_id)
    candidates = []
    for record_path in directory.glob("diagnostics/**/json_attempts/*/record.json"):
        try:
            record = read_json(record_path)
        except (OSError, ValueError):
            continue
        if (
            record.get("task_name") == expected_task
            and record.get("context", {}).get("StoryID") == expected_story
            and (record_path.parent / "output.txt").is_file()
        ):
            candidates.append(record_path)
    if not candidates:
        raise RuntimeError(f"No retained structured-state extraction for {sample_id} episode {episode_id + 1}")
    source = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    extraction = validate_extraction(json.loads((source.parent / "output.txt").read_text(encoding="utf-8")))
    previous_output = os.environ.get("DRAMA_OUTPUT_DIR")
    os.environ["DRAMA_OUTPUT_DIR"] = str(directory)
    try:
        memory = StructuredStateMemory(expected_story)
        if int(memory.data.get("last_updated_episode", -1)) != episode_id - 1:
            raise RuntimeError(f"Structured-state lag changed before repair: {sample_id}")
        result = memory.commit(episode_id, extraction)
    finally:
        if previous_output is None:
            os.environ.pop("DRAMA_OUTPUT_DIR", None)
        else:
            os.environ["DRAMA_OUTPUT_DIR"] = previous_output
    atomic_json(
        directory / "structured_state" / expected_story / "recoveries" / f"episode_{episode_id + 1:03d}.json",
        {
            "policy": "apply_retained_extraction_and_evict_oldest_unchanged_attributes",
            "source": str(source),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "result": result,
        },
    )


def selected_samples(values: list[str] | None) -> list[str]:
    selected = values or [row["sample_id"] for row in SAMPLES]
    invalid = sorted(set(selected) - set(SAMPLE_BY_ID))
    if invalid:
        raise ValueError(f"Unknown sample IDs: {invalid}")
    return list(dict.fromkeys(selected))


def run_generation(samples: list[str], workers: int, limit: int | None, execute_api: bool) -> None:
    prepare()
    if not execute_api:
        print("Dry run only. Add --execute-api to call Qwen3.6-27B.")
        show_status(samples)
        return
    verify_server(os.environ.get("DRAMA_LLM_BASE_URL", "http://127.0.0.1:8000/v1"), GENERATION_MODEL)
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(generate_one, sample_id, limit): sample_id for sample_id in samples}
        for future in concurrent.futures.as_completed(futures):
            sample_id = futures[future]
            try:
                print(json.dumps(future.result(), ensure_ascii=False), flush=True)
            except Exception as error:
                failures.append(sample_id)
                print(json.dumps({"sample_id": sample_id, "error": str(error)}, ensure_ascii=False), flush=True)
    show_status(samples)
    if failures:
        raise RuntimeError(f"{len(failures)} sample(s) failed; rerun the same command to resume")


def export_candidate(sample_id: str) -> Path:
    state = candidate_state(sample_id)
    if not state["complete"]:
        raise ValueError(f"Finish generation first: {sample_id} ({state['episodes']}/{EPISODES})")
    target = candidate_dir(sample_id) / "drama_evaluator_logic_quality_input/full_60_episodes.txt"
    subprocess.run(
        [
            PYTHON_BIN,
            str(EVALUATOR_ROOT / "tools/export_pipeline_script.py"),
            str(candidate_dir(sample_id)),
            str(target),
        ],
        cwd=EVALUATOR_ROOT,
        check=True,
    )
    return target


def evaluate_one(sample_id: str, execute_api: bool) -> dict:
    if score_path(sample_id).is_file():
        return {"sample_id": sample_id, "returncode": 0, "skipped": True}
    script = export_candidate(sample_id)
    output = score_path(sample_id).parent
    command = [
        PYTHON_BIN,
        str(EVALUATOR_ROOT / "evaluate_multi_agent.py"),
        str(script),
        "--output-dir",
        str(output),
        "--model",
        EVALUATION_MODEL,
        "--context-mode",
        "direct",
        "--direct-char-limit",
        "300000",
        "--chunk-chars",
        "100000",
        "--max-output-tokens",
        "24576",
        "--timeout",
        "1200",
        "--retries",
        "3",
        "--parse-retries",
        "3",
    ]
    if not execute_api:
        command.append("--dry-run")
    environment = os.environ.copy()
    environment.update(
        {
            "DRAMA_EVAL_BASE_URL": os.environ.get("DRAMA_EVAL_BASE_URL", "http://127.0.0.1:8001/v1"),
            "DRAMA_EVAL_API_KEY": os.environ.get("DRAMA_EVAL_API_KEY", "EMPTY"),
            "DRAMA_EVAL_MODEL": EVALUATION_MODEL,
            "DRAMA_EVAL_TEMPERATURE": "0",
            "DRAMA_EVAL_ENABLE_THINKING": "false",
            "PYTHONUNBUFFERED": "1",
        }
    )
    log = ROOT / "logs" / f"evaluate_{sample_id}.log"
    try:
        run_logged(command, log, environment)
        return {"sample_id": sample_id, "returncode": 0, "log": str(log)}
    except RuntimeError as error:
        return {"sample_id": sample_id, "returncode": 1, "log": str(log), "error": str(error)}


def run_evaluation(samples: list[str], workers: int, execute_api: bool) -> None:
    prepare()
    if execute_api:
        verify_server(os.environ.get("DRAMA_EVAL_BASE_URL", "http://127.0.0.1:8001/v1"), EVALUATION_MODEL)
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(evaluate_one, sample_id, execute_api): sample_id for sample_id in samples}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if result["returncode"]:
                failures.append(result["sample_id"])
    show_status(samples)
    if failures:
        raise RuntimeError(f"{len(failures)} evaluation(s) failed; rerun the same command to resume")
    if execute_api:
        write_report()


def score_pair(path: Path) -> tuple[float, float]:
    payload = read_json(path)["scores"]
    return (
        float(payload["剧本逻辑总分"]["final_score"]),
        float(payload["剧本质量最终总分"]["final_score"]),
    )


def summarize(values: list[float]) -> dict:
    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "sample_std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def write_report() -> None:
    rows = []
    for sample in SAMPLES:
        sample_id = sample["sample_id"]
        path = score_path(sample_id)
        if not path.is_file():
            continue
        logic, quality = score_pair(path)
        rows.append(
            {
                "sample_id": sample_id,
                "length_group": sample["length_group"],
                "cluster_id": sample["cluster_id"],
                "topic": sample["topic"],
                "logic": logic,
                "quality": quality,
                "score_file": str(path),
            }
        )
    if not rows:
        raise ValueError("No completed score files")
    groups = {}
    for group in sorted({row["length_group"] for row in rows}):
        selected = [row for row in rows if row["length_group"] == group]
        groups[group] = {
            "logic": summarize([row["logic"] for row in selected]),
            "quality": summarize([row["quality"] for row in selected]),
        }
    report = {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at": utc_now(),
        "completed": len(rows),
        "expected": len(SAMPLES),
        "overall": {
            "logic": summarize([row["logic"] for row in rows]),
            "quality": summarize([row["quality"] for row in rows]),
        },
        "by_length_group": groups,
        "samples": rows,
    }
    target = ROOT / "reports/candidate_scores_v24.json"
    atomic_json(target, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report={target}")


def show_status(samples: list[str] | None = None) -> None:
    selected = samples or [row["sample_id"] for row in SAMPLES]
    totals = {"assets": 0, "episodes": 0, "complete": 0, "scored": 0}
    for sample_id in selected:
        state = candidate_state(sample_id)
        totals["assets"] += int(state["assets"])
        totals["episodes"] += state["episodes"]
        totals["complete"] += int(state["complete"])
        totals["scored"] += int(state["scored"])
        print(
            f"{sample_id}: assets={state['assets']} episodes={state['episodes']}/{EPISODES} "
            f"narrative={state['narrative']} structured={state['structured']} "
            f"gates={state['gate_outcomes']} scored={state['scored']}"
        )
    print(
        f"TOTAL: assets={totals['assets']}/{len(selected)} "
        f"episodes={totals['episodes']}/{len(selected) * EPISODES} "
        f"complete={totals['complete']}/{len(selected)} scored={totals['scored']}/{len(selected)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("prepare")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--sample", action="append", choices=tuple(SAMPLE_BY_ID))
    subparsers.add_parser("report")
    for action in ("generate", "evaluate"):
        child = subparsers.add_parser(action)
        child.add_argument("--sample", action="append", choices=tuple(SAMPLE_BY_ID))
        child.add_argument("--workers", type=int, default=0, help="0 means all selected stories concurrently")
        child.add_argument("--execute-api", action="store_true")
        if action == "generate":
            child.add_argument("--limit", type=int, help="Generate at most N new episodes per selected story")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "status":
        show_status(selected_samples(args.sample))
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
            run_generation(samples, workers, args.limit, args.execute_api)
        else:
            run_evaluation(samples, workers, args.execute_api)


if __name__ == "__main__":
    main()
