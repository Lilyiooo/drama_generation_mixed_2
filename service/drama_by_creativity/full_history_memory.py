"""Opt-in baseline that uses every completed episode script as history memory."""
from __future__ import annotations

import os

from drama_local.runtime import LocalStore, ScriptContentFile


def full_history_baseline_enabled(generate_input=None) -> bool:
    return bool(getattr(generate_input, "full_history_baseline", False)) or os.getenv(
        "DRAMA_FULL_HISTORY_BASELINE", ""
    ).strip().lower() in ("1", "true", "yes", "on")


def full_history_prompt(prompt: str) -> str:
    """Replace specialized-memory sections with one complete-script history section."""
    prompt = prompt.replace("## 上一集剧本\n{{PrevEpisodeScript}}\n\n", "")
    prompt = prompt.replace("## 上一场内容\n{{PrevPlot}}\n\n", "")
    prompt = prompt.replace("## 上一集结尾\n{{PrevPlot}}\n\n", "")
    prompt = prompt.replace("## 最近五集摘要\n{{RecentEpisodeSummaries}}\n\n", "")
    prompt = prompt.replace(
        "## 与本集相关的人物、关系、资产和环境当前状态\n{{StateMemory}}\n\n", ""
    )
    prompt = prompt.replace(
        "## 与本集相关的需求树叙事记忆",
        "## 前序已经生成的全部完整剧本（唯一历史记忆）",
    )
    prompt = prompt.replace(
        "## 与当前集内容具有叙事相关性的已发生事件、细节、伏笔、线索",
        "## 前序已经生成的全部完整剧本（唯一历史记忆）",
    )
    prompt = prompt.replace(
        "严格承接前序事件以及检索到的人物、关系、知情状态、物品归属、地点环境和未完成叙事事项；若材料之间表述不同，以已经生成的剧本事实和当前状态为连续性依据。",
        "严格承接前序完整剧本中已经确立的人物身份、关系、知情状态、物品归属、地点环境和未完成事项；若当前大纲与前序完整剧本不同，以已经生成的剧本事实为连续性依据。",
    )
    return prompt


class FullHistoryMemory:
    """Loads all preceding scripts in strict episode order without extraction."""

    def __init__(self, story_id: str):
        self.story_id = story_id
        self.store = LocalStore()
        self.story_dir = self.store.path(story_id, "script_content")

    async def retrieve(self, ctx, episode_id: int) -> str:
        scripts = []
        for previous_id in range(episode_id):
            try:
                script = await ScriptContentFile.download(
                    ctx,
                    self.store,
                    project_id=self.story_id,
                    episode_id=previous_id,
                )
            except FileNotFoundError as error:
                raise ValueError(
                    f"完整剧本 baseline 无法生成第{episode_id + 1}集："
                    f"缺少第{previous_id + 1}集完整剧本"
                ) from error
            if not isinstance(script.result, str) or not script.result.strip():
                raise ValueError(
                    f"完整剧本 baseline 无法生成第{episode_id + 1}集："
                    f"第{previous_id + 1}集完整剧本为空"
                )
            scripts.append(
                f"===== 第{previous_id + 1}集完整剧本 =====\n{script.result.strip()}"
            )
        return "\n\n".join(scripts) or "暂无（第一集尚无前序完整剧本）"
