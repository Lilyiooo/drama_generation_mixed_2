"""Conservative scene gate with scene-aware canonical and terminal-history retrieval."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from drama_local.runtime import atomic_json
from .conservative_scene_gate import ConservativeSceneGate
from .scene_gate_v3_retrieval import retrieve_for_scene_gate
from .scene_outline_inference import validate_scene_outline
from .scene_state_gate import digest, read, state_catalog
from .structured_state_memory import state_digest


POLICY = "factorized_one_repair_scene_retrieval_v3_generalized"


def implementation_hash() -> str:
    paths = (Path(__file__), Path(__file__).with_name("scene_gate_v3_retrieval.py"))
    payload = b"".join(path.read_bytes() for path in paths)
    return hashlib.sha256(payload).hexdigest()


class ConservativeSceneGateV3(ConservativeSceneGate):
    def __init__(self, memory, episode_index, params, assets):
        output_root = Path(memory.story_dir).parents[1]
        directory = output_root / "scene_state_gate" / memory.story_id / f"E{episode_index + 1:02d}"
        super().__init__(directory, episode_index + 1, params, [])
        self.memory = memory
        self.episode_index = episode_index
        self.assets = assets
        self._retrieval_key = None
        self._retrieval_audit = None
        self.binding["experimental_policy"] = POLICY
        self.binding["experimental_implementation"] = implementation_hash()

    @classmethod
    def factory(cls, memory, episode_index, params):
        if not hasattr(memory, "data") or not hasattr(memory, "story_dir"):
            raise ValueError("conservative_v3 requires StructuredStateMemory")
        retrieval_path = Path(memory.story_dir) / "retrieval" / f"episode_{episode_index + 1:03d}.json"
        retrieval = read(retrieval_path)
        if (
            retrieval.get("story_id") != memory.story_id
            or retrieval.get("episode_id") != episode_index
            or retrieval.get("last_updated_episode") != episode_index - 1
            or retrieval.get("state_sha256") != state_digest(memory.data["state"])
        ):
            raise ValueError("Scene gate v3 is not bound to the current structured pre-episode state")
        assets_path = Path(memory.story_dir).parents[1] / "generation_assets.json"
        if not assets_path.is_file():
            raise ValueError(f"Scene gate v3 requires generation assets: {assets_path}")
        return cls(memory, episode_index, params, read(assets_path))

    def refresh_retrieval(self, scenes):
        retrieval_key = (digest(scenes), state_digest(self.memory.data["state"]))
        if self._retrieval_key == retrieval_key and (self.directory / "retrieval_v3.json").is_file():
            return self._retrieval_audit
        _, audit = retrieve_for_scene_gate(
            self.memory.data["state"],
            self.memory.data.get("metadata", {}),
            self.assets,
            self.params.get("Outline", ""),
            scenes,
            self.episode_index,
            budget=int(os.environ.get("DRAMA_SCENE_GATE_V3_BUDGET", "10000")),
            max_records=int(os.environ.get("DRAMA_SCENE_GATE_V3_LIMIT", "40")),
            history=[
                row for row in self.memory.data.get("history", [])
                if int(row.get("episode_id", -1)) < self.episode_index
            ],
        )
        if not audit["selected"]:
            raise ValueError("Scene gate v3 retrieved no state or canonical evidence")
        self.catalog = state_catalog(audit["selected"])
        self.binding = {
            "episode_number": self.episode,
            "params": self.params,
            "catalog": self.catalog,
            "mode": self.mode,
            "experimental_policy": POLICY,
            "experimental_implementation": implementation_hash(),
            "retrieval_sha256": digest(audit),
        }
        atomic_json(self.directory / "retrieval_v3.json", audit)
        self._retrieval_key = retrieval_key
        self._retrieval_audit = audit
        return audit

    def saved_scenes(self):
        path = self.directory / "input.json"
        if not path.exists():
            return None
        payload = read(path)
        scenes = validate_scene_outline(json.dumps(payload["scenes"], ensure_ascii=False), self.episode)
        self.refresh_retrieval(scenes)
        return super().saved_scenes()

    async def apply(self, ctx, scenes):
        original = validate_scene_outline(json.dumps(scenes, ensure_ascii=False), self.episode)
        self.refresh_retrieval(original)
        return await super().apply(ctx, original)
