#!/usr/bin/env python3
"""Run generalized gate v3 from the same 12 frozen PG19 outlines, without reusing scripts."""

import hashlib
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import pg19_selected12_study as base


SOURCE_ROOT = Path(os.environ.get("PG19_V3_SOURCE_ROOT", base.ROOT))
REPLICATE = os.environ.get("PG19_V3_REPLICATE", "")
if REPLICATE not in ("", "R02", "R03"):
    raise ValueError(f"Unsupported PG19_V3_REPLICATE: {REPLICATE}")
ROOT = base.SCRIPT_ROOT / "output" / (
    f"pg19_gate_v3_generalized_12_frozen_map_v1_{REPLICATE}"
    if REPLICATE else "pg19_gate_v3_generalized_12_frozen_map_v1"
)
ORIGINAL_GENERATION_ENVIRONMENT = base.generation_environment
PROTOCOL_VERSION = "pg19-gate-v3-generalized-12-frozen-map-v1"
FUTURE_MAP_FILES = ("future_map.json", "episode_contributions.json")


def tree_digest(directory):
    digest = hashlib.sha256()
    paths = [directory / "pipeline_result.json"]
    for relative in base.ASSET_PARTS:
        source = directory / relative
        paths.extend(source.rglob("*") if source.is_dir() else [source])
    for path in sorted(item for item in paths if item.is_file()):
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def code_digest():
    directory = base.SCRIPT_ROOT / "service/drama_by_creativity"
    paths = [directory / "conservative_scene_gate_v3.py", directory / "scene_gate_v3_retrieval.py"]
    return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()


def prepare():
    ROOT.mkdir(parents=True, exist_ok=True)
    protocol_path = ROOT / "protocol.json"
    previous = base.read_json(protocol_path) if protocol_path.is_file() else None
    previous_hashes = {
        row["sample_id"]: row["assets_sha256"]
        for row in (previous or {}).get("samples", [])
    }
    samples = []
    for row in base.SAMPLES:
        sample_id = row["sample_id"]
        source = SOURCE_ROOT / sample_id
        source_input = source / "input.json"
        source_assets = source / "assets"
        if not source_input.is_file() or not (source_assets / "pipeline_result.json").is_file():
            raise ValueError(f"Missing frozen outlines/assets for {sample_id}: {source}")
        destination = ROOT / sample_id
        destination.mkdir(parents=True, exist_ok=True)
        target_input = destination / "input.json"
        if target_input.is_file() and target_input.read_bytes() != source_input.read_bytes():
            raise ValueError(f"Frozen input changed: {target_input}")
        if not target_input.is_file():
            shutil.copy2(source_input, target_input)
        target_assets = destination / "assets"
        if target_assets.exists():
            if not target_assets.is_symlink() or target_assets.resolve() != source_assets.resolve():
                raise ValueError(f"Frozen asset reference changed: {target_assets}")
        else:
            target_assets.symlink_to(source_assets, target_is_directory=True)
        future_source = source / "candidate/04_future_map"
        future_target = destination / "candidate/04_future_map"
        future_target.mkdir(parents=True, exist_ok=True)
        future_hashes = {}
        for name in FUTURE_MAP_FILES:
            source_path = future_source / name
            target_path = future_target / name
            if not source_path.is_file():
                raise ValueError(f"Missing frozen Future Map asset: {source_path}")
            source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if target_path.exists():
                if hashlib.sha256(target_path.read_bytes()).hexdigest() != source_hash:
                    raise ValueError(f"Frozen Future Map asset changed: {target_path}")
            else:
                shutil.copy2(source_path, target_path)
            future_hashes[name] = source_hash
        assets_sha256 = previous_hashes.get(sample_id) or tree_digest(source_assets)
        samples.append({
            "sample_id": sample_id,
            "assets_sha256": assets_sha256,
            "future_map_sha256": future_hashes,
        })
    protocol = {
        "protocol_version": PROTOCOL_VERSION,
        "created_at": base.utc_now(),
        "source_root": str(SOURCE_ROOT),
        "episodes_per_sample": base.EPISODES,
        "sample_count": len(base.SAMPLES),
        "generation_model": base.GENERATION_MODEL,
        "gate_policy": "conservative_v3 generalized",
        "gate_implementation_sha256": code_digest(),
        "scene_limit": 40,
        "scene_budget": 10000,
        "state_memory": "StructuredStateMemory hybrid; limit=20; budget=6000",
        "reuse_policy": "Frozen v1 planning assets and outline-derived initial Future Map only; no scripts, memory, or gate outcomes reused",
        "samples": samples,
    }
    if REPLICATE:
        protocol["replicate"] = REPLICATE
    if previous is not None:
        previous.pop("created_at", None)
        protocol.pop("created_at")
        if previous != protocol:
            raise ValueError(f"Protocol or gate implementation changed: {protocol_path}")
    else:
        base.atomic_json(protocol_path, protocol)
    print(f"prepared={len(samples)} protocol={protocol_path}")


def generation_environment(output: Path):
    environment = ORIGINAL_GENERATION_ENVIRONMENT(output)
    environment.update({
        "DRAMA_SCENE_GATE_POLICY": "conservative_v3",
        "DRAMA_SCENE_GATE_V3_LIMIT": "40",
        "DRAMA_SCENE_GATE_V3_BUDGET": "10000",
        "DRAMA_STAGE_TIMING": "1",
    })
    return environment


base.ROOT = ROOT
base.PROTOCOL_VERSION = PROTOCOL_VERSION
base.prepare = prepare
base.generation_environment = generation_environment
if REPLICATE:
    base.story_id = lambda sample_id: f"pg19_selected12_{sample_id}_candidate_{REPLICATE}"


if __name__ == "__main__":
    base.main()
