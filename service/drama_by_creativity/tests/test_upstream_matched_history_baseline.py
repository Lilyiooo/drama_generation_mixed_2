import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from tools import upstream_matched_history_baseline as baseline


class UpstreamMatchedHistoryBaselineTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.script_root = self.root / "repo"
        self.source_root = self.script_root / "output"
        self.output_root = self.source_root / "new_scriptdrama_matched_direct_history_baseline_v1"
        prompt = self.script_root / "service/drama_by_creativity/prompts/script_format.py"
        prompt.parent.mkdir(parents=True)
        prompt.write_text('SCRIPT_FORMAT_PROMPT = "第{{EpisodeIndex}}集格式"\n', encoding="utf-8")
        self.patches = [
            patch.object(baseline, "SCRIPT_ROOT", self.script_root),
            patch.object(baseline, "SOURCE_ROOT", self.source_root),
            patch.object(baseline, "ROOT", self.output_root),
        ]
        for active in self.patches:
            active.start()
            self.addCleanup(active.stop)
        for run in baseline.RUNS:
            source = baseline.source_run_dir(run)
            assets = {
                "world_view": "",
                "role_info": f"{run}人物设定",
                "story_outline": f"{run}故事总纲",
                "episode_outlines": [
                    {"episode_id": index, "content": f"{run}第{index + 1}集大纲"}
                    for index in range(baseline.EPISODES)
                ],
            }
            baseline.atomic_json(source / "generation_assets.json", assets)
            for episode in range(1, baseline.EPISODES + 1):
                baseline.atomic_json(source / "05_drama" / f"episode_{episode:02d}.json", {
                    "episode_id": episode - 1,
                    "content": f"candidate-{run}-{episode}",
                })

    def test_prepare_freezes_different_assets_per_run_and_allows_empty_world(self):
        baseline.prepare()
        baseline.prepare()
        protocol = baseline.read_json(self.output_root / "protocol.json")
        hashes = {
            protocol["paired_sources"][run]["generation_assets_sha256"]
            for run in baseline.RUNS
        }
        self.assertEqual(len(hashes), len(baseline.RUNS))
        for run in baseline.RUNS:
            _, assets, script_format = baseline.require_prepared(run)
            self.assertEqual(assets["world_view"], "")
            self.assertEqual(assets["story_outline"], f"{run}故事总纲")
            self.assertEqual(script_format, "第{{EpisodeIndex}}集格式")
            self.assertTrue(protocol["paired_sources"][run]["world_view_empty"])

    def test_prompt_uses_only_own_baseline_history(self):
        baseline.prepare()
        _, assets, script_format = baseline.require_prepared("R02")
        prompt = baseline.render_prompt(assets, script_format, 2, ["baseline第一集原文"])
        self.assertIn("R02故事总纲", prompt)
        self.assertIn("R02第2集大纲", prompt)
        self.assertIn("baseline第一集原文", prompt)
        self.assertNotIn("candidate-R02-1", prompt)
        self.assertNotIn("R01故事总纲", prompt)

    def test_live_source_asset_drift_is_rejected(self):
        baseline.prepare()
        path = baseline.source_asset_path("R03")
        assets = json.loads(path.read_text(encoding="utf-8"))
        assets["story_outline"] += "已修改"
        baseline.atomic_json(path, assets)
        with self.assertRaisesRegex(ValueError, "changed after baseline preparation"):
            baseline.require_prepared("R03")

    def test_output_only_checkpoint_recovers_metadata_from_success_trace(self):
        baseline.prepare()
        run = "R01"
        _, assets, script_format = baseline.require_prepared(run)
        content = "baseline第一集已成功生成"
        baseline.atomic_json(baseline.episode_path(run, 1), {"episode_id": 0, "content": content})
        baseline.atomic_json(self.output_root / run / "attempts/episode_01_attempt_1.json", {
            "run": run,
            "episode": 1,
            "attempt": 1,
            "started_at": "2026-09-23T00:00:00+00:00",
            "status": "success",
            "response_sha256": baseline.sha_text(content),
            "usage": {"completion_tokens": 10},
        })
        history = baseline.verify_existing_prefix(run, assets, script_format)
        self.assertEqual(history, [content])
        record = baseline.read_json(baseline.metadata_path(run, 1))
        self.assertTrue(record["recovered_output_only_checkpoint"])
        self.assertEqual(record["history_episode_count"], 0)
        self.assertEqual(record["response_sha256"], baseline.sha_text(content))

    def test_evaluator_subprocess_receives_local_vllm_environment(self):
        script = self.root / "script.txt"
        script.write_text("剧本", encoding="utf-8")
        completed = Mock(returncode=0)
        with patch.object(baseline, "export_run", return_value=script), \
             patch.object(baseline.subprocess, "run", return_value=completed) as run:
            result = baseline.evaluate_run("R01", True)
        self.assertEqual(result["returncode"], 0)
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["DRAMA_EVAL_BASE_URL"], "http://127.0.0.1:8001/v1")
        self.assertEqual(environment["DRAMA_EVAL_MODEL"], "Qwen3.8-27B")
        self.assertEqual(environment["DRAMA_EVAL_ENABLE_THINKING"], "false")


if __name__ == "__main__":
    unittest.main()
