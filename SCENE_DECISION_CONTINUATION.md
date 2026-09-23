# R02/R03 续跑与三轮合并

本入口保留 `scene_gate_decision_v2` 及元数据恢复目录中的 R01 全部36项结果，只运行 R02/R03：18案例 × 2组 × 2run = 72项新的Qwen3.6检查。R01不重新抽样。

案例、初始提示词、输入上下文、temperature=0、输出上限4096及检查分类规则不变。候选组在线接入与R01离线恢复相同的元数据兼容函数，接受character_state等已知状态字段名，保留原值及兼容记录，不猜测domain。M/S编号、跨场次引用、结构组合和覆盖校验仍严格执行。

格式反馈仅在 memory_conflicts 的状态编号校验失败时补充说明：历史M与候选场次S冲突不等于历史内部两条M记录互斥；不得编造第二条M。新入口、兼容记录和反馈变化都有独立实现绑定，报告区分R01保留结果与后两轮在线兼容结果，不隐瞒原始格式失败。

本轮仍只检查，不自动改场次或生成正文，不改生命周期记忆。R01离线恢复和后两轮在线接受在错误处理流程上不同，因此原始格式成功率应分轮报告；同输入初始prompt的判定结果可以并列分析。3 run是重复性诊断，不是3份独立故事。

默认目录：`output/scene_gate_decision_v2_continued/`。冻结原始案例和R01汇总，原始文件保持不变；完成结果缓存可续跑。

## 运行（每条命令一行）

保持Qwen3.6服务运行即可，包装脚本使用已有conda环境。

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash continue_scene_gate_decision.sh run --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_decision_v2_continued/generation.log
bash continue_scene_gate_decision.sh status
bash continue_scene_gate_decision.sh report
```

run同时调度R02和R03，workers限制总并发为3，不是每轮各3。原命令重复执行只请求尚未完成的项，语义fail/uncertain也算有效完成，不重抽答案。无--execute-api仅列出任务，不调用API。

初始应显示两组各18/54（R01各18/18），pending=72；全部完成后两组各54/54，合计108/108。新status/report同时汇总R01–R03，不再以旧入口的严格格式计数作为合并进度。

如果需要重新启动Qwen3.6，先停掉占用同八卡的其他模型服务，再在服务终端执行：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

## 后续独立复核

先综合三轮Qwen3.6结果；如需独立复核，停止Qwen3.6并启动Qwen3.8。新evaluate统一覆盖三个run，每个案例/run只检查一次，共54项；不提供Qwen3.6答案或预设标签。复核是独立模型意见，不是整剧drama_evaluator分数或金标准。

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
```

另一个终端：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash continue_scene_gate_decision.sh evaluate --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_decision_v2_continued/evaluation.log
bash continue_scene_gate_decision.sh report
```

本轮新增入口不要与旧run入口同时使用。部署时仅准备文件、离线验证，真实GPU检查由用户在GPU机器运行。
