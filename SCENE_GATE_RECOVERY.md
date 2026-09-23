# 多类型门控校准：证据引用补跑

## 本次发现

原实验 `output/scene_gate_multitype_v1` 在第二轮尝试后，完成 33/42，独立复核 0/42。剩余任务为 `life_legal`、`real_e45_conflict`、`real_e45_clean` 的各 3 run，共 9 个。

失败原因不是日志显示的 GPU 显存或并发错误，而是检查返回的引文不是指定场次字段中的连续原文：含 JSON 字段名、跨字段拼接、添加省略号，或引用了大纲而非候选场次。temperature=0 下，笼统的格式反馈也反复得到同样的错误。此前另一个知识案例曾输出过长而截断，第二轮已经得到有效结构结果。

完成不等于判断正确：原结果中，资源补给和现场获知信息这 6 个合法变化任务都被首次检查误判为 fail；12 个状态歧义任务也全部被判为 fail 而非预设的 uncertain。这些是语义问题，不作为接口失败重新抽样。合成模板里的出场名单、地点和动机也可能引入干扰，后续应单独复核测试设计；本轮不得改输入后仍声称同一实验。

## 补跑做了什么

- 不改旧的 gate、runner、冻结案例、结果或失败日志；原入口的 status 仍如实显示 33/42。
- 只对原先没有有效 outcome 的 9 个任务，使用独立的引用协议重新请求 Qwen3.6。
- 程序从候选场次的情节概要、主要情节、冲突与张力机械生成 S 编号；模型选择状态 M 编号和场次证据 S 编号，程序映射回准确的原文与所属场次，再通过原有严格引文校验。
- 不模糊匹配、不删除不合规冲突来凑 pass、不改变预期标签，也不对已有的语义失败进行补抽样。
- 检查要求简短理由，避免将长篇反复推演写入 JSON。修订仍至多一次，修订后 fail 或 uncertain 仍阻断；阻断属于已完成的诊断。
- 补跑实现及其请求有独立绑定；报告明确区分 `original_quotes` 与 `recovery_span_ids`，不能把两种协议混在一起当作同一算法的正式准确率。

新目录：`output/scene_gate_multitype_recovery_v1/`。`manifest.json` 固定来源文件哈希、成功／待补跑分组及实现哈希；不要再同时运行旧的生成补跑命令。如果原结果改变，补跑脚本会拒绝混用。

生产生成端仍默认关闭门控，没有借此次接口恢复悄悄更新正式门控实现。

## GPU 机器命令

Qwen3.6 服务已启动时，不必重启。所有命令均为单行；包装脚本直接使用现有 conda Python。

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash repair_scene_gate_calibration.sh run --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_multitype_recovery_v1/generation.log
bash repair_scene_gate_calibration.sh status
```

预期进度从 `original_retained=33 recovered=0/9 complete=33/42` 到 `original_retained=33 recovered=9/9 complete=42/42`。`scored` 统计新目录内的独立复核，不代表旧目录里的旧评测数。

如需启动生成模型，在另一个终端运行：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

补跑完成后，先停止 Qwen3.6 服务，再启动八卡 Qwen3.8：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
```

另一个终端执行复核：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash repair_scene_gate_calibration.sh evaluate --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_multitype_recovery_v1/evaluation.log
bash repair_scene_gate_calibration.sh report
```

这个 evaluate 对保留的 33 项和恢复的 9 项统一使用证据编号协议进行 Qwen3.8 前／后复核（最多 84 个首次检查请求，另有必要的格式/API 重试）。它不会重新生成成功场次。结果写入新目录 `judges/`；`summary.json` 保留每项生成协议及判断。该一致性复核仍不是 drama_evaluator 的整剧质量分。

`status` 只读；`run`/`evaluate` 不加 `--execute-api` 不调用服务。接口／结构失败可重跑同一条新命令；语义阻断不通过重跑自动重新采样。代码修复经过离线模拟测试，真实模型对新协议的遵循程度仍需此次 GPU 补跑验证。
