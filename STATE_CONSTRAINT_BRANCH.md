# 第45集状态执行诊断实验

目的：定位“死亡事实已抽取、已检索，但正文仍让死者参与现实行动”的生成失效。
这是根据既有失败案例选择的局部诊断，不是完整60集消融，也不能从3次生成推断总体显著性。
不修改已有完整剧本、状态或评测结果，不在本实验中更新后续集数记忆。

## 固定输入与实验组

从 `output/full_pipeline_state_hybrid_v2` 冻结第45集当时真正发送给模型的场次和正文请求参数及模板。
包括当时已有的原生记忆、hybrid状态视图、近期摘要、上一集正文、人设与世界观。
原生场次请求本来包含相邻集大纲，这些作者计划保持不变；不读取第45集以后生成的正文或最终第60集记忆。
原正文请求中的旧场次大纲被移除，每个分支必须使用自己新生成的场次大纲。
原第45集正文只作为单独的历史失败参考，不能进入新生成请求。

三组各3次（R01～R03），所有生成和自检均用 Qwen3.6：

| 组 | 实验处理 |
|---|---|
| control | 原始场次/正文提示词，重新生成 |
| constraint | 与control相同输入，场次和正文请求末尾追加显式状态约束及冲突优先级 |
| checked | 复用constraint同一次原始草稿，检查后至多重写一次；不独立另抽一份草稿 |

显式约束 C01 来自本轮第39集实际正文中的白无相死亡事实，并验证它已经出现在原第45集hybrid输入中。
本次人为选择这一条已证实失败的约束以隔离“提示位置/执行”的影响，尚未实现可泛化的自动关键状态选择器。
约束区分现实行动和允许的死者提及、遗物、遗留关系网、明确标注的回忆/笔记画外音，禁止新造复活或替身来规避。

control和constraint使用相同的三个种子4501～4503、原采样参数（temperature=1），但相同seed不保证GPU推理逐位确定。
checked通过自检时保留原草稿原文；不通过或不确定时只重写一次。
若重写后仍失败，保存失败正文和检查结论，不反复生成直到成功，也不挑最好样本。

## 评判与保存

切换 Qwen3.8 后对9份实验正文及1份原始参考正文做隐藏组名的单集判断。
模型只能看到历史证据、本集大纲、上一集正文、约束和候选正文，看不到实验组标签和Qwen3.6自检结论。
这个分组盲法不能消除模型从文本本身推测处理方式的可能。

主要指标是状态冲突 pass/fail/uncertain；辅以大纲完成度和写作质量（分别1至5分）。
所有冲突证据都必须是候选正文的连续原文；不能因死者名字出现就自动判失败。
这个专门诊断并非原 `drama_evaluator` 的60集融合评分，不应与72.88等全剧分数横向混用。

默认输出：`output/state_constraint_branch_e45_v1`。
`inputs.json`、`manifest.json`保存冻结输入、源文件哈希、实现哈希与分组映射。
`generation/`保存每阶段原始响应、自检和重写；`variants/`保存9份候选；`evaluation/`保存盲评；`summary.json`保存汇总。
每个请求的失败响应保留在独立 attempts 目录；续跑复用校验通过的阶段，输入改变时拒绝复用。
API/结构失败最多3次重试，不根据内容好坏重抽。并发仅用于互相独立的分支，不并发推进同一故事的集数。

## 命令（每条一行）

准备和只读检查不需要GPU：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
bash state_constraint_branch.sh prepare
bash state_constraint_branch.sh status
```

先停止占用八卡的Qwen3.8服务，在GPU机器一个终端启动生成服务：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

另一个终端执行生成（wrapper自动使用既有qwen36-vllm环境的python）：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash state_constraint_branch.sh generate --workers 3 --execute-api 2>&1 | tee -a output/state_constraint_branch_e45_v1/generation.log
```

可加 `--run R01` 先跑一个run；后续不加该参数会复用已完成部分，补齐3run。
正常首次生成约15至21次模型调用（不含格式/API重试），随后10次Qwen3.8诊断评判。

生成完成后停止Qwen3.6服务，再启动评测服务：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
```

另一个终端执行：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash state_constraint_branch.sh evaluate --workers 3 --execute-api 2>&1 | tee -a output/state_constraint_branch_e45_v1/evaluation.log
bash state_constraint_branch.sh report
```

失败时重跑相同命令；不要删除成功结果，也不要同时在多个终端执行同一任务。
只有该诊断验证约束执行有效且不明显损伤大纲/质量后，再考虑同大纲的完整故事原生对照及长程接入实验。
