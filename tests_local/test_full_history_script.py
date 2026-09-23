import asyncio
import json
from types import SimpleNamespace
import jinja2
import pytest
from tools.demo_full_history_script import generate, PROMPT, history_text


def test_history_and_resume_after_failure(tmp_path):
    (tmp_path/'05_drama').mkdir()
    eps = [dict(episode_id=i, title='标题', core_plot='剧情') for i in range(1,4)]
    seen = []
    class Model:
        template = jinja2.Template(PROMPT)
        async def request(self, ctx, params, rid):
            seen.append(params)
            if params['EpisodeNumber'] == 3:
                raise RuntimeError('context too long')
            return SimpleNamespace(response=f"第{params['EpisodeNumber']}集原文\n完整保留", usage={})
    with pytest.raises(RuntimeError):
        asyncio.run(generate(tmp_path, eps, {}, Model(), 1200, 2200))
    assert seen[0]['History'] == ''
    assert seen[1]['History'] == history_text(['第1集原文\n完整保留'])
    assert seen[2]['History'] == history_text(['第1集原文\n完整保留', '第2集原文\n完整保留'])
    assert len(list((tmp_path/'05_drama').glob('*.json'))) == 2
    class Resume(Model):
        async def request(self, ctx, params, rid):
            assert params['EpisodeNumber'] == 3
            assert params['History'] == seen[2]['History']
            return SimpleNamespace(response='第三集正文')
    assert asyncio.run(generate(tmp_path, eps, {}, Resume(), 1200, 2200)) == 3
    assert '第三集正文' in (tmp_path/'script.txt').read_text()
    assert json.loads((tmp_path/'05_drama/episode_03.json').read_text())['history_episodes'] == 2


def test_rejects_gap(tmp_path):
    (tmp_path/'05_drama').mkdir()
    (tmp_path/'05_drama/episode_02.json').write_text('{}')
    with pytest.raises(ValueError, match='不连续'):
        asyncio.run(generate(tmp_path, [dict(episode_id=1)], {}, None, 1200, 2200))
