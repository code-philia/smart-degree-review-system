# 中英文标点误报最小修复与重测

目标：修复完整复核发现的417条不应报警和39条证据不足报警；保持普通中文正文及封面字段的标点检查。复用 Paper Model / Paper IR，仅本地检测，不调用 API/OCR。

选择：在检测入口补充可检查文本证据和技术表示排除，沿用现有解析、结果协议与精确字符高亮。无需重写 Paper Model，也不按论文名、审计编号或预存答案隐藏报警。

- [x] 在旧实现上复现语法、元组、扫描页文字层、模板等误报，测试先失败。
- [x] 修改 `backend/paper_compiler/local_checks.py`，保留 `completed` 协议；证据不足不报警，真实异常保留记录。
- [x] 新增 `backend/tests_py/test_fast_punctuation_scope.py`；验证普通正文、英文句点、封面字段、拆开的声明段落仍可检出。
- [x] 对固定原300个 Paper IR 变体及对应母本重测，报告真实 TP/FN/FP，不用新样本替换漏报。
- [x] 重新检查479篇归档，核对417+39条是否全部消除，剩余标点报警与逐条复核结果对应；记录状态及耗时。
- [x] 检查引用格式、核心章节完整性结果；保持历史结果不变，新结果另存。
- [x] 验证、提交开发分支；本轮先报告结果，不合入main、不更新正式部署，下一步由用户决定。

位置：仅在服务器 `/data/projects/smart-degree-review-system` 的 `czh-3rules-1025` 开发。保留全部未提交数据，不操作同学目录，不修改指定的 `30条规则_变异检测结果.csv`。

范围说明：短图表标签、结构化技术表示及扫描文字层缺少充分证据时不直接报错；这是检查范围的保守调整，不能宣称任意新PDF上绝对零误报。检测结果与误报回归结果分别报告。

验证：新旧 Python 本地规则测试，原300变体，479篇原PDF的本地解析与扫描，后端既有测试基线对照。API修复建议逻辑不变。

## 本轮验证结果

- 68项 Python 测试及19个子用例通过；完整后端 Node 测试343项通过、12项跳过、7项既有失败，修复前后失败集合一致。未修改相关旧接口。
- 原固定300个IR mutant及对应母本：三条各TP=100、FN=0、FP=0；母本IR哈希未变。此precision为受控母本实验结果，不是独立随机测试精度。
- 从479个原始PDF重新解析后执行1437次检查，均completed；失败、不适用状态为0。核心章节0篇0处；引用格式32篇279处；标点214篇1673处。
- 已知417条误报及39条证据不足报警均不再触发。所有1673处剩余标点报警与完整复核中的真实误用条目对应；原先认为真实的501条也被保守排除，不能据此宣称任意PDF上零误报或无漏报。扫描内容不做OCR，不作为缺失或标点错误证据。
- 本地解析加三条检测耗时中位数1045.3ms、P95 2813.5ms（8进程并发）；不含上传、浏览器渲染和API修复建议，不能当作网页端到端耗时。完整重测112.3秒。
- 独立只读代码复核无Critical/Important；保守整段排除和括号排除的召回代价已记录。审计脚本对原编号2630做过一次位置对应补偿，仅用于比对，不进入检测器。
- 结果：`/data/results/punctuation-fp-fix-20261025/final-verification.json`。本轮不推送main，不推送开发分支、不部署，保留测试站和正式站原版本，等待用户看结果后决定。

### 基线已有的7项失败

- FAIL  tests/local-five-rule-integration.test.js > four local rules in the existing basic-check flow > keeps all ten existing rules alongside three compiler rules without review-pilot
- FAIL  tests/paper-lint-jobs.test.js > durable MinerU paper-lint jobs > resumes a persisted running job once and keeps failure visible
- FAIL  tests/paper-lint-jobs.test.js > durable MinerU paper-lint jobs > returns 202, polls to a single saved report and hides another user job
- FAIL  tests/paper-lint-jobs.test.js > durable MinerU paper-lint jobs > runs sjtu_rule_11 in a durable background job because scanned pages can need OCR
- FAIL  tests/paper-lint-jobs.test.js > durable MinerU paper-lint jobs > runs sjtu_rule_15 in a durable background job because scanned pages can need OCR
- FAIL  tests/paper-lint-jobs.test.js > durable MinerU paper-lint jobs > runs sjtu_rule_16 in a durable background job because scanned pages can need OCR
- FAIL  tests/paper-lint-jobs.test.js > durable MinerU paper-lint jobs > runs sjtu_rule_29 in a durable background job because scanned pages can need OCR
