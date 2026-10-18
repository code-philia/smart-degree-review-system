# 真实 API 冒烟与在线开关验收（非正式300样本实验）

日期：2026-10-19。生产服务未切换。本目录/记录证明真实调用与执行路径，不能作为正式论文的300 mutant结果。

- 自然语言到任务规划：`planning-smoke/task/plan.json`，目标范围和变异指导由API生成，未人工提供target_kinds；只用于入口验证，未改变正在准备的正式任务。
- 初稿执行失败→真实API修订→新代码重执行：`smoke/actual-api-repair.json`。最初程序没有返回诊断列表；修订后实际执行，未提供事实时返回UNKNOWN。
- 小量R31离线反馈：`smoke-v3/loop-31/complete.json`。五轮均真实保存并执行；验证集选择初稿，heldout严格平衡正确率0.5→0.5，仍有错误。其旧样本标注来源角色不满足后续加强门，保留为开发冒烟，不并入正式统计。
- 可靠漏检反馈→修订→复检→原子晋级：`smoke/online-resource-type-cli-v2.json`。两次独立证据审查核验具体类型标识错误；API生成新检查程序后，目标由未检出变为VIOLATION，生成兼容suite并在隔离RuntimeControl中晋级。源PDF和正式答案未改。
- 冻结、解冻与后续复用：`smoke/online-two-modes-summary.json`、`online-frozen-cli.json`、`online-resumed-cli.json`。冻结时使用已晋级版本检测，解冻后可再进入评估；已正确检测的同一输入没有被强制再次修改程序。
- 真实归档PDF前端与固定版检测：`smoke/real-pdf-frozen-cli.json`。输入pdf-005b17aadceceb6a8a2b，产出123 PASS、6 UNKNOWN、2 VIOLATION对象诊断；覆盖仍部分，未把告警当人工已确认错误。
- 同一真实PDF默认自迭代路径：`smoke/real-pdf-adaptive-cli.json`。盲审核验8个局部，形成1项UNKNOWN→PASS的改进反馈；两轮候选均未改善，晋级门拒绝并保留旧版。如实保留未解决问题。

以上命令均另存同名`*-command.json`。所有模型请求共用原累计200元账本；2026-10-19本次检查保守记账33.451654元、含预留已承诺34.155488元，剩余165.844512元，6笔transport失败保留不确定预留。此为按配置费率的保守账本，不能冒充供应商实际现金扣费。

正式31—33数据另存benchmark-v1及后续有效版本；当前正补强原始局部、变异局部、引用语境与被引正文的来源角色验证。只引用规范或作品题名的候选不计正式有效样本。正式效果、模型协同修订收益和大规模扩展结论尚未完成。
