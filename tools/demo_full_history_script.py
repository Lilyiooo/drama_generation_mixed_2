"""逐集整集生成 baseline：当前大纲 + 故事背景 + 全部前集原文。"""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drama_local.runtime import Context, atomic_json
from service.drama_by_creativity.local_llm import LLM
from service.drama_by_creativity.utils import get_model_config
import jinja2

DEFAULT_SOURCE = ROOT/'output/qwen36_27b_eight_fields_demo_20260916_060508_407704'
PROMPT = """你是一位专业中文短剧编剧。根据本集大纲和此前全部剧本，直接创作第{{EpisodeNumber}}集的完整剧本，全剧共{{Total}}集。

故事基本信息：
{{Background}}

此前所有集的完整剧本（按集号顺序，第一集时为空）：
{{History}}

当前集大纲：
{{Outline}}

要求：
1. 主线沿本集大纲展开，将事件写成具体行动、阻力、选择与结果；允许合理补充细节，不提前推进到本集范围以外的主线事件。
2. 承接前文的人物身份、状态、关系、知情程度、时间地点、证据与事件结果，保持叙事一致。已发生的事件不要重新写成首次发生，不重复上一集已经演完的剧情；必要的过渡自然融入行动。
3. 输出可拍摄的剧本，使用场次编号、地点、时间、人物、动作与对白。人物情绪和关系通过具体行动与对白体现。
4. 正文目标为{{MinChars}}—{{MaxChars}}个中文字符。只输出当前集完整正文，不输出分析、梗概、JSON或前面各集正文。
"""


def load_inputs(source):
    episodes = json.loads((source/'episode_outlines.json').read_text())
    if not isinstance(episodes, list) or not episodes:
        raise ValueError('逐集大纲必须是非空数组')
    for i, ep in enumerate(episodes, 1):
        if not isinstance(ep, dict) or type(ep.get('episode_id')) is not int or ep['episode_id'] != i:
            raise ValueError(f'大纲集号必须连续，当前位置应为{i}')
        for key in ('title', 'core_plot'):
            if not isinstance(ep.get(key), str) or not ep[key].strip():
                raise ValueError(f'第{i}集缺少{key}')
    background = json.loads((source/'generation_background.json').read_text())
    background = {k: background[k] for k in ('Topic', 'WorldView', 'StoryOutline', 'RoleInfo') if background.get(k)}
    return episodes, background


def history_text(scripts):
    return '\n\n'.join(f'===== 第{i}集完整剧本 =====\n{text}' for i, text in enumerate(scripts, 1))


async def generate(out, episodes, background, model, min_chars, max_chars):
    scripts = []
    files = sorted((out/'05_drama').glob('episode_*.json'))
    expected = [f'episode_{i:02d}.json' for i in range(1, len(files)+1)]
    if [f.name for f in files] != expected or len(files) > len(episodes):
        raise ValueError('已有剧本不连续，禁止跳集续跑')
    for i, f in enumerate(files, 1):
        record = json.loads(f.read_text())
        if record.get('episode_number') != i or not isinstance(record.get('content'), str) or not record['content'].strip():
            raise ValueError(f'已保存第{i}集无效')
        scripts.append(record['content'])
    for ep in episodes[len(scripts):]:
        i = ep['episode_id']
        params = dict(EpisodeNumber=i, Total=len(episodes), Background=json.dumps(background, ensure_ascii=False),
                      History=history_text(scripts), Outline=json.dumps(ep, ensure_ascii=False),
                      MinChars=min_chars, MaxChars=max_chars)
        folder = out/'episode_calls'/f'episode_{i:02d}'
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'prompt.txt').write_text(model.template.render(**params), encoding='utf-8')
        started = time.monotonic()
        atomic_json(out/'status.json', dict(status='running', current_episode=i, completed_episodes=len(scripts)))
        # Adapter saves every raw response and rejects truncation. Never shorten history or skip a failed episode.
        ret = await model.request(Context(), params, f'full_history_ep{i:02d}')
        if not isinstance(ret.response, str) or not ret.response.strip():
            raise ValueError(f'第{i}集返回空正文')
        atomic_json(out/'05_drama'/f'episode_{i:02d}.json', dict(episode_id=i-1, episode_number=i,
                    content=ret.response, elapsed_seconds=time.monotonic()-started, usage=getattr(ret, 'usage', {}),
                    history_episodes=len(scripts), history_characters=len(params['History'])))
        scripts.append(ret.response)
        print(f'第{i}/{len(episodes)}集完成，历史输入{len(params["History"])}字符，耗时{time.monotonic()-started:.2f}秒', flush=True)
    (out/'script.txt').write_text(history_text(scripts), encoding='utf-8')
    return len(scripts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--resume', action='store_true', help='配合已有 --output-dir，从最后成功集继续')
    parser.add_argument('--prepare-only', action='store_true', help='只保存输入及模板，不调用模型')
    parser.add_argument('--min-chars', type=int, default=1200)
    parser.add_argument('--max-chars', type=int, default=2200)
    args = parser.parse_args()
    if not 0 < args.min_chars <= args.max_chars:
        parser.error('字数范围无效')
    if args.resume and not args.output_dir:
        parser.error('--resume 需要 --output-dir')
    episodes, background = load_inputs(args.source_dir.resolve())
    config = get_model_config('script_model')
    model = LLM(**{k: config[k] for k in ('model','system_prompt','temperature','top_p','top_k','max_length','max_new_tokens')}, template=jinja2.Template(PROMPT))
    settings = dict(model=model.model, url=model.url, temperature=model.temperature, top_p=model.top_p,
                    top_k=model.top_k, max_tokens=model.max_tokens, thinking=model.thinking, system_prompt=model.system_prompt)
    contract = dict(episodes=episodes, background=background, prompt=PROMPT, min_chars=args.min_chars, max_chars=args.max_chars, settings=settings)
    fingerprint = hashlib.sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    out = (args.output_dir or ROOT/'output'/('qwen36_27b_full_history_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))).resolve()
    if args.resume:
        if not out.is_dir(): raise ValueError('续跑目录不存在')
    else:
        out.mkdir(parents=True, exist_ok=False)
    with (out/'.run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.resume:
            if json.loads((out/'manifest.json').read_text())['fingerprint'] != fingerprint:
                raise ValueError('大纲、背景、提示词或模型设置发生改变，拒绝混合续跑')
        else:
            atomic_json(out/'manifest.json', dict(source_dir=str(args.source_dir.resolve()), fingerprint=fingerprint, **contract))
            atomic_json(out/'episode_outlines.json', episodes)
            (out/'prompt_template.txt').write_text(PROMPT, encoding='utf-8')
            (out/'05_drama').mkdir()
        os.environ['DRAMA_OUTPUT_DIR'] = str(out)
        print(f'输出目录：{out}\n接口：{model.url}；模型：{model.model}\n大纲集数：{len(episodes)}；每集输入此前全部正文', flush=True)
        if args.prepare_only:
            print('输入准备完成，未调用模型；运行时使用相同 --output-dir 并加 --resume。')
            return
        started = time.monotonic()
        try:
            completed = asyncio.run(generate(out, episodes, background, model, args.min_chars, args.max_chars))
        except BaseException as error:
            atomic_json(out/'status.json', dict(status='failed', error=f'{type(error).__name__}: {error}',
                        completed_episodes=len(list((out/'05_drama').glob('episode_*.json'))),
                        elapsed_seconds_this_run=time.monotonic()-started))
            raise
        atomic_json(out/'status.json', dict(status='complete', completed_episodes=completed,
                    elapsed_seconds_this_run=time.monotonic()-started))
        print(f'完成，共{completed}集，本次耗时{time.monotonic()-started:.2f}秒。')


if __name__ == '__main__':
    main()
