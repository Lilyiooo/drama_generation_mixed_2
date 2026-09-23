# 场次大纲状态门控与多类型校准

## 目的与接入位置

这是生成端的可选模块，不是修改 drama_evaluator 的评分规则。

流程为：本集大纲 → 原有生命周期状态及 hybrid 检索 → 场次大纲 → **状态一致性检查／至多一次修订／复查** → 剧本正文 → 原有记忆更新。

检查使用本集真正检索到的九字段状态视图、前集正文和本集大纲，不额外读取全量状态作为答案。状态引用有编号，冲突必须引用候选场次中的连续原文。没有检索到不等于事实不存在；目标未完成不等于状态冲突。模块不增加义务记忆或 Strategy 卡，也不删除 ScriptPipeline 原有的叙事记忆。

生成侧检查和修订固定使用 `Qwen3.6-27B`。独立复核使用 `Qwen3.8-27B`，但只是本轮一致性校准，**不是完整剧本的 drama_evaluator 质量评分**。

## 开关与安全边界

`DRAMA_SCENE_STATE_GATE` 默认 `off`：不新增模型请求。

- `audit`：仅记录检查结果，不修改或阻断场次。
- `enforce`：`pass` 直接放行；`fail` 修订一次并复查；`uncertain` 或修订后仍不通过，则阻止正文生成及后续记忆更新。
- 非 `off` 必须同时启用 `DRAMA_STATE_LIFECYCLE_HYBRID=1`。
- 只在全新输出目录中启用；禁止向已经开始的无门控剧本中途添加门控，也禁止在同一有门控目录切换模式或实现版本。
- 原始场次、输入、检查、修订和复查会冻结落盘，续跑复用验证通过的缓存。格式/API 失败最多尝试三次，附具体错误提示；不通过反复抽样把语义失败“刷成通过”。
- 正式生成中的 `SceneGateBlocked` 是需要分析的真实阻断，不能忽略后继续写下一集。校准实验为了收集所有案例，会将这种阻断记为一个已完成的诊断结果。

主要实现：`service/drama_by_creativity/scene_state_gate.py`；接入：`generate_episode_script.py`。正式生成日志位于对应输出目录的 `scene_state_gate/<StoryID>/E##/`。

## 本轮测试集

默认目录：`output/scene_gate_multitype_v1/`。

| 来源 | 案例数 | 设计 |
| --- | ---: | --- |
| 真实保存的生成结果 | 2 | 原始 E45 错误场次、先前独立重生成的正确场次；使用当时完整检索视图 |
| 受控合成案例 | 12 | 死亡、道具销毁、资源耗尽、角色认知四类，每类包含明确冲突、合法场内变化、历史状态互相矛盾 |

每例运行 R01–R03，共 **14 个不同案例、42 个任务**。真实两例来自同一 E45 背景；重复运行不是新的独立样本。受控案例不是已经观察到的自然错误，不能据此宣称真实长剧错误率下降。初始检查 temperature=0，重复结果可能相同；修订 temperature=1。

预期标签只用于统计，不进入模型检查或修订请求。含互相矛盾状态的案例预期 `uncertain`，拒绝强行修复才是合适行为；不能只看最终放行率。

这轮应关注：冲突识别、合法变化误报、不确定性处理、修复后是否仍冲突，以及独立 Qwen3.8 判断。通过后才开展相同世界观／人设／大纲的长剧配对实验，比较“原 hybrid”与“hybrid + 场次门控”，再用原 drama_evaluator 评完整剧本。

## GPU 机器命令（每条一行）

共享目录和脚本已准备好；本地无 GPU，不在准备阶段发起模型请求。切换模型前先在原服务终端 Ctrl+C，避免两个八卡服务抢显存。

启动 Qwen3.6（一个终端，保持运行）：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

另一个终端运行校准。包装脚本使用已有 qwen36-vllm 环境的绝对 Python 路径，无需迁移或重新创建环境：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
bash scene_gate_calibration.sh status
set -o pipefail; bash scene_gate_calibration.sh run --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_multitype_v1/generation.log
```

可先给 `run` 命令加 `--run R01`，只完成 14 个任务；之后去掉该参数续上全部。这里的 `run` 仅检查／修订冻结的场次，不生成新的一整部 60 集剧本。

生成侧完成后，停止 Qwen3.6，启动 Qwen3.8：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
```

另一个终端执行独立复核：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash scene_gate_calibration.sh evaluate --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_multitype_v1/evaluation.log
bash scene_gate_calibration.sh report
```

API／结构失败可原命令续跑；已有有效阶段缓存会保留。`status` 只读、不调 API；`report` 另外写 `summary.json`。`complete` 表示获得有效诊断，不代表全部 `pass`；`blocked` 应结合 expected 标签解读。

`cases.json` 为冻结测试集，`manifest.json` 记录来源及实现哈希；`cases/<case>/<run>/` 下保存原场次、检查、修订及复核，`attempts/` 保留重试原文。禁止修改已冻结测试集后沿用同一输出目录。

准备全新校准目录可使用 `bash scene_gate_calibration.sh prepare --root <新目录>`；之后所有命令都应指定相同 `--root`。

## 局限

模型检查不是形式化事实证明。当前引用校验只保证编号存在和引文真实，不能保证模型推理正确；这正是独立复核和人工检查的必要性。检索漏掉关键事实时模块也可能漏检。历史状态同时保留互相矛盾的描述时，模块可能阻断，需要分析状态抽取／生命周期，而不是放宽判断掩盖问题。

本轮没有声称修复后对白、可拍性、剧情丰富度不下降；这些需后续正文配对实验与原评测体系验证。暂不在已完成的长剧结果中开启门控，也不改写旧分数。
