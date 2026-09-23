# 状态门控：判定协议配对实验 v2

## 本轮边界

本轮仅校准检查器，**不生成正文、不修订场次、不修改历史状态，也不启用正式生成门控**。目的是先解决前轮发现的判定可靠性问题，再考虑把修订接回长剧流程。旧实验及其失败、误报完整保留。

前轮观察到：Qwen3.6 的理由末尾表示无冲突，但 JSON 开头仍写 fail；合法的资源补给／现场获知被判冲突；矛盾记忆被当作确定事实；修订有时新增资金、身份和机关绕过原问题。因此当前不通过重复抽样、加修订次数或重写旧标签来提高通过率。

## 两组与新协议

- `control_indexed`：上一轮补跑的证据编号协议，在本轮相同输入上重新检查。
- `candidate_factorized`：新协议，先判断具体证据的状态基础、与动作的关系和是否存在合法转换，再由程序汇总。

两组都使用 Qwen3.6-27B、temperature=0、同样的本集大纲、上一集正文、状态视图、场次原文和证据编号。检查请求上限4096输出tokens；结构/API错误最多3次，缓存及失败原文均保留。3 run 是重复性诊断，不是3份独立故事，尤其temperature=0时结果可能相同。

候选模型不输出自由的顶层 status，必须覆盖所有场次。程序根据合法的结构化组合生成分类：

| 分类 | 条件 | 汇总行为 |
| --- | --- | --- |
| hard_conflict | 相关状态明确、行动互斥、没有合法转换 | fail，标记为待修订候选，但本轮不执行修订 |
| legal_transition | 状态兼容，原文展示合法转换 | pass，保留 |
| no_conflict | 兼容或没有特定历史限制 | pass，保留 |
| memory_conflict | 相关历史记录相互矛盾，至少引用两条状态 | uncertain，核实记忆 |
| insufficient_evidence | 关键状态或适用性不明 | uncertain，核实证据 |

一般写作建议单独放 `writing_notes`，不影响判定。与矛盾记忆重叠的状态不能同时被当作确定冲突依据；但不依赖这些矛盾记录的其他硬冲突仍可判 fail。

这能保证结构化字段与**程序汇总结果**一致，不能保证模型填写的字段或自然语言理由一定正确。引用真实也不等于证明充分；不使用“理由里有无冲突”这样的关键词自动替换判定。语义正确性仍须人工检查及独立复核。

## 测试集与来源

共18案例 × 2组 × 3 run = **108个Qwen3.6检查任务**。

- 16个新版受控合成案例：死亡、道具、资源、认知四类，每类包括硬冲突、合法行为、同一时点记忆矛盾、关键证据不足。
- 合法死亡案例的名单不再包含死者；典当案例明确当铺、铺主、所有权和资金交付；开门案例明确在门外获知口令再进入。
- 这些是新测试输入，不能与旧模板的结果直接拼成统一准确率。旧检查器和新检查器都在这份相同的新输入上重新运行。
- 2个真实E45场次原文、检索视图及生成参数保持原样，用作复杂场景诊断。移除其整体pass/fail金标准：过去的clean仅验证死亡动作问题，不代表全部139条状态均无问题。真实案例不进入受控标签命中率。
- expected_status、expected_kind、来源类型及案例名不进入模型请求。标签用于实验报告，而非提示模型答案。

默认输出：`output/scene_gate_decision_v2/`，`cases.json`和`manifest.json`冻结案例及实现哈希。

## 执行命令（每条一行）

已有Qwen3.6服务运行时不必重启。脚本直接使用原conda环境，不需另建环境。

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash scene_gate_decision_study.sh run --run R01 --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_decision_v2/generation.log
bash scene_gate_decision_study.sh status
```

建议先完成R01的36个检查，确认真实模型能遵循协议，再去掉`--run R01`完成剩余72项。已有有效缓存不重复调用：

```bash
set -o pipefail; bash scene_gate_decision_study.sh run --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_decision_v2/generation.log
```

如需启动Qwen3.6，请先停掉占用同八卡的另一服务，然后在服务终端运行：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

## 独立复核

完成选定run的两组检查后可切换Qwen3.8。模型只看原始输入，不看Qwen3.6判断、分组或预设标签，使用相同的结构化分类协议。

因为两组没有改写场次，每个案例/run只需一次复核，共54项，而非重复检查两次。它是独立模型意见，**不是金标准，也不是drama_evaluator整剧质量分**；使用相同协议仍可能共享判断偏差。

先在原服务终端Ctrl+C停止Qwen3.6，再启动：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
```

另一个终端：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash scene_gate_decision_study.sh evaluate --workers 3 --execute-api 2>&1 | tee -a output/scene_gate_decision_v2/evaluation.log
bash scene_gate_decision_study.sh report
```

若只完成R01，两组复核命令也要加`--run R01`。`status`只读；`report`写`summary.json`；`run`与`evaluate`不加`--execute-api`不会调用API。API/格式失败可原命令续跑，语义判定无论pass/fail/uncertain都视作已完成，不自动重抽。

## 接下来怎样决定

先比较同输入下合法变化误报、硬冲突漏报、记忆矛盾与证据不足的分流，以及格式失败率；检查真实E45的证据是否真的支持判定。若通过，再单独研究受限修订，要求不新增无依据的既往资金／身份／道具路径，并评估剧情保留程度。记忆条目的时间版本／替代关系另开实验，不在本轮悄悄删除旧记忆。
