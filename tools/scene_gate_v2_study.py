"""Run the quality-preserving Scene Gate V2 on three full 60-episode trajectories."""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from drama_local.runtime import atomic_json
from service.drama_by_creativity.state_lifecycle_memory import StateLifecycleMemory
from tools import state_hybrid_study as generation
from tools.quality_preserving_scene_gate import (
    POLICY,
    QualityPreservingSceneGate,
    changed_ratio,
    route_hard_checks,
)


ROOT = REPO / "output/scene_gate_v2_quality_preserving"
SOURCE = REPO / "output/full_scene_gate_ab_v1"
EVALUATOR = Path(os.environ.get(
    "DRAMA_LOGIC_EVALUATOR",
    "/inspire/hdd/global_user/wangqiqi-CZXS25210124/"
    "drama_evaluator_logic_quality/evaluate_multi_agent.py",
))
RUNS = ("R01", "R02", "R03")
REFERENCE_ARMS = ("control_hybrid", "candidate_gate")
ARM = "candidate_gate_v2"
EPISODES = 60
DIMENSIONS = ("剧本逻辑总分", "剧本质量最终总分")
EVALUATION_CONFIG = {
    "model": "Qwen3.8-27B",
    "context_mode": "direct",
    "direct_char_limit": 300000,
    "chunk_chars": 100000,
    "max_output_tokens": 24576,
    "review_workers": 2,
    "audit_workers": 2,
    "arbitration_workers": 2,
    "timeout": 1200,
    "retries": 3,
    "parse_retries": 3,
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identifier(run: str) -> str:
    return f"scene-gate-v2-{run}"


def evaluator_files() -> list[Path]:
    root = EVALUATOR.parent
    paths = [EVALUATOR]
    paths.extend(path for folder in (root / "drama_evaluator", root / "prompts")
                 for path in folder.rglob("*") if path.is_file() and path.suffix in {".py", ".md"})
    return sorted(set(paths))


def implementation_hashes() -> dict[str, str]:
    paths = [
        Path(__file__),
        REPO / "scene_gate_v2_study.sh",
        REPO / "tools/quality_preserving_scene_gate.py",
        REPO / "tools/state_hybrid_study.py",
        REPO / "service/drama_by_creativity/generate_episode_script.py",
        REPO / "service/drama_by_creativity/state_lifecycle_memory.py",
        REPO / "service/drama_by_creativity/conservative_scene_gate.py",
        REPO / "service/drama_by_creativity/scene_gate_decision.py",
        REPO / "service/drama_by_creativity/scene_state_gate.py",
        REPO / "service/drama_by_creativity/scene_outline_inference.py",
    ]
    paths.extend(evaluator_files())
    return {str(path): file_hash(path) for path in sorted(set(paths))}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_bundle(source: Path) -> tuple[dict, dict]:
    manifest = read(source / "manifest.json")
    bundle = read(source / "frozen_inputs.json")
    if manifest.get("bundle_sha256") != generation.digest(bundle):
        raise ValueError("Source A/B frozen input bundle changed")
    if manifest.get("source_story_id") != "APID-test-001" or manifest.get("episodes") != EPISODES:
        raise ValueError("Unexpected source A/B experiment")
    for arm in REFERENCE_ARMS:
        for run in RUNS:
            directory = source / arm / run
            status = generation.directory_progress(directory, "hybrid", f"full-gate-{arm}-{run}")
            if status["complete"] != EPISODES:
                raise ValueError(f"Reference trajectory is incomplete: {arm}/{run}")
            reference_scores(directory)
    return manifest, bundle


def intervention_audit(source: Path) -> dict:
    rows = []
    for run in RUNS:
        root = source / "candidate_gate" / run / "scene_state_gate"
        for outcome_path in sorted(root.glob("*/E*/outcome.json")):
            outcome = read(outcome_path)
            if not outcome.get("repair_attempted"):
                continue
            original = read(outcome_path.parent / "input.json")["scenes"]
            checks = [item for item in outcome["before"]["checks"]
                      if item.get("classification") == "hard_conflict"]
            rewrite, constraints = route_hard_checks(checks)
            rows.append({
                "run": run,
                "episode": outcome_path.parent.name,
                "v1_hard_checks": len(checks),
                "v1_domains": [item["domain"] for item in checks],
                "v1_changed_ratio": changed_ratio(original, outcome["candidate_scenes"]),
                "v2_minimal_rewrite_domains": [item["domain"] for item in rewrite],
                "v2_constraint_domains": [item["domain"] for item in constraints],
            })
    return {
        "scope": "Observed V1 interventions only; this diagnoses routing and does not resample generation.",
        "v1_checked_episodes": len(RUNS) * EPISODES,
        "v1_rewritten_episodes": len(rows),
        "rows": rows,
    }


def prepare(source: Path, root: Path) -> None:
    if (root / "manifest.json").exists():
        load(root)
        return
    if root == source or (root.exists() and any(root.iterdir())):
        raise ValueError("Prepare requires a fresh output directory")
    source_manifest, bundle = source_bundle(source)
    implementation = implementation_hashes()
    audit = intervention_audit(source)
    manifest = {
        "version": 1,
        "source": str(source),
        "source_manifest_sha256": generation.digest(source_manifest),
        "bundle_sha256": generation.digest(bundle),
        "arm": ARM,
        "runs": list(RUNS),
        "episodes": EPISODES,
        "generation_model": "Qwen3.6-27B",
        "evaluation_model": "Qwen3.8-27B",
        "policy": POLICY,
        "implementation": implementation,
        "intervention": (
            "Factorized evidence checker; defer reversible hard conflicts as additive script constraints; "
            "minimal outline rewrite only for life/object conflicts; preserve dramatic fields; fallback to constraints."
        ),
        "memory": "Native narrative memory plus single nine-field lifecycle state with hybrid retrieval.",
        "excluded": ["obligation memory", "Strategy cards"],
        "comparison": (
            "New independent trajectories are compared descriptively with frozen Control/V1 references. "
            "Observed V1 intervention audit is retained separately because full trajectories do not share random streams."
        ),
        "evaluation": EVALUATION_CONFIG,
    }
    atomic_json(root / "frozen_inputs.json", bundle)
    atomic_json(root / "intervention_audit.json", audit)
    for run in RUNS:
        directory = root / ARM / run
        inputs = bundle["inputs"]
        atomic_json(directory / "04_future_map/future_map.json", inputs["future_map"])
        atomic_json(directory / "04_future_map/episode_contributions.json", inputs["episode_contributions"])
        atomic_json(directory / "generation_assets.json", bundle["assets"])
        state_root = directory / "state_lifecycle" / identifier(run)
        atomic_json(state_root / "story_assets.json", bundle["assets"])
        atomic_json(state_root / "initial_state.json", bundle["initial"])
        atomic_json(directory / "arm_binding.json", {
            "arm": ARM,
            "run": run,
            "manifest_sha256": generation.digest(manifest),
        })
    atomic_json(root / "manifest.json", manifest)


def load(root: Path) -> tuple[dict, dict]:
    manifest = read(root / "manifest.json")
    bundle = read(root / "frozen_inputs.json")
    if manifest.get("version") != 1 or manifest.get("implementation") != implementation_hashes():
        raise ValueError("Frozen Scene Gate V2 implementation changed; use a new experiment directory")
    if manifest.get("bundle_sha256") != generation.digest(bundle):
        raise ValueError("Frozen Scene Gate V2 inputs changed")
    source_manifest, source = source_bundle(Path(manifest["source"]))
    if (manifest["source_manifest_sha256"] != generation.digest(source_manifest)
            or source != bundle):
        raise ValueError("Source A/B experiment changed")
    return manifest, bundle


def verify_directory(root: Path, run: str, manifest: dict, bundle: dict) -> Path:
    directory = root / ARM / run
    expected = {"arm": ARM, "run": run, "manifest_sha256": generation.digest(manifest)}
    if read(directory / "arm_binding.json") != expected:
        raise ValueError(f"Arm binding changed: {run}")
    generation.verify_static_inputs(directory, bundle["inputs"])
    state_root = directory / "state_lifecycle" / identifier(run)
    for path, expected_value in (
        (state_root / "story_assets.json", bundle["assets"]),
        (state_root / "initial_state.json", bundle["initial"]),
        (directory / "generation_assets.json", bundle["assets"]),
    ):
        if read(path) != expected_value:
            raise ValueError(f"Opening state/assets changed: {path}")
    return directory


def score_path(directory: Path) -> Path:
    return directory / "drama_evaluations_logic_quality_qwen38_v24/full_60_episodes/scores.json"


def extract_scores(path: Path) -> dict[str, float]:
    payload = read(path)
    if payload.get("model") != "Qwen3.8-27B":
        raise ValueError(f"Unexpected evaluator model: {path}")
    result = {name: payload["scores"][name]["final_score"] for name in DIMENSIONS}
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100
           for value in result.values()):
        raise ValueError(f"Invalid evaluator scores: {path}")
    return result


def reference_scores(directory: Path) -> dict[str, float]:
    path = directory / "drama_evaluations_logic_quality_qwen38_v24/full_60_episodes/scores.json"
    if not path.exists():
        raise ValueError(f"Missing frozen v2.4 reference score: {path}")
    return extract_scores(path)


def candidate_scores(directory: Path) -> dict[str, float] | None:
    path = score_path(directory)
    return extract_scores(path) if path.exists() else None


def export_script(directory: Path) -> tuple[Path, str]:
    episodes = generation.scripts(directory)
    if len(episodes) != EPISODES:
        raise ValueError("Evaluation requires all 60 episodes")
    text = "\n\n".join(f"第{index + 1}集\n\n{episode.strip()}"
                         for index, episode in enumerate(episodes)) + "\n"
    destination = directory / "drama_evaluator_logic_quality_input/full_60_episodes.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination, hashlib.sha256(text.encode()).hexdigest()


def evaluate(directory: Path) -> None:
    script, script_sha = export_script(directory)
    destination = score_path(directory).parent
    protocol = {
        **EVALUATION_CONFIG,
        "script_sha256": script_sha,
        "evaluator_sha256": {str(path): file_hash(path) for path in evaluator_files()},
    }
    protocol_path = destination / "experiment_protocol.json"
    if protocol_path.exists() and read(protocol_path) != protocol:
        raise ValueError(f"Evaluation protocol changed: {protocol_path}")
    destination.mkdir(parents=True, exist_ok=True)
    atomic_json(protocol_path, protocol)
    config = EVALUATION_CONFIG
    command = [
        sys.executable,
        str(EVALUATOR),
        str(script),
        "--output-dir", str(destination),
        "--model", config["model"],
        "--context-mode", config["context_mode"],
        "--direct-char-limit", str(config["direct_char_limit"]),
        "--chunk-chars", str(config["chunk_chars"]),
        "--max-output-tokens", str(config["max_output_tokens"]),
        "--review-workers", str(config["review_workers"]),
        "--audit-workers", str(config["audit_workers"]),
        "--arbitration-workers", str(config["arbitration_workers"]),
        "--timeout", str(config["timeout"]),
        "--retries", str(config["retries"]),
        "--parse-retries", str(config["parse_retries"]),
    ]
    environment = dict(os.environ)
    environment.setdefault("DRAMA_EVAL_BASE_URL", "http://127.0.0.1:8001/v1")
    environment.setdefault("DRAMA_EVAL_API_KEY", "EMPTY")
    environment.setdefault("DRAMA_EVAL_TEMPERATURE", "0")
    environment.setdefault("DRAMA_EVAL_ENABLE_THINKING", "false")
    subprocess.run(command, cwd=EVALUATOR.parent, env=environment, check=True)
    candidate_scores(directory)


def report(root: Path, runs: tuple[str, ...], write: bool = False) -> dict:
    manifest, bundle = load(root)
    rows = []
    for run in runs:
        directory = verify_directory(root, run, manifest, bundle)
        progress = generation.directory_progress(directory, "hybrid", identifier(run))
        outcomes = [read(path) for path in directory.glob("scene_state_gate/*/E*/outcome.json")]
        row = {
            "run": run,
            "completed_episodes": progress["complete"],
            "scores": candidate_scores(directory),
            "gate_checked": len(outcomes),
            "hard_conflict_episodes": sum(bool(item["routing"]["minimal_rewrite"]
                                                or item["routing"]["constraint_injection"])
                                          for item in outcomes),
            "minimal_rewrite_attempted": sum(bool(item["repair_attempted"]) for item in outcomes),
            "minimal_rewrite_accepted": sum(bool(item["repair_accepted"]) for item in outcomes),
            "constraint_episodes": sum(bool(item["constraints_injected"]) for item in outcomes),
            "constraint_count": sum(len(item["constraints_injected"]) for item in outcomes),
            "fallback_to_constraints": sum(bool(item["fallback_to_original"]) for item in outcomes),
            "unexpected_after": sum(bool(item["unexpected_after"]) for item in outcomes),
        }
        if len(outcomes) < progress["complete"]:
            raise ValueError(f"Completed V2 episodes without gate outcomes: {run}")
        references = {
            arm: reference_scores(Path(manifest["source"]) / arm / run)
            for arm in REFERENCE_ARMS
        }
        row["reference_scores"] = references
        if row["scores"] is not None:
            row["differences"] = {
                f"v2_minus_{arm}": {
                    name: round(row["scores"][name] - values[name], 4)
                    for name in DIMENSIONS
                }
                for arm, values in references.items()
            }
        rows.append(row)
        print(
            f"{ARM}/{run}: episodes={progress['complete']}/{EPISODES} "
            f"scored={row['scores'] is not None} checked={len(outcomes)} "
            f"constraint_episodes={row['constraint_episodes']} "
            f"rewrites={row['minimal_rewrite_accepted']} unexpected={row['unexpected_after']}",
            flush=True,
        )
    result = {
        "policy": POLICY,
        "rows": rows,
        "intervention_audit": read(root / "intervention_audit.json"),
        "comparison_caveat": manifest["comparison"],
    }
    if write:
        atomic_json(root / "reports" / ("_".join(runs) + ".json"), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def run_worker(root: Path, run: str, action: str, limit: int) -> None:
    manifest, bundle = load(root)
    directory = verify_directory(root, run, manifest, bundle)
    with (directory / ".trajectory.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action == "generate":
            os.environ["DRAMA_SCENE_STATE_GATE"] = "off"
            asyncio.run(generation.generate_directory(
                bundle["inputs"], directory, "hybrid", identifier(run), limit,
                scene_gate_factory=QualityPreservingSceneGate.factory,
            ))
        else:
            if generation.directory_progress(directory, "hybrid", identifier(run))["complete"] != EPISODES:
                raise ValueError("Finish all 60 episodes before evaluation")
            if candidate_scores(directory) is None:
                evaluate(directory)


def dispatch(root: Path, runs: tuple[str, ...], action: str, limit: int, workers: int) -> None:
    summary = report(root, runs)
    pending = [row for row in summary["rows"]
               if (row["completed_episodes"] < limit if action == "generate" else row["scores"] is None)]
    if action == "evaluate" and any(row["completed_episodes"] != EPISODES for row in summary["rows"]):
        raise ValueError("Finish generation in all selected runs before evaluation")
    print(f"pending={len(pending)} stage={action}", flush=True)

    def launch(row: dict) -> int:
        run = row["run"]
        path = root / "logs" / f"{action}_{run}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable, str(Path(__file__)), action,
            "--root", str(root), "--run", run, "--worker",
            "--limit", str(limit), "--execute-api",
        ]
        with path.open("a") as stream:
            result = subprocess.run(command, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT)
        print(json.dumps({"run": run, "returncode": result.returncode, "log": str(path)},
                         ensure_ascii=False), flush=True)
        return result.returncode

    with (root / ".tasks.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            failures = [future.result() for future in as_completed(
                [executor.submit(launch, row) for row in pending]
            )]
    report(root, runs)
    if any(failures):
        raise SystemExit("Some tasks failed; successful outputs retained; rerun the same command")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "status", "generate", "evaluate", "report"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source", type=Path, default=SOURCE)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run", choices=RUNS, default="R01")
    group.add_argument("--all-runs", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int, default=EPISODES)
    parser.add_argument("--execute-api", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.workers < 1 or not 1 <= args.limit <= EPISODES:
        parser.error("Positive workers and limit between 1 and 60 required")
    root = args.root.resolve()
    runs = RUNS if args.all_runs else (args.run,)
    if args.action == "prepare":
        prepare(args.source.resolve(), root)
        report(root, runs)
    elif args.worker:
        if not args.execute_api or args.all_runs or args.action not in {"generate", "evaluate"}:
            parser.error("Worker requires one run and explicit API permission")
        run_worker(root, args.run, args.action, args.limit)
    elif args.action in {"status", "report"} or not args.execute_api:
        report(root, runs, write=args.action == "report")
        if args.action in {"generate", "evaluate"}:
            print("Read-only; add --execute-api to execute pending tasks")
    else:
        dispatch(root, runs, args.action, args.limit, args.workers)


if __name__ == "__main__":
    main()
