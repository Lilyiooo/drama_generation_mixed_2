# ScriptPipeline：真实生成资产 → 初始状态 → 生命周期与 hybrid

## 真实生成时的数据传递

1. 剧本策划阶段生成世界观、人设，立即保存原始 JSON 和格式化后的 `01_script_proposal/story_assets.json`。
2. 这些实际生成的设定进入故事总纲请求。总纲返回时保留世界观、人设，并保存 `03_story_outline/story_assets.json`。
3. 分集大纲生成结束，进入剧本阶段时，把当前请求的世界观、人设、总纲和全部分集大纲原样保存为 `generation_assets.json`。
4. 状态模块接收这份资产快照，由 Qwen3.6 建立第一集开场前的九类初始状态。代码为本次世界观、人设的原文片段编号，模型只返回状态条目和证据编号，代码回填逐字证据并严格校验，不接受模型拼接省略或改写的引文。最多32条初始状态，每条最多80字、1至4个证据编号。
5. 后续每集从最终正文抽取增量，合并并清理已完成目标、已揭晓未知和被推翻事实；下一集使用 hybrid 检索视图。

所有初始条目、引用证据及资产哈希保存在 `state_lifecycle/<story_id>/initial_state.json`；
该目录下的 `story_assets.json` 保存原始资产。总纲与后续分集大纲作为作者计划保留；
初始化只用总纲和首集大纲辅助判断开场边界，不能把未来结婚、死亡、身份揭露等事件提前记入历史或角色已知信息。

## 接入方式

直接复用 Tencent-drama 的 `local_pipeline/gated_engine.py` 中的 `merge_state`、`apply_lifecycle`，
以及 `local_pipeline/state_retrieval.py` 的 `select_state`。
状态模块不生成义务记忆或经验卡。原生 Future Map/FD/World State、前情摘要和上一集原文仍照常工作。
新增状态视图同时进入场次大纲和正文 prompt；它结合 BM25、近期性、字段权重和固定项优先级，
压缩 JSON 不超过6000字符。该预算只限制新增状态块，不限制整个 prompt。

初始化和逐集抽取都使用 Qwen3.6、temperature=0；失败最多三次尝试，输出上限依次为4096、8192、8192。
初始状态每次调用的证据目录和逐次响应保存在 `state_lifecycle/<story_id>/initialization_attempts/<唯一编号>/`，不会覆盖以前的失败日志。
失败时停止推进并保留产物。`state_hybrid_study.sh` 的恢复入口可补抽取已经保存的剧本。

## 全流程在剧本阶段失败后续跑

不要重新执行 `run_60ep.sh`：它会从策划开始。用下面入口复用失败运行中实际保存的
`generation_assets.json`、同一 story_id 下的状态资产和静态 Future Map，从初始化/剧本阶段继续。
默认目录为 `output/full_pipeline_state_hybrid_v2`，story_id 为 `APID-test-001`；可通过 `--run-dir`、`--story-id` 指定。
该入口只适用于这里的60集 SHORT_CARTOON 实验，沿用原来的每集1000至1400字配置。
不重新生成人设、世界观或大纲，也不拷贝别的运行历史；已保存的正文只补缺失的记忆更新。
不要同时运行原启动命令和恢复命令。默认只读检查，必须加 `--execute-api` 才会请求模型。

```bash
bash resume_state_hybrid.sh
bash resume_state_hybrid.sh --limit 2 --execute-api
bash resume_state_hybrid.sh --execute-api
```

`--limit 2` 表示完成至第2集，后续不带 limit 的命令接着完成至第60集。

## 固定大纲的试验

默认从已经完成的 `output/full_pipeline_qwen36_1run` 读取其真实生成时保存的
`pipeline_result.json` 中的策划和总纲响应，以及同轮分集大纲、静态 Future Map。
这允许复用这轮生成资产；不复制其剧本或动态历史。实验目录改为 `output/state_lifecycle_hybrid_v2`，
之前只准备了空状态方案的 v1 目录不再使用。

默认生成 `hybrid` 一组60集、一个run。可选 `native_context` 组使用相同保存设定和原生流程，
用于分离“设定恢复”与“新增状态记忆”的影响。

```bash
bash state_hybrid_study.sh prepare
bash state_hybrid_study.sh generate --limit 2 --execute-api
bash state_hybrid_study.sh generate --execute-api
bash state_hybrid_study.sh status
bash state_hybrid_study.sh evaluate --execute-api
```

上述每条命令各占一行。生成需8000端口Qwen3.6，评测切换到8001端口Qwen3.8。
加 `--arm native_context` 可运行对照。评测仍使用 Tencent-drama 的 drama_evaluator。

## 从创意重新完整生成

在 Qwen3.6 服务就绪、qwen36-vllm 环境中，也可以直接启用同一接入点：

```bash
DRAMA_STATE_LIFECYCLE_HYBRID=1 DRAMA_LLM_MODEL=Qwen3.6-27B DRAMA_LLM_TIMEOUT=600 DRAMA_OUTPUT_DIR="$PWD/output/full_pipeline_state_hybrid_v2" bash run_60ep.sh
```

这个入口会重新生成人设、世界观和大纲，再自动用本次产出初始化状态；不读取上一轮运行目录。
评测可使用 `tools/evaluate_with_drama_evaluator.py`，传入对应输出目录并加 `--execute-api`。
