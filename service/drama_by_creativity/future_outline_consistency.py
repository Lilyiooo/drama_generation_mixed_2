"""Future episode-outline context used to protect downstream continuity."""
from __future__ import annotations

import os
import re
from typing import Iterable


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"布尔值必须是 true/false，实际为：{value}")


def future_outline_consistency_enabled(generate_input=None) -> bool:
    """An explicit request value wins; otherwise read the environment, defaulting off."""
    request_value = getattr(generate_input, "future_outline_consistency", None)
    if request_value is not None:
        return parse_bool(request_value)
    environment_value = os.getenv("DRAMA_FUTURE_OUTLINE_CONSISTENCY", "").strip()
    if environment_value:
        return parse_bool(environment_value)
    return False


def _extract_title_and_core_plot(outline: str, episode_number: int) -> tuple[str, str]:
    text = str(outline or "").strip()
    title_match = re.search(r"^###\s*第\s*\d+\s*集[：:]\s*(.+?)\s*$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""
    core_match = re.search(
        r"####\s*核心情节\s*\n(.*?)(?=\n\s*####|\Z)",
        text,
        re.DOTALL,
    )
    core_plot = core_match.group(1).strip() if core_match else text
    if not core_plot:
        core_plot = "（核心情节为空）"
    return title or f"第{episode_number}集", core_plot


def build_future_episode_core_plots(
    episode_outlines: Iterable[str], current_episode_id: int
) -> str:
    """Return only title and core_plot for episodes after the current episode."""
    outlines = list(episode_outlines)
    blocks = []
    for index in range(current_episode_id + 1, len(outlines)):
        episode_number = index + 1
        title, core_plot = _extract_title_and_core_plot(outlines[index], episode_number)
        blocks.append(f"### 第{episode_number}集：{title}\n{core_plot}")
    return "\n\n".join(blocks)
