# E45 已知错误：前置与后置状态检查

上一轮新生成的control和constraint均3/3通过，checked没有触发修订，因此没有验证检查修订的检出能力或修复能力。
本轮固定原始失败输入，回答两个问题：检查器能否识别已知错误而不误报正确样本？把检查放在场次之后或正文之后，分别能修复到什么程度？

## 冻结资产与边界

- 沿用 `output/state_constraint_branch_e45_v1` 的冻结上下文，包含原第45集实际提示词、人设、世界观、前情和截至第44集的状态。
- 读取原始第45集错误场次JSON，验证它正是原正文生成请求使用的场次；原始错误正文仍作为后置修复的固定输入。
- 原大纲并未安排白无相活人出场。死亡约束C01来自第39集正文且已经存在于原第45集hybrid检索结果中。
- 检查器不会看到“正确/错误样本”标签、期望判定或实验组名称。
- 不重新生成世界观、大纲或前44集；不读取第45集之后的生成记忆，不写回旧剧本或旧评分。
- 这是已知失败案例的机制诊断，不是完整60集效果提升实验，也不是自动关键状态选择方案。

## 检出测试

每个run做四次Qwen3.6检查：

| 输入 | 预期 | 用途 |
|---|---|---|
| 同一份原始错误场次 | fail | 是否识别计划中的死者现实行动 |
| 同一份原始错误正文 | fail | 是否识别正文中的死者现实行动 |
| 上轮control对应run的场次 | pass | 检查误报，包括“死者留下的账本/资料”这种合法描述 |
| 上轮control对应run的正文 | pass | 检查正确正文的误报 |

总计12份检查结果，支持pass/fail/uncertain。错误场次和错误正文各重复3次，但它们仍是两个固定输入，不是6个独立错误案例。
正确场次已人工检查C01相关内容，正确正文在上轮通过Qwen3.8该约束检查；这些标签不代表文本在其他维度完全正确。
检测temperature=0，设不同seed仅用于重复检查，不保证结果不同，也不等于独立统计样本。
所有违规引用必须逐字出现在对应候选中，不能引用历史正文冒充候选证据。

## 修复位置对照

每组3run，修订及生成都用Qwen3.6，沿用原采样参数temperature=1，种子4601～4603：

| 组 | 流程 |
|---|---|
| raw_scene | 保留原错误场次，直接用原正文提示词重新生成；测试正文是否会自行纠错 |
| scene_gate | 检查原错误场次；fail/uncertain时最多修一次场次；再用原正文提示词写正文 |
| script_gate | 检查原错误正文；fail/uncertain时最多修一次完整正文 |

scene_gate修订必须保留场次数量、编号、顺序和完整字段，不能通过丢场次规避。
写正文时只替换场次输入，不再追加额外强约束提示，以隔离前置场次修复的影响。
若场次未改变，scene_gate直接复用同run的raw_scene正文，避免重复采样引入虚假的组间差异。
script_gate修订允许纠正上游场次中的错误安排，但必须保留原大纲的军饷证据、禁军倒戈和萧砚接管指挥权等任务。

检查器漏检时不根据预期标签强制重写。修订后再检查一次，即使仍fail/uncertain也保存，不无限重写、不挑最好结果。
修后场次仍被自检判fail时，也保留并继续写正文用于研究错误传播；本实验不是生产放行机制。
scene_gate与script_gate分别考察不同修复位置，未增加双重检查组，不能从本轮直接推断两者叠加收益。

## 独立评判

生成完成后切换Qwen3.8，在不提供组标签、自检结论或修订意见的情况下评判：

- 9份分组正文及1份原始正文参考：状态冲突pass/fail/uncertain、大纲完成度1～5、写作质量1～5。
- 3份scene_gate最终场次及1份原始场次参考：仅判断状态冲突。

总共14份评判。这样可以区分“修后场次仍错”“场次已改好但正文再犯错”和“正文后置修复失败”。
报告中的gate_check_kind说明Qwen3.6末次检查的是场次还是正文，不能把场次自检当成正文已经检查。
这仍是单集专门诊断，不是 `drama_evaluator` 全剧融合评分。

## 运行命令

默认独立目录：`output/state_gate_placement_e45_v2`。脚本自动使用既有qwen36-vllm环境，不必另建环境。
v1 的失败请求保留不动：模型将 JSON 人物列表改写为引文，未通过逐字证据校验。
v2 明确要求短小连续的行动/对白引文，并在格式重试中定位错误的 violations 下标与引文。
仍严格验证全部证据，不接受模糊匹配、不静默丢弃违规引用、不按预期标签强制判定；旧 constraint 实验实现不变。
提示和实现发生变化，因此使用新目录，不覆盖 v1 manifest，也不复用其失败响应作为正式结果。
准备不调用API，预计正式生成阶段15～30次Qwen3.6调用，加14次Qwen3.8评判（不含请求/格式重试）。

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
bash state_gate_placement.sh prepare
bash state_gate_placement.sh status
```

GPU机器：先停止Qwen3.8服务，等待退出释放显存，再启动八卡Qwen3.6：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 MAX_NUM_SEQS=4 PORT=8000 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/qwen36-vllm-deploy/serve.sh
```

同一GPU机器另一个终端：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash state_gate_placement.sh generate --workers 3 --execute-api 2>&1 | tee -a output/state_gate_placement_e45_v2/generation.log
```

可加 `--run R01` 先试一个run。3个run可并发，每个run内部按阶段串行。缓存绑定输入和实现哈希，失败后重跑相同命令即可。

生成完成后停止Qwen3.6，启动Qwen3.8：

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 TP_SIZE=8 MAX_MODEL_LEN=131072 PORT=8001 bash /inspire/hdd/global_user/wangqiqi-CZXS25210124/Tencent-drama/local_pipeline/serve_evaluator.sh
```

同一GPU机器另一个终端：

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
set -o pipefail; bash state_gate_placement.sh evaluate --workers 3 --execute-api 2>&1 | tee -a output/state_gate_placement_e45_v2/evaluation.log
bash state_gate_placement.sh report
```

`inputs.json`与`manifest.json`保存冻结输入和实验协议；`generation/Rxx`保留检查、单次修订和请求失败日志；
`scenes/`与`variants/`保存场次和正文；`evaluation/`保存盲评；`summary.json`由report生成。
status为只读，不调用模型、不更新实验结果。
