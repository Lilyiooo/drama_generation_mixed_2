# R01 元数据兼容恢复（离线）

原始 `scene_gate_decision_v2` 的 R01 共36项：control完成18项，candidate完成13项，剩余5项。R02/R03尚未启动，不属于失败。

主要问题是模型在domain字段返回了状态字段名character_state或resources_and_evidence，而原校验只允许life、object等分类名；报错没有给出具体非法值与可选项，重试重复同样输出。这一domain字段不参与程序的最终状态汇总，实际汇总仅依据state_basis、scene_relation、transition及证据约束。

## 恢复边界

- 不改旧实现、旧提示词、旧结果、失败日志，也不重抽模型答案。
- 只接受已知九个状态字段名作为额外的元数据命名空间，不猜测character_state应当是life、location还是其他类别。
- 校验时将该描述性字段投影为other，随后保留模型原domain值并标记domain_namespace=state_field。其余全部字段仍通过原验证器：状态/场次编号、覆盖率、状态矛盾组、转换关系、理由长度都不放宽。
- 严禁把场次S编号当成历史M编号，严禁将“历史与候选场次冲突”自动改成“历史内部矛盾”。遇到这些错误的原始尝试仍拒绝。
- 按原始尝试文件的时间顺序取第一份只需上述元数据兼容、且其余结构完整有效的回包，不根据pass/fail或预期标签选择答案。
- 校验原请求的模型、输入、提示词、实现绑定、采样和输出上限。被截断或API失败的回包不能通过此恢复路径接受。
- 保存选中的原始文本、来源文件、哈希、兼容项及此前被拒绝的尝试。已完成任务保持原样；模型调用次数为0。

真实错误E45的一份尝试曾混淆M与S编号，应继续拒绝；已有另一份回包正确识别硬冲突，仅domain不合规，可以恢复。恢复并不代表判断与预设标签一致：object_missing仍会按原模型判断保留pass，不能把它改成预期的uncertain。

恢复目录：`output/scene_gate_decision_v2_metadata_recovery`。

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
bash recover_scene_decision_metadata.sh status
bash recover_scene_decision_metadata.sh report
```

首次恢复由`bash recover_scene_decision_metadata.sh recover`执行，只读原结果并写新目录，无需启动模型。report写入新目录的summary.json。所有命令均使用现有conda Python。

原`scene_gate_decision_study.sh status`仍显示原始严格格式完成数，这是故意保留的运行记录；R01合并完整度以新的status为准。**恢复兼容后完成率与原始严格格式成功率必须分别报告**，不能据此声称原始协议一次运行全部成功。

本次只恢复R01用于分析，不修改生产门控或删除记忆。暂不启动R02/R03或旧evaluate命令；后续应先审阅R01，再以明确版本的元数据兼容协议安排后续实验。该补丁解决格式阻塞，不验证模型语义正确性。
