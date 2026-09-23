import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from drama_local import models as pb
from drama_local.runtime import LocalStore, ScriptContentFile
from service.drama_by_creativity.full_history_memory import (
    FullHistoryMemory,
    full_history_baseline_enabled,
    full_history_prompt,
)
from service.drama_by_creativity.prompts import (
    GENERATE_SCENE_OUTLINE_PROMPT,
    GENERATE_WHOLE_EPISODE_PROMPT,
)


class FullHistoryMemoryTests(unittest.TestCase):
    def test_opt_in_and_prompt(self):
        with patch.dict(os.environ, {"DRAMA_FULL_HISTORY_BASELINE": "0"}):
            self.assertFalse(full_history_baseline_enabled(pb.GenerateInputByCreativity()))
            self.assertTrue(
                full_history_baseline_enabled(
                    pb.GenerateInputByCreativity(full_history_baseline=True)
                )
            )
        for original in (GENERATE_SCENE_OUTLINE_PROMPT, GENERATE_WHOLE_EPISODE_PROMPT):
            prompt = full_history_prompt(original)
            self.assertIn("前序已经生成的全部完整剧本（唯一历史记忆）", prompt)
            self.assertNotIn("需求树叙事记忆", prompt)
            self.assertNotIn("人物、关系、资产和环境当前状态", prompt)
            self.assertNotIn("最近五集摘要", prompt)
            self.assertNotIn("上一集剧本\n", prompt)
            self.assertNotIn("上一集结尾\n", prompt)

    def test_retrieve_all_scripts_in_order(self):
        async def run():
            store = LocalStore()
            await ScriptContentFile(result="第一集正文").upload(
                None, store, project_id="story", episode_id=0
            )
            await ScriptContentFile(result="第二集正文").upload(
                None, store, project_id="story", episode_id=1
            )
            memory = FullHistoryMemory("story")
            self.assertIn("第一集尚无前序完整剧本", await memory.retrieve(None, 0))
            history = await memory.retrieve(None, 2)
            self.assertLess(history.index("第一集正文"), history.index("第二集正文"))
            self.assertEqual(history.count("完整剧本 ====="), 2)
            with self.assertRaisesRegex(ValueError, "缺少第3集完整剧本"):
                await memory.retrieve(None, 3)

        with tempfile.TemporaryDirectory() as output, patch.dict(
            os.environ, {"DRAMA_OUTPUT_DIR": output}
        ):
            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
