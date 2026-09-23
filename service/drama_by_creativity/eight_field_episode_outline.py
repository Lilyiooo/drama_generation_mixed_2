"""八字段逐集大纲：阶段生成、三轮一致性审校与完整重写、评分择优。"""
from .stage_episode_planning import generate_stage_episode_outlines
from .episode_outline_review import review_episode_outlines

FIELDS = {'episode_id', 'title', 'core_plot', 'roles', 'highlights',
          'character_growth', 'relationship_changes', 'main_storyline_progression'}
EXAMPLE = """[
 {"episode_id": 1, "title": "本集标题", "core_plot": "本集核心剧情，约200字，写清具体行动与结果",
  "roles": ["人物姓名"], "highlights": "本集看点和名场面",
  "character_growth": "人物成长或心理变化", "relationship_changes": "人物关系变化",
  "main_storyline_progression": "主线推进"}
]"""
EPISODE_PROMPT = """{{RoleDescription}}

请将当前阶段的详细事件列表扩展为第{{StartEpisodeId}}集至第{{EndEpisodeId}}集的逐集大纲。全剧共{{TotalEpisodeNums}}集。

题材：{{Topic}}
世界观：{{WorldView}}
核心创意：{{StoryOutline}}
人物设定：{{RoleInfo}}

全剧阶段及集数范围：{{StageRanges}}
当前阶段：{{StageName}}
当前阶段的详细事件列表：{{Outline}}
当前阶段的篇幅分配依据：{{PacingReason}}
已经确定的前序逐集大纲：{{EpisodeOutline}}

要求：
1. 主线必须沿当前阶段事件列表展开。可以适度填充合理支线、行动过程与人物互动，但不得提前完成当前阶段事件后继续写后续阶段内容，更不得挪用后续阶段的主线事件。
2. 在展开当前阶段事件时，自然承接前序集的人物处境、关系、知情状态、事件结果、物品归属和未解决冲突。任何变化都要有触发过程，避免人物行为、地点时间或情节事实突然跳变。
3. 每集写清人物因何采取什么行动、受到什么阻碍、作出什么选择并造成什么结果。合理控制推进速度和整体叙事节奏，不机械平均事件，也不重复已经完成的事件。
4. `core_plot`保留具体行动与结果；其他字段必须与`core_plot`中实际发生的事情一致。人物成长和关系变化没有实质变化时，也要准确描述其当前延续状态，不得编造变化。
5. 集号严格从{{StartEpisodeId}}连续到{{EndEpisodeId}}，不缺集、不重复。

仅输出JSON数组。每集必须且只能包含以下八个字段：
""" + EXAMPLE

EIGHT_REVIEW_PROMPT = """你是一位非常严格的全剧叙事一致性审校编辑。请通读全部逐集大纲，只围绕叙事一致性提出问题、修改建议并打总分。本轮不重写。
故事基本信息：
{{Background}}
总集数：{{Total}}
当前完整逐集大纲：
{{Original}}

评审范围：
1. 检查人物身份、亲属关系、生死、伤病、能力、动机、知情状态及关系变化是否前后连续；人物行动是否符合前文建立的人物状态和已经建立的设定，是否存在逻辑矛盾或情节事实冲突，以及时间、地点等背景状态信息是否存在冲突。
2. 检查事件起因与结果、时间顺序、地点移动、世界规则、权力状态、重要道具与证据的获取、持有和使用是否自洽，已完成事件是否被无交代地重置或重复为首次发生。
3. 检查相邻集及远距离事件是否自然衔接，以及同一集内部、各字段之间是否矛盾。人物成长、关系变化、主线推进和看点必须与core_plot中的实际事件一致。
4. 问题必须有当前大纲依据，说明涉及集数、相关情节、矛盾或缺失的衔接及影响。区分明确矛盾和必要交代缺失；合理省略、悬念和符合既定世界规则的行为不直接当作矛盾。可以概述证据，不要求逐字引用。
5. 仅以叙事自洽为修改目标，不因爽感、文风、新颖性、商业性、节奏快慢或个人剧情偏好提出修改或加减分。伏笔仅检查它的前后信息与因果是否自洽。必要时可建议联动调整多集，避免只修措辞或改完一处又制造另一处矛盾。

评分标准：
总分total_score为0—100的数值，只根据有依据的一致性问题的数量、严重程度和影响范围评分。
严重：关键身份、生死、核心设定或主线因果直接冲突，影响多集理解或后续事件成立。
一般：局部状态、证据流转或跨集衔接有明显缺口，需要补充事件或修改局部剧情才能合理。
轻微：局部指代或交代含混，只需少量澄清即可理解，不影响主要事件成立。
同一根源问题跨多集出现时合并为一项，在严重程度与影响范围中体现，不能拆成多项重复扣分。
100分：未发现有依据的一致性问题。
90—99分：只有少量轻微问题；75—89分：有少量一般问题或多处轻微问题，无严重问题；
60—74分：有一项严重问题或多项一般问题；40—59分：有多项严重问题，显著破坏人物或主线连续性；
0—39分：严重矛盾广泛存在，核心叙事难以自洽。同一区间内，问题越多、影响越广，分数越低。
总分必须与列出的问题及其严重程度相匹配。在overall_assessment中说明各等级问题数量和主要扣分依据。每次按相同标准评价当前文本。
{% if RetryFeedback %}上次输出校验反馈：{{RetryFeedback}}{% endif %}
只输出JSON对象：
{
 "total_score": 80,
 "overall_assessment": "一致性结论、各严重程度问题数量与扣分依据",
 "issues": [
  {"issue_id": "I01", "severity": "一般", "category": "人物状态一致性",
   "episode_ids": [1, 2], "evidence": [{"episode_id": 1, "summary": "相关情节概述"}],
   "problem": "具体矛盾或必要衔接缺口", "impact": "对前后事件成立的影响",
   "recommendation": "修正建议与需要联动处理的情节"}
 ],
 "revision_strategy": "如何统一状态、修复因果与衔接，并保持已有有效情节"
}
无问题时issues输出空数组。
"""

EIGHT_REWRITE_PROMPT = """你是全剧大纲修订编剧。依据评审意见核对并修复当前大纲的叙事一致性，输出完整{{Total}}集大纲。
故事基本信息：
{{Background}}
当前完整逐集大纲：
{{Original}}
评审意见：
{{Review}}

修订要求：
1. 核对评审问题是否有原文依据，修复人物身份、状态、关系、动机、知情程度、世界设定、时间地点、道具证据、事件因果和跨集衔接中的矛盾。缺乏依据的意见不强行采纳。
2. 保留主要人物、核心故事、有效事件与重要线索。允许为消除不一致而对部分集进行较大范围的重组、增删或替换，并同步处理前后影响；修改以解决一致性问题为目的。
3. 若发现评审未提出的其他叙事不一致，也应一并解决。把修复落实为具体情节，不用声称“逻辑自洽”代替事件解释。各字段与本集core_plot及前后集实际内容一致。
4. 总集数保持{{Total}}，episode_id从1到{{Total}}连续。每集core_plot约200字，保留具体行动和结果，后半段也保持细化程度。输出全部集数，包括无需修改的集。
{% if RetryFeedback %}上次输出校验反馈：{{RetryFeedback}}{% endif %}
只输出JSON数组，每集必须且只能包含示例中的八个字段：
""" + EXAMPLE


def validate_eight_fields(episodes, start, end):
    # Reuse established nine-field validation with a temporary compatibility value.
    # The actual model result must contain exactly eight fields and is never altered.
    from service.drama_by_creativity.stage_episode_planning import validate_episode_batch
    if not isinstance(episodes, list):
        raise ValueError('逐集大纲必须是JSON数组')
    for episode in episodes:
        if not isinstance(episode, dict) or set(episode) != FIELDS:
            raise ValueError('每集必须且只能包含episode_id、title、core_plot、roles、highlights、character_growth、relationship_changes、main_storyline_progression')
    validate_episode_batch([dict(ep, ending_hook='仅供兼容校验') for ep in episodes], start, end)


async def review_eight_fields(ctx, episodes, story, plan, common):
    return await review_episode_outlines(ctx, episodes, story, plan, common,
        batch_validator=validate_eight_fields, review_prompt=EIGHT_REVIEW_PROMPT,
        rewrite_prompt=EIGHT_REWRITE_PROMPT)


async def generate_eight_fields(ctx, story, total, common, unused_prompt=None):
    return await generate_stage_episode_outlines(ctx, story, total, common, EPISODE_PROMPT,
        batch_validator=validate_eight_fields, review_callback=review_eight_fields)
