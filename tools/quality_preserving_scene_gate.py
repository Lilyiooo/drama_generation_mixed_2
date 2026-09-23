"""Quality-preserving scene gate with constraint injection before minimal rewrite."""

from __future__ import annotations

import copy
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re

from drama_local.runtime import atomic_json
from service.drama_by_creativity import scene_gate_decision as decision
from service.drama_by_creativity.conservative_scene_gate import ConservativeSceneGate
from service.drama_by_creativity.scene_outline_inference import (
    validate_repair_preserves_scenes,
    validate_scene_outline,
)
from service.drama_by_creativity.scene_state_gate import digest


POLICY = "quality_preserving_constraint_first_v2"
CONSTRAINT_FIELD = "状态一致性执行约束"
REWRITE_DOMAINS = frozenset({"life", "object"})
PROTECTED_FIELDS = (
    "核心功能",
    "人物动机与目标",
    "冲突与张力",
    "悬念钩子",
)
MAX_CHANGED_RATIO = 0.20

REPAIR_RULES = f"""你只修复 hard_checks 中必须在场次大纲阶段消除的不可逆硬冲突。
只输出完整场次JSON数组，保留原场次数量、编号、顺序和全部字段。
以下字段必须逐字保持不变：{PROTECTED_FIELDS}。
没有被 hard_checks 引用的场次必须逐字保持不变。
只能修改被引用场次中的时间与地点、出场人物、情节概要或主要情节，并且只修改解决冲突所需的最小文字。
不得删除原有事件、冲突、转折、人物目标或悬念钩子；不得用取消剧情来规避矛盾。
不得编造过去发生的复活、替身、资源补给、身份变化、提前知情或幕后事件。
允许由确实在场且具备能力和信息的角色承接动作，允许明确标注的回忆、遗物以及本场可见的合法变化。
总文字变化比例不得超过{int(MAX_CHANGED_RATIO * 100)}%。这是唯一一轮修订。"""


def implementation_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def hard_checks(result: dict) -> list[dict]:
    return [item for item in result.get("checks", []) if item.get("classification") == "hard_conflict"]


def check_key(item: dict) -> tuple[str, str, tuple[str, ...]]:
    return item["scene_id"], item["domain"], tuple(sorted(item.get("state_ids", [])))


def route_hard_checks(checks: list[dict]) -> tuple[list[dict], list[dict]]:
    rewrite, constraints = [], []
    for item in checks:
        (rewrite if item.get("domain") in REWRITE_DOMAINS else constraints).append(item)
    return rewrite, constraints


def changed_ratio(original: list[dict], repaired: list[dict]) -> float:
    before = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    after = json.dumps(repaired, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return 1.0 - SequenceMatcher(None, before, after).ratio()


def validate_quality_preserving_repair(
    original: list[dict], repaired: list[dict], checks: list[dict]
) -> dict:
    validate_repair_preserves_scenes(json.dumps(original, ensure_ascii=False), repaired)
    affected = {item["scene_id"] for item in checks}
    before = {scene["场次编号"]: scene for scene in original}
    after = {scene["场次编号"]: scene for scene in repaired}
    for scene_id, original_scene in before.items():
        repaired_scene = after[scene_id]
        if scene_id not in affected and repaired_scene != original_scene:
            raise ValueError(f"Repair changed unaffected scene {scene_id}")
        if scene_id in affected:
            for field in PROTECTED_FIELDS:
                if repaired_scene.get(field) != original_scene.get(field):
                    raise ValueError(f"Repair changed protected dramatic field {field} in {scene_id}")
    ratio = changed_ratio(original, repaired)
    if ratio > MAX_CHANGED_RATIO:
        raise ValueError(f"Repair changed {ratio:.1%}, above {MAX_CHANGED_RATIO:.0%} limit")
    return {"changed_ratio": ratio, "affected_scenes": sorted(affected)}


def _clean_reason(value: str) -> str:
    value = re.sub(r"[MS]\d{4}(?:/[MS]\d{4})*", "相关证据", value)
    return re.sub(r"\s+", " ", value).strip()


def constraint_text(item: dict) -> str:
    return (
        f"场次{item['scene_id']}：在冲突动作发生前，必须用镜头可见的行动解决以下状态矛盾："
        f"{_clean_reason(item['reason'])}"
        "只能使用既有设定或本场明确展示的合法变化；如果无法合法解决，就不得执行冲突动作。"
        "不得删除或弱化本场核心功能、人物目标、冲突、转折和悬念钩子。"
    )


def inject_constraints(scenes: list[dict], checks: list[dict]) -> tuple[list[dict], list[dict]]:
    selected = copy.deepcopy(scenes)
    by_scene: dict[str, list[str]] = {}
    records = []
    for item in checks:
        text = constraint_text(item)
        by_scene.setdefault(item["scene_id"], []).append(text)
        records.append({
            "scene_id": item["scene_id"],
            "domain": item["domain"],
            "state_ids": list(item.get("state_ids", [])),
            "text": text,
        })
    for scene in selected:
        values = by_scene.get(scene["场次编号"])
        if values:
            existing = scene.get(CONSTRAINT_FIELD, [])
            if existing and (not isinstance(existing, list) or any(not isinstance(value, str) for value in existing)):
                raise ValueError(f"{CONSTRAINT_FIELD} must be a list of strings")
            scene[CONSTRAINT_FIELD] = [*existing, *values]
    return selected, records


class QualityPreservingSceneGate(ConservativeSceneGate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.binding["experimental_policy"] = POLICY
        self.binding["experimental_implementation"] = implementation_hash()

    @classmethod
    def factory(cls, memory, episode_index, params):
        return cls.from_memory(memory, episode_index, params, "enforce")

    async def apply(self, ctx, scenes):
        original = validate_scene_outline(json.dumps(scenes, ensure_ascii=False), self.episode)
        saved = self.saved_scenes()
        if saved is not None and saved != original:
            raise ValueError("Reuse the frozen original scenes when resuming a gate")
        if saved is None:
            atomic_json(self.directory / "input.json", {
                "binding": self.binding,
                "scenes": original,
                "scenes_sha256": digest(original),
            })

        before = await self.check(ctx, original)
        initial_hard = hard_checks(before)
        rewrite_checks, deferred_checks = route_hard_checks(initial_hard)
        selected = original
        candidate = None
        after = before
        repair_metrics = None
        repair_accepted = False
        unexpected_after = []

        if rewrite_checks:
            packet = {
                "original_generation_params": self.params,
                "state_catalog": self.catalog,
                "original_scenes": original,
                "hard_checks": rewrite_checks,
            }

            def validate_repair(raw):
                result = validate_scene_outline(raw, self.episode)
                nonlocal repair_metrics
                repair_metrics = validate_quality_preserving_repair(original, result, rewrite_checks)
                return result

            candidate = await self.request(
                ctx,
                "minimal_repair",
                REPAIR_RULES,
                json.dumps(packet, ensure_ascii=False),
                validate_repair,
                temperature=0,
            )
            after = await self.check(ctx, candidate, "check_after_minimal_repair")
            deferred_keys = {check_key(item) for item in deferred_checks}
            unexpected_after = [
                item for item in hard_checks(after) if check_key(item) not in deferred_keys
            ]
            repair_accepted = not unexpected_after
            if repair_accepted:
                selected = candidate

        constraints_to_inject = list(deferred_checks)
        if rewrite_checks and not repair_accepted:
            constraints_to_inject.extend(rewrite_checks)
        selected, constraints = inject_constraints(selected, constraints_to_inject)
        selected = validate_scene_outline(json.dumps(selected, ensure_ascii=False), self.episode)

        outcome = {
            "policy": POLICY,
            "binding_sha256": digest(self.binding),
            "original_scenes_sha256": digest(original),
            "before": before,
            "after": after,
            "routing": {
                "pass": not initial_hard,
                "minimal_rewrite": [check_key(item) for item in rewrite_checks],
                "constraint_injection": [check_key(item) for item in constraints_to_inject],
            },
            "repair_attempted": candidate is not None,
            "repair_accepted": repair_accepted,
            "repair_metrics": repair_metrics,
            "fallback_to_original": candidate is not None and not repair_accepted,
            "constraints_injected": constraints,
            "deferred_to_script": bool(constraints),
            "unexpected_after": unexpected_after,
            "unresolved": bool(unexpected_after),
            "outline_rewritten": repair_accepted and candidate != original,
            "text_changed": selected != original,
            "candidate_scenes": candidate,
            "scenes": selected,
            "scenes_sha256": digest(selected),
            "allowed": True,
        }
        atomic_json(self.directory / "outcome.json", outcome)
        return selected
