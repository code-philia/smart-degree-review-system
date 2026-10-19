# 正式实验重启前的通用框架修正

2026-10-19。study-v4 已保留，不与重启成绩混合。R31 反馈和验证执行结果已被观察，独立测试尚未执行；本次修正属于观察执行问题后的协议修订，不能称为完全事前注册。

第一次修订 API 原样返回旧源代码，第二次请求因输入相同命中该答复缓存。通用编译循环现传入有实际内容的修订历史：候选、程序与模型版本、反馈集错误与结果，以及是否改变。无效候选也进入历史，但不替代有效版本。初稿输入保持原样；同轮恢复保持相同上下文，下一真实尝试才增加历史。历史不含验证或独立测试成绩，也不用随机值绕过缓存。未解决错误时的未改候选仍计入最多五轮，不能视为收敛。

另外18个ERROR追溯到19份finish=stop的文献抽取响应，均为单层json围栏内的合法对象。新解码只识别这一完整外壳；自由说明、多个对象、损坏JSON、非对象与非stop仍拒绝，原字段、类型、引句与来源验证继续执行。成功API响应缓存不变，派生事实缓存绑定新解码策略。旧失败原文、ERROR和费用不改，不做隐式重试或退款。

两项修复适用于所有规则；没有手写R31—R33的检查代码。它们是人工通用框架修复，必须与后续API自动修订带来的效果分开报告。study-v5使用同一390例与18份原始初稿，基线和两种条件统一使用修正后的宿主框架。数据标签、划分、最多五轮、验证选择准则与累计200元账本不变，全部六个选择终态冻结后才评测独立测试。

验收：compiler 802 passed/2170 deselected，83个源码/测试文件前后哈希一致；39个解码专项、51个循环相关测试通过。原始18文件及31/32版本不变，33保留原编译失败。数据来源、同系列模型辅助标签、受控库和构造语境的局限仍需在最终结果报告中披露。

证据根目录：/data/results/paper-compiler/framework-20261019。修正计划framework-correction-plan-04.json；诊断diagnostics/study-v4-r31-round000-modelerror-readonly.json；根核验diagnostics/decoder-historical-envelope-root-acceptance-04.json、diagnostics/actual-initial-compatibility-root-acceptance-05.json；完整回归/data/results/paper-compiler/development/compiler-all-repair-history-json-1792377119.json。
