# 2026-10-19 独立审阅与修复记录

审阅范围为 `d368deb..8b1e280`；独立审阅只读，无收费请求。未发现已证实的 Critical，发现10项 Important，均纳入本次修复并以失败复现测试验证；另有1项 Minor 暂缓。该记录不代表正式300样本、消融、479篇扫描或生产部署已完成。

| Important | 最终处理 | 验证 |
| --- | --- | --- |
| 旧程序被错误绑定到并发新版父版本 | CLI 将原快照传入 loop；loop 使用同一快照加载版本，晋级前校验版本及 generation | online_review 的并发版本测试 RED→GREEN |
| 单条选择发布不完整全局规则包 | 配置的完整 inventory 与所选报告分开；保留 active 中的其他规则，只筛选最终报告 | pipeline 完整release测试及 Node 边界测试 RED→GREEN |
| 缺少分析依赖使引用审计证据门降级 | 引用调用的双侧证据要求由运行时统一执行，独立于被检查程序是否声明分析请求 | online_loop 的 omits_analysis 测试 RED→GREEN |
| 后续旧模型副本覆盖共享模型修订 | 按单一 working_model 顺序合并候选，全部程序重绑定后再检测和保存 | online_review 的 shared_model 测试 RED→GREEN |
| 字段反向布尔或字符串绕过证据门 | 所有引用语义观察均校验明确依据和支持/冲突来源，不按布尔 False 单独决定是否检查 | program_analysis 的3种字段编码测试 RED→GREEN |
| 网站未复用已确认在线历史案例 | 成功版本携带最多32个在线回归案例及其内容哈希，后续 gate 自动加载和复检 | online_review 的 prior_verified 测试 RED→GREEN |
| 报告显示旧版本 | 显式 report_version 与 current_snapshot 分开；网页用实际报告版本标注结论 | Node report release测试 RED→GREEN |
| 前一规则占满审计名额 | 各规则轮流分配名额，并对本规则目标作稳定散列抽样 | online_review 的 across_rules 测试 RED→GREEN |
| 默认任务允许仅引规范的标签 | 原始/变异局部证据及真实编辑覆盖为builder不变量；完成快照恢复也重新验证 | benchmark_builder 新增测试 RED→GREEN，37项通过 |
| 离线失败候选不进入下一轮 | 保存失败的原始答复，优先放入修订反馈并保留已验证语义反例 | feedback_loop 的 rejected_offline 测试 RED→GREEN，14项通过 |

合并后的框架专项回归：**557 passed**，日志 `/data/results/paper-compiler/development/review-all-final-compiler.log`。Node 后端完整回归：**242 passed, 11 skipped**，使用独立临时数据库，日志 `/data/tmp/compiler-node-final-xseybsjv/vitest.log`。曾有并行测试捕获TDD中间的RED，以上最新完整结果替代这些中间态，不改写旧日志。

Ruling：所有 ReferenceUse 的在线确认均要求实际引用语境与已确认被引内容；即使某个格式检查不需要外部内容，也不因生成程序缺失依赖而降低审计门。代价是外部证据不足时少产生在线修订，保留 UNKNOWN，而不是制造可靠反馈。

Ruling：在线历史回归库存以共享兼容版本携带，限定32个已确认在线案例，执行侧私有保存，不接入正式独立测试答案，不把其他用户原文作为网页报告内容。代价是超过窗口的旧案例不提供无限期自动防退化保证；完整历史仍在原episode中。

Minor 暂缓：planner 接受字符串/字符串列表规范输入，而下游期望带 id/text 的记录列表。当前三条正式任务均使用记录列表，正常实验不受影响；后续应在任务入口统一归一化或提前拒绝，避免无效输入产生费用。

独立审阅未裁定正式标签正确率、实验改进、实时供应商费用、生产隔离/权限和国标全文逐条转录。本轮也不据专项测试宣称模型标签是人工金标准或形式化证明；正式实验与首次生产验收分别保留。
