# 旧 10 规则定向回归核验（2026-10-19，T55）

本次确认了生产版本旧规则目录及执行代码，并在唯一开发仓库运行必要的离线回归。结果为 **Python 79 passed、0 failed、10 skipped；Node 12 passed、0 failed、0 skipped**。这支持所列触发场景在当前开发代码中保持行为；不等同于十规则的全量历史准确率验收，也不代表线上部署或实时外部解析服务已验收。

## 生产代码与规则范围

- 只读生产入口：`/data/apps/smart-degree-review/current`。
- 本次解析到的发布目录：`/data/apps/smart-degree-review/releases/d3b5eb5c01e49662475f31ca28dc11442df15046`。
- 开发仓库：`/data/projects/smart-degree-review-system`；Python：`/data/envs/six-rule-dev/bin/python`。
- 生产旧目录的规则 ID 为 **sjtu_rule_11、13、14、15、16、18、22、24、28、29**。名称和 ID 来自生产 `localFiveRulePaperLintService.js` 与 `sixRulePaperLintService.js` 的静态定义，而非按文件名推断。
- `localFiveRulePaperLintService.js` 虽沿用 five 命名，实际公开四条旧规则 18/22/24/28；旧 Python 脚本还含规则 6，但规则 6 不属于这十条生产目录，本次特意排除其三个专门用例。
- 生产 `getSixRules()` 中 13/14 的可用性取决于服务配置的 MinerU 凭据。本次不读取凭据或查询其值，因此只确认目录注册及条件，不声称当前线上可用开关状态。

逐字节比较生产与开发中的 `backend/pdf_rules/*.py`、`backend/scripts/five_rule_detector.py`、`backend/scripts/six_rule_detector.py`、两份旧 JS 适配器，共 **117 个文件全部相同**。这些 Python 模块及两条 CLI 未引用 `paper_compiler`。完整各文件 SHA-256 在 `/data/tmp/t55-legacy-regression-20261019/production-parity.json`。旧检测器路径的工作区 `git diff --name-only` 为空。

生产六规则版本文件记载版本 `six-rules-20261011-pure-rules`、`llm_assistance=false`；同时明确历史母本仍有误报，且此前母本扫描仅完成 12/78。本报告保留该限制，没有把局部回归解释成历史错误已修复。

## 实际执行的规则行为

表中“通过”指有具体输入及结果断言的旧检测逻辑已执行。图表版面测试使用已冻结观察或 fake HTTP 返回；这些断言覆盖规则行为，不验证云端解析当前是否会产生相同观察。

| 规则 | 旧执行代码 | 本次实际触发与对照 | 验证层级与结果 |
| --- | --- | --- | --- |
| 11 图引用目标不存在 | `pdf_rules/engine.py::detect` → `local_rules.py::detect_rules`，由 `six_rule_detector.py` 调用 | 已有图与不存在的图同时出现；正文/附录同号图隔离；显式附录限定；Unicode 分隔符；空白/不可读页返回 unsupported；fake OCR 恢复后的原页坐标 | 实际生成 PDF 后调用旧 CLI/engine，并断言 token、status、页码和非退化 bbox；通过 |
| 13 图缺少图题 | `engine.py::detect` → `caption_rules.py::detect_caption_rules` | 无题真实图、一个标题不可覆盖两个独立图、跨页题注、封面 logo 排除、原生题注补足 fake MinerU 漏检、原生图对象补检；冻结 archive figure 3/5/6 有题与删题对照、缓存题注不能替代原生字形、正文隔断 | 实际布局规则、原生 PDF 加 fake HTTP 及冻结历史观察回归；通过。实时 MinerU 未调用 |
| 14 表缺少表题 | `engine.py::detect` → `caption_rules.py::detect_caption_rules` | 无题表、表下题、跨页续表、行政表排除、原生三线表补检；Tab./Table 双语题注与正文隔断；邻表标题不能串用；删除双语题后必须报缺题 | 实际布局规则、原生 PDF 加 fake HTTP；两个历史原稿和一个冻结 V3 变异稿按 SHA-256 校验后执行；通过。实时 MinerU 未调用 |
| 15 图未被全文引用 | `engine.py::detect` → `local_rules.py::detect_rules` | 已引用/未引用图同文；图目录和自指不作为正文使用；附录同号图分属不同作用域；不可读输入不输出 clean | 实际生成 PDF 调旧 CLI/engine，断言未引用 token、页码、bbox 和 unsupported；通过 |
| 16 表未被全文引用 | 同上 | 已引用/未引用表；表目录不代替正文引用；不可读页 unsupported | 实际生成 PDF 调旧 CLI/engine并断言结果及坐标；通过 |
| 18 公式引用目标不存在 | `scripts/five_rule_detector.py::_rule_18` | 可见公式号缺失、跨行引用、单号公式、点/短横线及 Unicode dash 归一；数字列表、编号正文和非引用跨行数字不误报；异常 PDF 内容流仍输出合法 JSON | 实际 Line 输入规则及 PDF/CLI 输入输出；通过 |
| 22 文献引用目标不存在 | `five_rule_detector.py::_rules_22_24` | 正文合法 [1] 与不存在 [0]/[99]；数组下标、数据区间、坏括号排除；图目录中的真实引文仍检查；缺参考文献返回 unsupported | 实际 Line/PDF 检测；Node 上传 PDF 服务调用真实旧 Python CLI，断言第 1 页缺目标；通过 |
| 24 参考文献未被全文引用 | 同上 | 未引用条目；混合引用列表/范围；代码下标不计真实引用；模型名、百分号、斜线后的引文保留；缺文献表 unsupported | 实际 Line/PDF 检测；Node 上传 PDF 服务调用真实旧 CLI，断言第 2 页未引用条目；通过 |
| 28 目录页码与正文不一致 | `five_rule_detector.py::_rule_28` | 目录页码偏移共识中的错误页；零宽连接符、拆分视觉行、标题垂直偏移、精确标题优先、概览图中文字排除、续页目录及后记 | 实际 Line 输入及页码结果断言；通过。Node 中 28 的 unsupported 适配另外验证，未把该适配算成 PDF 端到端验收 |
| 29 附录引用目标不存在 | `six_rule_detector.py` → `engine.py` → `local_rules.py` | 现有附录 A 与缺失 Z；正文叙述“附录 A 介绍…”不是标题；“附录 C 使用说明”是真标题；不可读页 unsupported | 实际生成 PDF 调旧 CLI，断言 token、页码、bbox 和 status；通过 |

## 测试选择、数量及输出

没有重跑全部 backend Python。89 个收集到的定向 Python 用例分布如下；逐个 node ID、结果及跳过原因已保存，不以文件通过数代替断言范围。

| Python 文件 | passed | skipped | 说明 |
| --- | ---: | ---: | --- |
| `test_five_rule_detector.py` | 17 | 0 | 排除规则 6 专属测试，只选生产四本地规则相关项 |
| `test_five_rule_real_paper_regressions.py` | 9 | 0 | 从真实问题抽象出的 Line 回归；不是重新扫描完整真实论文 |
| `test_five_rule_pdf_io.py` | 3 | 0 | PDF 提取、异常流 CLI、22/24 可定位结果 |
| `test_six_rule_local.py` | 7 | 0 | 真实子进程 CLI + 生成 PDF，11/15/16/29 |
| `test_six_rule_captions.py` | 5 | 0 | 13/14 的布局、跨页、题注归属、UNKNOWN 对照 |
| `test_six_rule_cli.py` | 1 | 0 | UTF-8/字体代理字符序列化，仅 CLI 契约 |
| `test_six_rule_real_pdf.py` | 1 | 0 | 只运行本地四规则正负 PDF 用例，明确未选择 live MinerU 用例 |
| `test_six_rule_regressions.py` | 9 | 0 | 指定 OCR/行政区/原生图表/题注/Unicode 的代表性用例；HTTP 依赖均 fake |
| `test_tab_abbreviation_caption_20261014.py` | 10 | 0 | 历史表题原稿、冻结变异及局部负对照 |
| `test_caption_archive_figures_20261014.py` | 10 | 0 | archive figure 3/5/6 冻结观察及原生字形/删题对照 |
| `test_caption_native_geometry_followup.py` | 7 | 10 | 七项可执行局部对照通过；十项缺少原始 PDF 跳过 |
| 合计 | **79** | **10** | **0 failed，7.087 秒** |

Node 选取三份已有测试文件：`local-five-rule-integration.test.js` 5 项、`local-five-rule-paper-lint.test.js` 2 项、`six-rule-paper-lint.test.js` 5 项，共 **12 passed，0 failed，0 skipped，0.665 秒**。显式设置 `FIVE_RULE_TEST_PYTHON=/data/envs/six-rule-dev/bin/python`，因此真实旧 CLI 的上传 PDF 用例和总时限用例确实执行，未因缺少开关而跳过。

Node 的边界应分开理解：

- 全十条旧 ID 与新三条编译规则共同出现在目录、暂时 fallback 后目录重试：目录/路由契约验证。
- 所有 findings、bbox、双语多个 rect、unsupported→inconclusive、不完整输出拒绝、混合结果顺序和计数：结果适配验证。
- 六规则 wrapper 的超时预算及子进程退出诊断：合成子进程契约验证，不是实际 OCR 云端耗时验证。
- 仅 22/24 在本次 Node 测试中从上传 PDF buffer 进入正常服务并调用真实 Python 检测器。其余规则不能据 Node 测试声称完整上传流程已逐条端到端验收。
- 未调用运行中的生产 HTTP 页面或上传端点，未进行部署、服务重启或生产数据库写入。

全部输出另存于 `/data/tmp/t55-legacy-regression-20261019/`：

- `python-output.txt`、`python-junit.xml`、`python-results.json`：原始输出、89 个 node ID 与逐项结果。
- `node-output.txt`、`node-results.json`、`node-run.json`：Node 原始输出、12 项断言结果及命令。
- `production-parity.json`：117 个旧源码生产/开发哈希与一致性。
- `input-provenance.json`：历史夹具、现存原 PDF 预期/实际哈希、缺失原 PDF 清单。
- `tested-source-hashes.json`：执行时的测试、正常调用服务源码及 Git HEAD 指纹，避免把后续编辑视为同一次验证。
- `run_verification.py`、`no-network/sitecustomize.py`：可核对的选择及离线执行器；临时 PDF、测试缓存和子进程 spool 同样位于 `/data/tmp`。

Python 主进程及其 Python 子进程禁用出站 socket，日志中被阻断的联网尝试为 **0**；外部 API 凭据变量在本次进程环境中清除，未读取或展示凭据文件内容。Node 所选用例只使用本地检测器、fake catalog/结果或合成子进程，不执行付费解析/语义请求。

## 无法在本次验收的项

1. `caption_native_geometry_followup` 中原稿 `220-36`、`225-63`、`234-73`、`234-106`、`234-129` 的不可变源 PDF 不存在。五项原稿、四项删题变异、一项缺独立公式号的对照共 **10 skipped**；不能算通过，不能仅凭冻结文字/对象替代所需像素证据。
2. 13/14 的实时 MinerU 检出质量、外部账号可用性、当前真实网络错误和云端版面结果。本次只验证既有观察进入检测器后的行为，未发真实外部 API 请求。
3. 完整历史母本、所有 OCR/图引用/误报失败、全体学生论文准确率和召回率。既有全 backend 基线报告 `/data/tmp/shared-model-runtime-backend-suite-failures-20261019.json` 记载 145 个失败，其中 1 个当时的新框架 fixture 问题后来由主任务处理；旧基线部分为 **144 个**。本次未重跑或修复它们，也未根据局部全绿将其抹除。
4. 生产运行时服务的逐规则 HTTP 端到端验收以及真实业务数据回放。本次只读生产源码，未对运行服务发检测请求。

所执行的必要规则场景没有失败，没有观察到新框架引起的旧规则退化。这个结论限定于上述可执行输入与断言；缺失源文件、未调用的云端环节和既有历史失败均保留为未验收范围。
