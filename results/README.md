# Results

本目录保存已经完成生成和 Qwen3.8-27B 多 Agent 评测的两组严格配对实验。

## `new_scriptdrama_3run/`

- `our_method/R01..R03/`：新版 ScriptDrama + StructuredStateMemory + hybrid retrieval + conservative_v1 gate。
- `baseline/R01..R03/`：共享同名 run 的规划资产，每集直接输入当前大纲与 baseline 自己此前的全部剧本。
- `protocols/`：baseline 协议以及三个 run 的冻结生成资产。
- `reports/`：逐 run 与总体配对比较。

每个 run 目录包含：

```text
Rxx/
├── full_60_episodes.txt
└── evaluation/
    ├── scores.json
    ├── 00_多Agent评估报告.md
    ├── multi_agent_result.json
    └── multi_agent/
```

## `pg19_selected12/`

- `our_method/<sample_id>/`：12 个当前方法结果。
- `baseline/<sample_id>/`：12 个严格匹配 baseline 结果。
- `shared_inputs/<sample_id>/input.json`：冻结的中文创意输入。
- `shared_inputs/<sample_id>/generation_assets.json`：双方共享的世界观、人设、故事总纲及分集大纲。
- `shared_inputs/pipeline_inputs_zh.jsonl`：runner 默认读取的原始 12 条输入，SHA-256 为 `dff1530a6e55df4600ac980362b6fb24c7857228108ffa409e2accfe87ba2376`。
- `protocols/`：双方实验协议。
- `reports/pg19_candidate_vs_matched_history_baseline_v24.json`：逐故事、分长度档和总体配对统计。

## 完整性

| 项目 | 数量 |
|---|---:|
| 60 集完整剧本（V1 与 baseline） | 30 |
| `scores.json`（V1 与 baseline） | 30 |
| 多 Agent Markdown 报告 | 30 |
| 独立 reviewer JSON | 180 |

这里没有只挑选高分或获胜样本。PG19 中当前方法逻辑低于 baseline 的 `idea_pg19_18579`、`idea_pg19_41542` 和 `idea_pg19_22060` 也完整保留。

## 路径说明

原始协议和报告中可能保留生成机器上的绝对路径。这些路径用于记录当时的运行绑定；仓库内对应文件已经按本目录的相对路径重新整理。分数、文本和 SHA-256 内容未修改。
