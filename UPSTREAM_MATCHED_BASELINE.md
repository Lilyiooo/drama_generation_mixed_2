# 新版 ScriptDrama 严格配对 Baseline

## 目的

本实验为 `new_scriptdrama_structured_hybrid_gate_R01/R02/R03` 分别构造同资产、同分集大纲的直接生成 baseline。

每个 baseline run 只使用同名 candidate run 的以下冻结输入：

- 世界观；
- 人物设定；
- 故事总纲；
- 当前集分集大纲；
- 该 baseline 自己此前已经生成的全部剧本原文。

Baseline 不读取 candidate 剧本正文，也不使用场次大纲 Agent、叙事记忆、状态周期记忆、hybrid 检索、义务记忆、Strategy 卡、状态门控、桥段检索或生成后改写。

本次 candidate 的世界观字段本来就是空字符串。Baseline 按 run 原样冻结该字段，不额外生成或补写世界观，以保证配对公平。

## 输出目录

`output/new_scriptdrama_matched_direct_history_baseline_v1`

其中 `protocol.json` 保存完整实验协议、每条 source run 路径、资产 SHA256、模型参数、随机种子和排除模块；`frozen_sources` 保存逐 run 冻结资产。

## 生成

Qwen3.6-27B 服务运行在 `http://127.0.0.1:8000/v1` 时执行：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && mkdir -p logs && bash upstream_matched_history_baseline.sh generate --execute-api 2>&1 | tee -a logs/upstream_matched_baseline_generation.log
```

三个 run 默认全部并发；每个 run 内部必须按集顺序串行，因为第 N 集需要该 baseline 的第 1 至 N-1 集完整原文。失败后重复同一命令即可从连续前缀恢复。

## 状态

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash upstream_matched_history_baseline.sh status
```

`history_audit=True` 表示每一集的提示词哈希、历史剧本哈希和输出哈希均通过审计。

## 评测

生成完成、切换为 Qwen3.8-27B 服务并监听 `http://127.0.0.1:8001/v1` 后执行：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash upstream_matched_history_baseline.sh evaluate --execute-api 2>&1 | tee -a logs/upstream_matched_baseline_evaluation.log
```

评测使用与 candidate 相同的 `drama_evaluator_logic_quality`、模型、direct context、字符上限、chunk、输出上限、超时及重试参数，并使用 evaluator 默认内部并发。

评测全部完成后会自动生成配对报告：

`output/new_scriptdrama_matched_direct_history_baseline_v1/reports/matched_baseline_vs_upstream_candidate_v24.json`

也可单独重新生成报告：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash upstream_matched_history_baseline.sh report
```
