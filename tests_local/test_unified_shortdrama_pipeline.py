from pathlib import Path

from service.drama_by_creativity import prompts
from service.drama_by_creativity.utils import get_drama_config_by_plot_type


ROOT = Path(__file__).resolve().parents[1]


def test_all_legacy_enum_values_resolve_to_one_configuration():
    configs = [get_drama_config_by_plot_type(value) for value in (None, 1, 2, 3, 4, 999)]
    assert all(config == configs[0] for config in configs)
    assert configs[0]["name"] == "连续短剧"
    assert (configs[0]["scene_nums_min"], configs[0]["scene_nums_max"]) == (1, 3)


def test_active_prompts_are_unified_and_keep_consistency_memory_constraints():
    active = "\n".join([
        prompts.GENERATE_WORLD_VIEW_PROMPT,
        prompts.GENERATE_ROLE_SETTING_PROMPT,
        prompts.GENERATE_PLOT_POINT_PROMPT,
        prompts.GENERATE_OUTLINE_BY_SCRIPT_PROMPT,
        prompts.GENERATE_SCENE_OUTLINE_PROMPT,
        prompts.GENERATE_WHOLE_EPISODE_PROMPT,
        prompts.SCRIPT_FORMAT_PROMPT,
    ])
    for legacy in ("短番", "动漫类型", "秒级抓人", "腹黑总裁", "复仇女主", "台词占比不低于70%"):
        assert legacy not in active
    assert "需求树叙事记忆" in prompts.GENERATE_WHOLE_EPISODE_PROMPT
    assert "人物、关系、资产和环境当前状态" in prompts.GENERATE_WHOLE_EPISODE_PROMPT
    assert "欲望、阻力、行动和后果" in prompts.GENERATE_WHOLE_EPISODE_PROMPT
    assert "严格维护叙事连续性" in prompts.GENERATE_WHOLE_EPISODE_PROMPT
    assert "不规定固定比例" in prompts.SCRIPT_FORMAT_PROMPT


def test_public_launchers_have_no_type_selector():
    for name in ("run_60ep.sh", "run_hybrid_from_88_outline.sh", "run_shortdrama_from_88_outline.sh"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "--plot-type" not in text
        assert "--plot_type" not in text


def test_active_generation_chain_does_not_branch_on_plot_type():
    files = [
        "service/drama_by_creativity/generate_script_proposal.py",
        "service/drama_by_creativity/generate_story_outline_and_role.py",
        "service/drama_by_creativity/generate_episode_outline.py",
        "service/drama_by_creativity/generate_episode_script.py",
    ]
    for relative in files:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "request.story_info.plot_type ==" not in text
        assert "request.story_info.plot_type in" not in text
