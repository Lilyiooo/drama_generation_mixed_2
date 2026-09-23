import asyncio
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock

from drama_local.runtime import Context
from service.drama_by_creativity import scene_state_gate as base
from tools.quality_preserving_scene_gate import (
    CONSTRAINT_FIELD,
    QualityPreservingSceneGate,
    changed_ratio,
    inject_constraints,
    route_hard_checks,
    validate_quality_preserving_repair,
)
from tools.scene_gate_decision_study import controlled_cases


class QualityPreservingSceneGateTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        case = controlled_cases()[0]
        self.episode = case["episode"]
        self.scenes = copy.deepcopy(case["scenes"])
        self.view = copy.deepcopy(case["view"])
        self.params = copy.deepcopy(case["params"])
        self.gate = QualityPreservingSceneGate(
            self.root, self.episode, self.params, self.view, "enforce"
        )

    def hard(self, domain="resource", scene_id="2-1"):
        return {
            "scene_id": scene_id,
            "domain": domain,
            "state_ids": ["M0001"],
            "scene_span_ids": ["S0001"],
            "classification": "hard_conflict",
            "reason": "M0001确认原状态，S0001中的动作与之冲突且没有合法转换。",
        }

    def result(self, checks):
        return {
            "status": "fail" if checks else "pass",
            "action": "repair_candidate" if checks else "keep",
            "memory_conflicts": [],
            "checks": checks,
            "writing_notes": [],
            "auto_repair_executed": False,
        }

    def test_reversible_conflict_only_injects_constraint(self):
        check = self.hard("resource")
        self.gate.check = AsyncMock(return_value=self.result([check]))
        self.gate.request = AsyncMock()
        selected = asyncio.run(self.gate.apply(Context(), self.scenes))
        self.gate.request.assert_not_awaited()
        self.assertEqual(selected[0]["核心功能"], self.scenes[0]["核心功能"])
        self.assertEqual(selected[0]["主要情节"], self.scenes[0]["主要情节"])
        self.assertEqual(len(selected[0][CONSTRAINT_FIELD]), 1)
        outcome = base.read(self.root / "outcome.json")
        self.assertTrue(outcome["deferred_to_script"])
        self.assertFalse(outcome["outline_rewritten"])
        self.assertFalse(outcome["unresolved"])

    def test_irreversible_conflict_uses_minimal_rewrite(self):
        check = self.hard("object")
        repaired = copy.deepcopy(self.scenes)
        repaired[0]["情节概要"] += "角色改用仍然存在的合法物件。"
        self.gate.check = AsyncMock(side_effect=[self.result([check]), self.result([])])
        self.gate.request = AsyncMock(return_value=repaired)
        selected = asyncio.run(self.gate.apply(Context(), self.scenes))
        self.assertEqual(selected, repaired)
        outcome = base.read(self.root / "outcome.json")
        self.assertTrue(outcome["repair_accepted"])
        self.assertTrue(outcome["outline_rewritten"])
        self.assertFalse(outcome["constraints_injected"])

    def test_failed_minimal_rewrite_falls_back_to_constraint(self):
        check = self.hard("object")
        repaired = copy.deepcopy(self.scenes)
        repaired[0]["情节概要"] += "仍未解决。"
        self.gate.check = AsyncMock(side_effect=[self.result([check]), self.result([check])])
        self.gate.request = AsyncMock(return_value=repaired)
        selected = asyncio.run(self.gate.apply(Context(), self.scenes))
        self.assertEqual(selected[0]["情节概要"], self.scenes[0]["情节概要"])
        self.assertIn(CONSTRAINT_FIELD, selected[0])
        outcome = base.read(self.root / "outcome.json")
        self.assertTrue(outcome["fallback_to_original"])
        self.assertTrue(outcome["deferred_to_script"])
        self.assertTrue(outcome["unresolved"])

    def test_quality_validator_rejects_dramatic_drift_and_unrelated_scene(self):
        checks = [self.hard("object")]
        repaired = copy.deepcopy(self.scenes)
        repaired[0]["悬念钩子"] = "删除原钩子"
        with self.assertRaisesRegex(ValueError, "protected dramatic field"):
            validate_quality_preserving_repair(self.scenes, repaired, checks)

        second = copy.deepcopy(self.scenes[0])
        second["场次编号"] = "2-2"
        original = [self.scenes[0], second]
        repaired = copy.deepcopy(original)
        repaired[1]["情节概要"] += "无关改动"
        with self.assertRaisesRegex(ValueError, "unaffected scene"):
            validate_quality_preserving_repair(original, repaired, checks)

    def test_routing_constraints_and_change_ratio_are_deterministic(self):
        rewrite, constraints = route_hard_checks([
            self.hard("life"), self.hard("knowledge"), self.hard("relationship")
        ])
        self.assertEqual([item["domain"] for item in rewrite], ["life"])
        self.assertEqual([item["domain"] for item in constraints], ["knowledge", "relationship"])
        selected, records = inject_constraints(self.scenes, constraints)
        self.assertEqual(len(records), 2)
        self.assertTrue(all("M0001" not in record["text"] for record in records))
        self.assertTrue(all(record["state_ids"] == ["M0001"] for record in records))
        self.assertGreater(changed_ratio(self.scenes, selected), 0)
        self.assertEqual(selected[0]["主要情节"], self.scenes[0]["主要情节"])
        self.assertEqual(selected[0]["悬念钩子"], self.scenes[0]["悬念钩子"])


if __name__ == "__main__":
    unittest.main()
