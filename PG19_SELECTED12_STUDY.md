# PG-19 中文 12 故事泛化实验

## 目标

- 输入：`selected_chinese_12/pipeline_inputs_zh.jsonl` 中冻结的 12 条中文创意。
- 覆盖：3 个原文长度档，每档 4 条；10 个题材聚类。
- 每个故事：60 集、1 条轨迹。
- 当前方法：新版 ScriptDrama + `StructuredStateMemory` + hybrid 检索 + `conservative_v1` scene gate。
- 严格 baseline：复用对应当前方法生成的世界观、人设、故事总纲和 60 集分集大纲；每集只输入该集大纲与此前所有 baseline 剧本原文。
- 生成：Qwen3.6-27B；评测：Qwen3.8-27B 与 `drama_evaluator_logic_quality` v24。

12 个不同故事用于估计跨故事泛化，不再对同一故事做 3 次随机重复。当前方法与 baseline 合计生成 `12 × 2 × 60 = 1440` 集。

## 当前方法

准备并核验冻结输入，不调用模型：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_study.sh prepare
```

生成全部 12 个故事。默认故事级全并发，即 12 个故事同时推进；vLLM 自行排队：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && mkdir -p logs && bash pg19_selected12_study.sh generate --execute-api 2>&1 | tee -a logs/pg19_selected12_candidate_generation.log
```

状态：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_study.sh status
```

只跑一个样本的 2 集 smoke test：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_study.sh generate --sample idea_pg19_13114 --limit 2 --execute-api 2>&1 | tee -a logs/pg19_selected12_smoke.log
```

评测全部当前方法输出：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_study.sh evaluate --execute-api 2>&1 | tee -a logs/pg19_selected12_candidate_evaluation.log
```

汇总：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_study.sh report
```

## 严格匹配 Baseline

baseline 的 `prepare` 会冻结当前方法的生成资产，因此应在 12 个当前方法故事全部达到 60/60 后运行。

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_baseline.sh prepare
```

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_baseline.sh generate --execute-api 2>&1 | tee -a logs/pg19_selected12_baseline_generation.log
```

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_baseline.sh status
```

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_baseline.sh evaluate --execute-api 2>&1 | tee -a logs/pg19_selected12_baseline_evaluation.log
```

严格 baseline 的评测完成后会自动生成逐故事配对比较报告；也可手动重建：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922 && bash pg19_selected12_baseline.sh report
```

配对报告固定包含逐故事差值、三个输入长度档的分组结果、总体均值、样本标准差、候选方法胜/平/负数量，以及 12 个配对故事均值差的 95% t 置信区间。报告路径：

```text
output/pg19_selected12_matched_history_baseline_v1/reports/pg19_candidate_vs_matched_history_baseline_v24.json
```

## 恢复语义

- 所有命令都保留成功结果；失败后重跑同一条命令即可续跑。
- 当前方法按每个故事的 `narrative_memory` 与 `structured_state` 一致进度恢复。
- baseline 校验此前每集正文、历史哈希和 prompt 哈希后，从连续前缀的下一集恢复。
- 已存在的 `scores.json` 会跳过，不重复评测。
