# 完整 60 集场次门控 A/B 实验

## 比较什么

| 分组 | 共同生成框架 | 唯一区别 |
| --- | --- | --- |
| `control_hybrid` | ScriptPipeline 原生叙事记忆 + 单状态生命周期 + hybrid 检索 | 不启用场次门控 |
| `candidate_gate` | 与对照相同 | 最新因子化检查 + 硬冲突一次修订 + 复查 |

生成、状态抽取、检查和修订均用本地 **Qwen3.6-27B**。最终完整剧本用原来的 **drama_evaluator + Qwen3.8-27B** 评测，不新增评分规则。这里优化的是生成，不是用 Qwen3.8 帮忙生成。

从 `output/full_pipeline_state_hybrid_v2` 固定实际生成并保留的世界观、人设、总纲、60 集大纲、静态 Future Map 和 episode contributions，同时复用有来源证据且通过校验的开场状态。不会重新编造人设，也不会把来源剧本、旧动态记忆或未来集的状态复制进实验。

每条轨迹从第 1 集开始重新写剧本，自行更新原生记忆和生命周期状态。仍保留原有前一集正文、上下文和生成 prompt；不加入义务记忆或经验卡，不修改 hybrid 检索预算与清理规则。世界观/角色/生成参数在 A/B 间相同，但不是使用相同随机流的确定性配对。

默认先做 **R01：两组各 60 集，共 120 集**。目录预留 R02/R03，但不会默认调用它们。R01 确认后显式扩展为 2 组 × 3 run × 60 集 = 360 集。同一故事的三个采样 run 不能等同于三个独立故事。

## 门控策略

1. 场次大纲先生成并冻结，再检查本次实际 hybrid 检索的九字段状态视图；不是偷偷给门控读取全量状态。
2. 无冲突、合法转变：不修订。
3. 历史状态自身冲突、证据不足：记录不确定，保留原始场次，不强行补写。
4. 有独立证据的硬冲突：最多一轮语义修订，只处理硬冲突，不把写作建议当修订目标。保持场次数量、编号、结构与本集核心任务；禁止编造过去的资源、身份和事件。
5. 修订后复查通过才采用；仍冲突或不确定则回退到冻结的原始场次，记录 `fallback_to_original` 和 `unresolved`，不中断整部剧本。
6. API 错误、JSON/证据/结构校验失败不是语义不确定：重试耗尽后停止该轨迹，不能伪装成通过或悄悄回退。重跑时复用已验证的请求缓存；不会重复进行已完成的语义修订。

这是保守的研究方案，不保证消灭所有逻辑错误。它只检查场次大纲，不是最终正文的全面逻辑验证；状态缺失和错误记忆仍可能造成漏检/误检。最终是否提升必须看完整剧本的同协议 A/B 分数。

## 一行一条命令

进入目录并启用现有环境（不迁移环境）：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
source /inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/etc/profile.d/conda.sh && conda activate qwen36-vllm
mkdir -p logs
set -o pipefail
bash full_scene_gate_study.sh status
```

首次准备，纯离线，无模型请求，已有目录不会被覆盖：

```bash
bash full_scene_gate_study.sh prepare
```

GPU 机器上，终端 A 启动生成服务。已有同一 Qwen3.6 服务则无需重复启动：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

终端 B，建议先每组生成前两集，然后原地续跑完整 R01：

```bash
bash full_scene_gate_study.sh generate --run R01 --limit 2 --workers 2 --execute-api 2>&1 | tee -a logs/full_scene_gate_smoke.log
bash full_scene_gate_study.sh generate --run R01 --workers 2 --execute-api 2>&1 | tee -a logs/full_scene_gate_generation.log
bash full_scene_gate_study.sh status --run R01
```

每组完成必须同时具备正文、原生记忆更新、生命周期更新。失败后重跑同一命令，保留已完成正文；已有正文但抽取未完成时只恢复抽取。两个并发是两个独立进程内的完整轨迹；每条轨迹的集数仍严格顺序执行，避免环境变量及记忆互相串用。

R01 两组均达到 `episodes=60/60` 后，在终端 A 对生成服务按 Ctrl+C，等显存释放，再启动评测服务（不要让两个八卡服务同时占用同一组 GPU）：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
```

终端 B 启动相同协议的完整剧本评测与汇总：

```bash
bash full_scene_gate_study.sh evaluate --run R01 --workers 2 --execute-api 2>&1 | tee -a logs/full_scene_gate_evaluation.log
bash full_scene_gate_study.sh report --run R01
```

评测内部 review/audit/arbitration workers 沿用各 3，外层并发 2；Qwen3.8 温度固定 0、不启用 thinking。若显存/吞吐紧张可降低外层 workers，不变更评分协议。

确认 R01 后，再切回 Qwen3.6 服务并显式生成其他 run；`--all-runs` 自动跳过 R01 已完成部分：

```bash
bash full_scene_gate_study.sh generate --all-runs --workers 2 --execute-api 2>&1 | tee -a logs/full_scene_gate_generation.log
```

之后切回 Qwen3.8：

```bash
bash full_scene_gate_study.sh evaluate --all-runs --workers 2 --execute-api 2>&1 | tee -a logs/full_scene_gate_evaluation.log
bash full_scene_gate_study.sh report --all-runs
```

## 产物与解释

实验目录：`output/full_scene_gate_ab_v1/`。

- `manifest.json`、`frozen_inputs.json`：分组、策略、源资产、共享开场状态和实现哈希；代码/资产变化会拒绝混跑。
- `<arm>/<run>/05_drama/episode_*.json`：本组实际生成的正文。
- `<arm>/<run>/state_lifecycle/`、`narrative_memory/`：独立演化的动态记忆。
- `candidate_gate/<run>/scene_state_gate/<story_id>/E*/`：原始场次、检查、修订、复查、采用/回退结果、每次失败的请求和原始响应。
- `<arm>/<run>/drama_evaluations_qwen38/full_60_episodes/`：原始评测输出，绑定完整正文摘要；不复用旧版本的评分。
- `reports/R01.json` 或 `reports/R01_R02_R03.json`：三维融合分、同 run 的候选减对照、修订次数、回退数、未解决数。
- `logs/`：每条轨迹追加写入的独立日志；根目录的执行锁防止重复启动同一实验。

先看逻辑得分改善是否伴随质量/创意损失，再看各 run 一致性、修订率、回退率和典型错误。不应根据旧单次得分或局部检查通过率宣称完整剧本提升。
