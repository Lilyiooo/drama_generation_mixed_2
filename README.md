# Drama Generation Mixed 2

这是新版 ScriptDrama 长篇连续剧生成实验的可复现快照，包含：

- 已完成验证的生成代码：`StructuredStateMemory + hybrid retrieval + conservative_v1 scene gate`；
- 严格匹配的直接生成 baseline：每集接收当前集大纲和 baseline 自己此前生成的全部剧本原文；
- Qwen3.6-27B 生成、Qwen3.8-27B 评测所使用的代码；
- 3-run 单故事实验和 PG19 中文 12 故事实验的完整剧本、完整多 Agent 评测轨迹、评分与聚合报告。

> 本仓库只保存已经完成在线生成与评测的稳定快照，不包含后续尚未完成完整实验验证的改动。

## 方法

当前方法在新版 ScriptDrama 规划与逐集写作框架上增加：

1. **结构化状态记忆**：持续维护人物状态、人物关系、资产/物品/环境状态；
2. **Hybrid 状态检索**：结合中文词项相关性、实体/关系命中和更新时间，从完整状态库中选择本集相关状态；
3. **叙事记忆**：保留 ScriptDrama 原生的需求树/叙事记忆；
4. **场次级生成**：先生成场次大纲，再生成整集剧本；
5. **Conservative v1 gate**：只对有明确状态证据的场次冲突执行一次保守修订；不确定项不作为强制改写依据。

默认状态检索上限为 20 条、6000 字符。主要实现位于：

- `service/drama_by_creativity/structured_state_memory.py`
- `service/drama_by_creativity/narrative_memory.py`
- `service/drama_by_creativity/scene_state_gate.py`
- `service/drama_by_creativity/conservative_scene_gate.py`
- `service/drama_by_creativity/generate_episode_script.py`

## Baseline

Baseline 与当前方法严格共享世界观、人设、故事总纲和 60 集分集大纲。第 `N` 集直接由大纲生成剧本，并逐字提供该 baseline 自己此前生成的第 `1..N-1` 集全部正文。

Baseline 不使用：场次大纲 Agent、叙事记忆、结构化状态记忆、hybrid 检索、obligation memory、Strategy 卡、scene gate、桥段库检索或生成后改写。

因此，对比不是“当前方法有历史、baseline 没有历史”，而是“结构化记忆与检索/门控”对比“全部历史正文直接输入”。

## 核心结果

生成模型均为 **Qwen3.6-27B**，评测模型均为 **Qwen3.8-27B**。评测器快照位于 `evaluation/drama_evaluator_logic_quality/`。

### 新版 ScriptDrama：同一故事 3 Runs

每条轨迹 60 集；同名 run 严格配对。

| 指标 | Baseline | 当前方法 | 配对差值 | 胜负 |
|---|---:|---:|---:|---:|
| 逻辑总分 | 71.83 ± 5.39 | 82.48 ± 2.45 | **+10.65** | 3/3 胜 |
| 质量总分 | 80.13 ± 6.21 | 85.93 ± 0.80 | **+5.80** | 2/3 胜 |

| Run | Baseline 逻辑 | 当前方法逻辑 | 差值 | Baseline 质量 | 当前方法质量 | 差值 |
|---|---:|---:|---:|---:|---:|---:|
| R01 | 65.93 | 81.36 | **+15.43** | 76.80 | 86.00 | **+9.20** |
| R02 | 73.07 | 85.29 | **+12.22** | 76.30 | 85.10 | **+8.80** |
| R03 | 76.50 | 80.79 | **+4.29** | 87.30 | 86.70 | -0.60 |

详细报告：

- `results/new_scriptdrama_3run/reports/matched_baseline_comparison_summary_v24.md`
- `results/new_scriptdrama_3run/reports/matched_baseline_vs_upstream_candidate_v24.json`

### PG19 中文 12 故事

覆盖 3 个原文长度档、10 个题材聚类；每个故事生成 60 集，当前方法与 baseline 共 1440 集。

| 指标 | Baseline | 当前方法 | 配对差值 | 胜负 | 配对差 95% CI |
|---|---:|---:|---:|---:|---:|
| 逻辑总分 | 78.24 ± 6.46 | 82.86 ± 2.77 | **+4.62** | 9/12 胜 | [0.20, 9.04] |
| 质量总分 | 80.48 ± 4.97 | 88.43 ± 1.24 | **+7.95** | 12/12 胜 | [4.64, 11.26] |

按输入长度分组的逻辑差值为：

- `30k–40k`：`+8.27`；
- `60k–80k`：`+5.48`；
- `90k–120k`：`+0.11`。

这说明质量收益跨长度档稳定，而最长输入组的逻辑收益接近持平；仓库同时保留三个逻辑回归样本，便于后续分析，而不是只上传有利结果。

详细报告：

- `results/pg19_selected12/reports/pg19_candidate_vs_matched_history_baseline_v24.json`
- `results/pg19_selected12/reports/candidate_scores_v24.json`

### Generalized V3：可选场次门控

`conservative_v3` 在 V1 的结构化状态记忆与 hybrid 检索之上，为每个场次另行检索当前状态、终局历史和既定故事事实，再执行保守的场次检查与一次修订。V1 仍是默认策略；只有设置 `DRAMA_SCENE_GATE_POLICY=conservative_v3` 才启用 V3。实现位于 `service/drama_by_creativity/conservative_scene_gate_v3.py` 和 `service/drama_by_creativity/scene_gate_v3_retrieval.py`。

`pg19_gate_v3_generalized_study.sh` 使用外部提供的冻结规划资产和初始 Future Map：每个 `<sample_id>/` 下需有 `input.json`、`assets/pipeline_result.json`、`assets/generation_background.json`、`assets/03_story_outline/outline.json`、`assets/04_episode_outline/*.json`，以及 `candidate/04_future_map/{future_map,episode_contributions}.json`。脚本只复用这些输入，不复用剧本、记忆或 gate 结果。本次上传**仅包含方法代码和运行入口**；未上传新的原始创意、大纲、Future Map、剧本或评分数据。

## 仓库结构

```text
.
├── service/drama_by_creativity/       # 生成、状态记忆、hybrid 检索、conservative_v1 gate
├── tools/                             # 实验编排、恢复、导出与比较工具
├── evaluation/
│   └── drama_evaluator_logic_quality/ # 本次实际使用的评测器快照
├── results/
│   ├── new_scriptdrama_3run/          # 3-run 方法/baseline 剧本与评测
│   └── pg19_selected12/               # 12 故事方法/baseline 剧本与评测
├── pg19_selected12_study.sh
├── pg19_selected12_baseline.sh
└── upstream_matched_history_baseline.sh
```

结果目录共包含 30 份 60 集完整剧本、30 份 `scores.json`、30 份多 Agent Markdown 报告、180 份独立 reviewer 记录，以及各实验协议、冻结输入和聚合统计。详见 `results/README.md`。

## 环境

```bash
conda activate qwen36-vllm
pip install -r requirements-local.txt
export PYTHON_BIN="$(command -v python)"
export DRAMA_LLM_BASE_URL="http://127.0.0.1:8000/v1"
export DRAMA_LLM_MODEL="Qwen3.6-27B"
export DRAMA_LLM_THINKING=0
```

评测服务默认使用：

```bash
export DRAMA_EVAL_BASE_URL="http://127.0.0.1:8001/v1"
export DRAMA_EVAL_MODEL="Qwen3.8-27B"
export DRAMA_EVAL_ENABLE_THINKING=false
```

## 复现实验

PG19 当前方法：

```bash
bash pg19_selected12_study.sh prepare
bash pg19_selected12_study.sh generate --execute-api
bash pg19_selected12_study.sh evaluate --execute-api
```

PG19 严格 Baseline，应在当前方法全部完成后执行：

```bash
bash pg19_selected12_baseline.sh prepare
bash pg19_selected12_baseline.sh generate --execute-api
bash pg19_selected12_baseline.sh evaluate --execute-api
```

两套脚本默认对所有选中故事执行故事级全并发；每个故事内部按集顺序推进。失败后重跑同一命令即可恢复，已完成剧集与评分不会重复执行。

Generalized V3 的运行命令（需自行提供冻结输入，并先启动相应的 Qwen3.6 生成服务或 Qwen3.8 评测服务）：

```bash
export PG19_V3_SOURCE_ROOT=/path/to/frozen_v1_source
bash pg19_gate_v3_generalized_study.sh prepare
bash pg19_gate_v3_generalized_study.sh generate --workers 0 --execute-api
bash pg19_gate_v3_generalized_study.sh evaluate --workers 0 --execute-api
python tools/report_pg19_stage_timing.py output/pg19_gate_v3_generalized_12_frozen_map_v1
```

生成脚本将输出写入忽略追踪的 `output/`，不会覆盖 V1；`DRAMA_STAGE_TIMING=1` 记录 gate 与剧本撰写阶段耗时。没有外部冻结输入时，请勿将本仓库已有的简化结果文件误当作原始八字段集大纲。

更完整的命令和恢复语义见：

- `PG19_SELECTED12_STUDY.md`
- `UPSTREAM_MATCHED_BASELINE.md`
- `INTEGRATED_STATE_HYBRID_GATE.md`

## 评测文件说明

每个 `results/**/<case>/evaluation/` 目录包含：

- `scores.json`：最终逻辑与质量分数；
- `00_多Agent评估报告.md`：人类可读报告；
- `multi_agent_result.json`：汇总结构；
- `multi_agent/reviews/`：逻辑/质量独立 reviewer 输出；
- `multi_agent/audits/`：审核台账；
- `multi_agent/holistic_scores/`：整体评分；
- `multi_agent/arbitrations/`：仲裁记录；
- `multi_agent/manifest.json`：评测绑定信息。

## 实验边界

- 3-run 实验只有一个故事的三个随机轨迹，适合描述重复稳定性，不适合推断跨故事显著性。
- PG19 实验包含 12 个不同故事，仍属于中等规模评估。
- 当前方法不是所有样本逻辑都优于 baseline：PG19 中逻辑为 9 胜 3 负，最长输入组均值基本持平。
- 本仓库保留完整负例、原始评分和 reviewer 输出，便于复核结论。
