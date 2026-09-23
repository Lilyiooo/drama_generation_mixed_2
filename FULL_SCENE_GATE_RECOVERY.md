# 完整剧本门控实验：引用校验恢复 v1

## 修复范围

R01 对照组已完成 60 集；候选组完成 8 集，第 9 集在场次门控的 `check_before` 阶段失败。三次响应均未满足 `conflicting check must cite a complete declared memory_conflicts group`。

原重试只有简短错误，没有返回上一份无效回答和不匹配的组/检查编号。恢复入口把原始响应、声明的组、具体 conflicting 检查和引用编号一并反馈给模型，要求重新依据原有证据判断。明确区分历史 M 与 M 的矛盾、历史 M 与候选 S 的互斥、普通转场/铺垫不足。

**不自动补编号、不自动删除冲突、不强制改判通过，不放宽校验器。** 合法响应仍由原 `compatible_validate` 和原分类映射验证。每次仍最多三次 schema/API 尝试，失败后停止，不能伪装成语义不确定或成功。

## 保留与版本记录

- 原生成代码、门控规则、校验器、修订策略、评测器、实验 manifest 及代码哈希均不修改。
- 使用新增 `tools/recover_full_scene_gate.py` 和启动脚本；原 `full_scene_gate_study.sh status` 仍可用。
- 恢复前给已有正文、生命周期记录、门控输入/结果/失败响应建立哈希保护；原生可变记忆另存快照。
- 第 9 集复用已经冻结的场次大纲，不重新生成该场次，不改写之前八集。
- 已验证的旧检查缓存照常复用；新检查结果用 `check_before_check_feedback_v1.json` 等独立文件名保存，旧失败尝试不覆盖。
- 第 9 集首次恢复请求带有绑定原输入的失败反馈；之后新集的首次检查保持原始 prompt，只有校验失败后才增加详细反馈。
- 新结果在 outcome 中标记 `recovery_protocol=check_feedback_v1`。这是**保留原 R01 前缀的恢复实验**，不应宣称整条 R01 从第一集就用了改进后的反馈。后续 R02/R03 可单独 prepare 后从头使用同一恢复入口。
- 不改变 A/B 组的故事、人设、大纲、检索预算、记忆清理规则或评测口径。

## GPU 机器执行：一行一条

进入项目，保证 Qwen3.6-27B 服务在端口 8000（如果已启动，不要重复启动）：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
source /inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/etc/profile.d/conda.sh && conda activate qwen36-vllm
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

另一个终端进入相同目录；准备只做离线核查与快照，可重复执行：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
mkdir -p logs
set -o pipefail
bash recover_full_scene_gate.sh prepare --run R01
bash recover_full_scene_gate.sh generate --run R01 --workers 2 --execute-api 2>&1 | tee -a logs/full_scene_gate_recovery.log
```

对照组 60 集自动跳过，候选组从第 9 集续跑到第 60 集。若要先只验证第 9 集，把生成命令加上 `--limit 9`；成功后执行不带该限制的完整命令。失败后重跑**新的恢复命令**，不要退回旧生成入口。

```bash
bash recover_full_scene_gate.sh status --run R01
bash recover_full_scene_gate.sh report --run R01
```

两组均完成 60 集后，停掉 Qwen3.6 服务并启动 Qwen3.8，再执行原评测命令：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
bash full_scene_gate_study.sh evaluate --run R01 --workers 2 --execute-api 2>&1 | tee -a logs/full_scene_gate_evaluation.log
```

恢复版本记录和日志：`output/full_scene_gate_ab_v1/recovery/check_feedback_v1/R01/`。

本次代码测试使用模拟模型响应；不代表真实模型一定一次通过。真实执行仍会记录全部失败，而不是跳过证据审查。
