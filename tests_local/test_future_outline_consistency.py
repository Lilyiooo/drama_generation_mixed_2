import os
from unittest.mock import patch

import jinja2

from drama_local import models as pb
from service.drama_by_creativity.future_outline_consistency import (
    build_future_episode_core_plots,
    future_outline_consistency_enabled,
    parse_bool,
)
from service.drama_by_creativity.prompts.script_unified import (
    GENERATE_SCENE_OUTLINE_PROMPT,
    GENERATE_WHOLE_EPISODE_PROMPT,
)


def _outline(number: int, title: str, core_plot: str) -> str:
    return f"""### 第{number}集：{title}
涉及角色：角色{number}

#### 核心情节
{core_plot}

#### 本集亮点
绝不能进入未来上下文的亮点{number}
"""


def test_future_context_contains_only_later_titles_and_core_plots():
    outlines = [
        _outline(1, "起点", "第一集核心"),
        _outline(2, "追查", "第二集核心"),
        _outline(3, "揭晓", "第三集核心"),
    ]

    context = build_future_episode_core_plots(outlines, 0)

    assert "第一集核心" not in context
    assert "第2集：追查" in context
    assert "第二集核心" in context
    assert "第3集：揭晓" in context
    assert "第三集核心" in context
    assert "涉及角色" not in context
    assert "本集亮点" not in context
    assert "绝不能进入未来上下文" not in context
    assert build_future_episode_core_plots(outlines, 2) == ""


def test_switch_defaults_off_and_supports_explicit_true():
    with patch.dict(os.environ, {}, clear=True):
        assert not future_outline_consistency_enabled(pb.GenerateInputByCreativity())
        assert not future_outline_consistency_enabled(
            pb.GenerateInputByCreativity(future_outline_consistency=False)
        )

    with patch.dict(
        os.environ, {"DRAMA_FUTURE_OUTLINE_CONSISTENCY": "false"}, clear=True
    ):
        assert not future_outline_consistency_enabled(pb.GenerateInputByCreativity())
        assert future_outline_consistency_enabled(
            pb.GenerateInputByCreativity(future_outline_consistency=True)
        )

    with patch.dict(
        os.environ, {"DRAMA_FUTURE_OUTLINE_CONSISTENCY": "true"}, clear=True
    ):
        assert not future_outline_consistency_enabled(
            pb.GenerateInputByCreativity(future_outline_consistency=False)
        )

    assert parse_bool("true") is True
    assert parse_bool("0") is False


def test_future_section_is_conditional_in_both_generation_prompts():
    future_context = "### 第2集：追查\n第二集核心"
    for source in (GENERATE_SCENE_OUTLINE_PROMPT, GENERATE_WHOLE_EPISODE_PROMPT):
        template = jinja2.Template(source)
        enabled = template.render(FutureEpisodeCorePlots=future_context)
        disabled = template.render(FutureEpisodeCorePlots="")

        assert "后续尚未生成剧本的逐集核心情节" in enabled
        assert future_context in enabled
        assert "不得在本集提前" in enabled
        assert "后续尚未生成剧本的逐集核心情节" not in disabled
        assert future_context not in disabled
