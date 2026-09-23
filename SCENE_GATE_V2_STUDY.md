# Scene Gate V2：质量保真门控实验

## 目的

在固定的单状态生命周期与 Hybrid 检索框架上，比较新的质量保真门控与已经冻结的
`control_hybrid`、`candidate_gate` 三次 60 集结果。生成模型保持为 Qwen3.6-27B，评测模型保持为
Qwen3.8-27B，且不加入义务记忆或 Strategy 卡。

V1 三个 Run 共检查 180 集，但只有 3 集真正改写。因此 V1 与 Control 的整条轨迹分差不能全部解释为
门控因果效应。本实验会把这 3 个真实干预案例冻结在 `intervention_audit.json` 中，同时运行三条新的
V2 完整轨迹，分别报告两类证据。

## V2 策略

1. 继续使用已有的因子化证据检查器，只有 `hard_conflict` 才会干预。
2. `resource`、`knowledge`、`location`、`relationship` 等可在正文中合法解决的问题，不改写已有场次字段，
   只新增 `状态一致性执行约束`，要求正文在冲突动作前展示合法转换，否则不得执行该动作。
3. `life` 和 `object` 等不可逆冲突才进入最小改写。
4. 最小改写必须逐字保留核心功能、人物动机与目标、冲突与张力、悬念钩子；不能修改无关场次；
   全集场次 JSON 的文字变化比例不能超过 20%。
5. 最小改写复检失败时回退原始场次，并把冲突转为正文硬约束，不使用第二轮自由改写。

## 准备

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
bash scene_gate_v2_study.sh prepare --all-runs
bash scene_gate_v2_study.sh status --all-runs
```

准备阶段不调用 API。默认输出目录：

```text
output/scene_gate_v2_quality_preserving
```

## 生成

先启动 Qwen3.6-27B 服务，再执行：

```bash
mkdir -p logs
bash scene_gate_v2_study.sh generate --all-runs --workers 3 --execute-api 2>&1 | tee -a logs/scene_gate_v2_generation.log
```

命令可安全重跑：每个 Run 有独立锁，已完成的剧集、剧本、双套记忆和门控结果会保留。

如果某个 Run 因门控 JSON 的 `scene_id`、`domain` 或记忆冲突引用格式失败，先执行版本化恢复器：

```bash
bash recover_scene_gate_v2.sh recover --all-runs --workers 2 --execute-api
```

恢复器只做两类操作：根据已引用的 S 证据确定性绑定完整场次编号/合法 domain，或把上一份无效响应及
严格校验错误反馈给 Qwen3.6 后重新输出完整判断。它不会修改已生成剧本、状态记忆、证据、分类或实验输入。
恢复成功后重新执行原生成命令即可从断点继续。

若一条长轨迹可能多次遇到同类格式失败，可以让恢复与续跑自动交替：

```bash
RUN=R01 MAX_ROUNDS=20 bash resume_scene_gate_v2.sh
```

脚本只会恢复当前未完成门控并从已有剧集断点继续；不会重新生成已经完成的剧集。

建议先冒烟：

```bash
bash scene_gate_v2_study.sh generate --run R01 --limit 2 --workers 1 --execute-api
```

## 评测

停止生成服务并启动 Qwen3.8-27B 评测服务后执行：

```bash
bash scene_gate_v2_study.sh evaluate --all-runs --workers 3 --execute-api 2>&1 | tee -a logs/scene_gate_v2_evaluation.log
```

评测固定采用 `drama_evaluator_logic_quality` v2.4 参数：direct 300000 字符、chunk 100000 字符、
24576 输出 token，review/audit/arbitration 各 2 并发，1200 秒超时，3 次 API 与格式重试。

## 汇总

```bash
bash scene_gate_v2_study.sh report --all-runs
```

报告写入：

```text
output/scene_gate_v2_quality_preserving/reports/R01_R02_R03.json
```

报告会同时列出 V2 分数、冻结的 V1/Control 分数、差值、约束注入次数、最小改写次数、回退次数与
未预期冲突数。完整轨迹不是同随机流，差值只做描述统计；真实 V1 干预路由审计单独保存在：

```text
output/scene_gate_v2_quality_preserving/intervention_audit.json
```
