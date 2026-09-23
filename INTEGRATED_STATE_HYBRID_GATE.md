# 新版 ScriptPipeline StructuredStateMemory Hybrid 与 Scene Gate 集成

## 目录与版本

- 保留的旧工作目录：`/inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline`
- 新版集成目录：`/inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922`
- 上游基线：`rimory6/ScriptPipeline` 的提交 `695e0df`
- 集成分支：`integrate-state-hybrid-scene-gate`

旧目录没有被重命名、覆盖或清理，已有输出与恢复任务仍可使用。

## 集成行为

新版原生流程保持不变，包括统一短剧 Prompt、真实世界观与人设传递、Future Map、未来分集核心情节约束和原生结构化状态记忆。

正式方法直接使用新版仓库提交 `695e0df` 自带的 `StructuredStateMemory` 和 Hybrid 检索。旧九字段 `StateLifecycleMemory` 仅保留用于历史实验复现，正式启动脚本会显式设置 `DRAMA_STATE_LIFECYCLE_HYBRID=0`，不会让旧状态模块替换新版实现。

增强路径包括：

1. 每集生成前，新版状态模块从人物、人物关系、资产/物品/环境三类当前快照中，使用中文 BM25、实体/关系命中和更新时间进行 Hybrid 检索。
2. 检索结果进入新版 Prompt 的 `StateMemory` 专用槽；当前集未命中的状态不会进入上下文，但仍完整保存在状态快照中。
3. 每集生成后，新版状态抽取器以增量 `patch` 更新受影响属性，并通过 `delete` 与主体删除字段清理已经失效的状态；未受影响状态逐字保留。
4. `DRAMA_SCENE_STATE_GATE=enforce` 且 `DRAMA_SCENE_GATE_POLICY=conservative_v1` 时，我们的 Gate 直接消费新版 Hybrid 检索选出的 `selected` 证据记录，并绑定 `state_sha256`、集号和状态更新时间，保证检查证据来自当前集生成前的确切新版状态快照。
5. V1 Gate 对新版检索证据进行因子化硬冲突判定，最多执行一次保守修复并复核；修复未通过时回退原场次而不是阻断整集。
6. 世界观、人设、总纲和分集大纲固定写入 `generation_assets.json`。
7. Gate 输入、检查、修复与结果均可恢复；新版状态更新、摘要和 Hybrid 检索审计分别保存在 `structured_state/` 下。

## 启动环境

```bash
source /inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/bin/activate qwen36-vllm
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
```

## 启动 Qwen3.6 服务

在 GPU 机器执行：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy && bash serve.sh
```

服务健康检查：

```bash
curl -s http://127.0.0.1:8000/v1/models
```

## 运行完整 60 集增强方法

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && RUN_ID=mixed_R01 bash run_60ep_state_hybrid_gate.sh
```

指定不同输出与 API：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && RUN_ID=mixed_R01 DRAMA_LLM_BASE_URL=http://127.0.0.1:8000/v1 DRAMA_LLM_MODEL=Qwen3.6-27B bash run_60ep_state_hybrid_gate.sh
```

使用早期 Gate 做审计但不修改场次：

```bash
DRAMA_SCENE_STATE_GATE=audit DRAMA_SCENE_GATE_POLICY=legacy RUN_ID=mixed_audit bash run_60ep_state_hybrid_gate.sh
```

只使用新版 StructuredStateMemory Hybrid、不启用 Gate：

```bash
DRAMA_SCENE_STATE_GATE=off DRAMA_SCENE_GATE_POLICY=legacy RUN_ID=mixed_hybrid_only bash run_60ep_state_hybrid_gate.sh
```

完全使用新版原生算法时，不使用该包装脚本，运行：

```bash
RUN_ID=upstream_native DRAMA_LLM_MODEL=Qwen3.6-27B PYTHON_BIN=/inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/envs/qwen36-vllm/bin/python bash run_60ep_qwen36_27b.sh
```

## 关键输出

- `generation_assets.json`：本轮真实世界观、人设、总纲和分集大纲。
- `structured_state/<story_id>/state_memory.json`：新版人物、关系、资产当前状态快照及历史更新。
- `structured_state/<story_id>/retrieval/`：新版每集 Hybrid 检索结果、选中证据和状态快照哈希。
- `structured_state/<story_id>/updates/`：新版每集增量 patch、删除项与应用后的状态。
- `scene_state_gate/<story_id>/`：Gate 输入、检查、修复和最终结果。
- `05_drama/`：逐集剧本。

## 验证

```bash
conda run -n qwen36-vllm python -m unittest discover -v service/drama_by_creativity/tests 'test_*.py'
```

当前集成验证结果为 109 个测试通过，3 个依赖历史输出目录的夹具测试跳过；根目录全部 Shell 脚本通过 `bash -n`。
