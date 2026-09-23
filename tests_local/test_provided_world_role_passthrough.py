import asyncio
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from drama_local import models as pb
from drama_local.runtime import Context

proposal_module = importlib.import_module(
    "service.drama_by_creativity.generate_script_proposal"
)
outline_module = importlib.import_module(
    "service.drama_by_creativity.generate_story_outline_and_role"
)


class ProvidedWorldRolePassthroughTest(unittest.TestCase):
    def test_proposal_calls_only_plot_planning_by_default(self):
        request = pb.GenerateScriptProposalByCreativityReq(
            story_info=pb.StoryInfo(plot_type=pb.PlotType.SHORT),
            generate_input=pb.GenerateInputByCreativity(
                core_story="核心创意",
                topic="悬疑、家庭",
                world_view="输入世界观",
                role_setting="输入人物设定",
                reference="",
                common=pb.GenerateInputCommon(episode_nums=20),
            ),
        )
        calls = []

        async def fake_json(*, task_name, **kwargs):
            calls.append(task_name)
            return {
                "plot_planning": [{
                    "plot_id": 1,
                    "title": "建立冲突",
                    "episode_range": [1, 20],
                    "plot_desc": [{"episode_id": 1, "plot_desc": "触发事件"}],
                }],
                "plot_stuck_point_id": 1,
                "stuck_point_desc": "从建立冲突推进至结局。",
            }

        with tempfile.TemporaryDirectory() as output, patch.dict(
            os.environ,
            {"DRAMA_OUTPUT_DIR": output, "DRAMA_REGENERATE_WORLD_ROLE": "0"},
        ), patch.object(proposal_module, "llm_inference_json", side_effect=fake_json):
            response = asyncio.run(
                proposal_module.generate_script_proposal(Context(), request)
            )

            self.assertEqual(calls, ["生成卡点信息"])
            self.assertEqual(response.story_outline.world_building, ["输入世界观"])
            self.assertEqual(response.story_outline.role_info, ["输入人物设定"])
            self.assertEqual(
                json.loads(
                    (Path(output) / "01_script_proposal/01_world_view.json").read_text(
                        encoding="utf-8"
                    )
                )["world_view"],
                "输入世界观",
            )
            self.assertEqual(
                json.loads(
                    (Path(output) / "01_script_proposal/02_role_setting.json").read_text(
                        encoding="utf-8"
                    )
                ),
                "输入人物设定",
            )

    def test_story_outline_receives_and_returns_canonical_settings(self):
        request = pb.GenerateStoryOutlineByCreativityReq(
            story_info=pb.StoryInfo(plot_type=pb.PlotType.SHORT),
            generate_input=pb.GenerateInputByCreativity(
                core_story="核心创意",
                topic="悬疑、家庭",
                world_view="输入世界观",
                role_setting="输入人物设定",
                reference="",
            ),
            generate_data=pb.GenerateStoryOutline(script_proposal=pb.ScriptProposal()),
        )
        captured = {}
        outline = {
            "title": "测试剧",
            "background": "背景",
            "framework": [
                {"stage": name, "event_list": [{"event": f"{name}事件"}]}
                for name in ("开端", "发展", "高潮", "结局")
            ],
            "highlights": "亮点",
            "summary": "总结",
        }

        async def fake_json(*, params, **kwargs):
            captured.update(params)
            return outline

        with patch.object(outline_module, "llm_inference_json", side_effect=fake_json), patch.object(
            outline_module, "refine_story_outline_eventlines", new=AsyncMock(return_value=outline)
        ):
            response = asyncio.run(
                outline_module.generate_story_outline_and_role(Context(), request)
            )

        self.assertEqual(captured["WorldView"], "输入世界观")
        self.assertEqual(captured["RoleInfo"], "输入人物设定")
        self.assertEqual(response.story_outline.world_building, ["输入世界观"])
        self.assertEqual(response.story_outline.role_info, ["输入人物设定"])


if __name__ == "__main__":
    unittest.main()
