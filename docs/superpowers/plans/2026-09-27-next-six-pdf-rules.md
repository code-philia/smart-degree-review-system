# 六条 PDF 规则检测器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 在基础规则检测中加入规则 11、13、14、15、16、29，逐处定位问题；图题和表题使用 MinerU API，结果支持现有 PDF 高亮与历史报告。

**Architecture:** Python 新包分别负责 PDF 抽取、编号索引、六条规则及 MinerU 适配；Node 把结果接入现有报告，并为耗时的 MinerU 请求保存后台任务；前端沿用规则卡和报告界面。未来本地 MinerU 只替换解析适配器。

**Tech Stack:** Python 3.12、PyMuPDF、Python 标准库 HTTP/ZIP、Node/Express/SQLite、React/TypeScript、unittest、Vitest。

**Spec:** docs/superpowers/specs/2026-09-27-next-six-pdf-rules-design.md

## Global Constraints

- 规则 6 继续暂停；规则 18、22、24、28 的检测算法和现有报告行为不变。
- 规则 13、14 在开发和上线阶段使用 MinerU 精准解析 API；选择后直接运行，无新增用户确认、弹窗或复选框。其余四条新规则不调用 MinerU。
- Token 只从 MINERU_API_TOKEN 读取；不进入仓库、前端、报告或日志。PDF 不暴露为公开 URL。
- MinerU 请求使用 model_version=vlm；单文件最多 200 页、200 MB；原上传限制仍为 50 MB。超过 MinerU 页数限制的论文先拆分，再映射回原 PDF 页码和 bbox。
- 每条规则返回所有独立发现；抽取失败或证据不足时为无法判定，不报告为通过。保持现有 DeepSeek 规则的确认流程。
- 独立测试论文不参与阈值调校。仅以获知答案的开发样本和人工核查结果调试。

## Review Focus

1. 超过 200 页的 PDF：分片仍返回原页码及正确 bbox；由任务 2 的分页测试覆盖。
2. 正文与附录复用编号：按作用域匹配，不把正文图误配附录图；由任务 1 的编号测试覆盖。
3. 图表目录与图题自引用：不让它们掩盖规则 15/16；由任务 1 的全文引用测试覆盖。
4. 扫描页、缺失版面块或 MinerU 失败：对应规则无法判定；由任务 2、3 的故障测试覆盖。
5. 服务重启和重复轮询：同一后台任务最多生成一份报告，用户不能读取他人任务；由任务 4 的持久化与鉴权测试覆盖。

---

### Task 1: 本地 PDF 索引和四条引用规则

**Files:** Create backend/pdf_rules/{__init__,model,pdf_extract,numbering,index,local_rules,engine}.py、backend/scripts/six_rule_detector.py、backend/tests_py/test_six_rule_local.py；create backend/requirements-six-rule-detector.txt。

**Interfaces:** extract_pdf(path) -> PdfDocument；build_index(document, layout_objects=None) -> DocumentIndex；detect_rules(index, selected_rule_numbers) -> dict，沿用 five_rule_detector.py 的 status/findings/location 结构。

- [ ] Step 1: 写 test_six_rule_local.py 的 test_rule11_and_29_all_missing、test_scope_and_self_reference、test_unreadable_page：断言每个缺失引用各有一个 finding 且 bbox 页码正确，正文/附录重号不误配，标题及图表目录不算有效引用，无法抽取返回 unsupported。
- [ ] Step 2: 运行 python -m unittest discover -s backend/tests_py -p test_six_rule_local.py，确认新增测试先失败。
- [ ] Step 3: 实现抽取、编号归一化、全文索引、规则 11/15/16/29 及 CLI；CLI 的 --pdf 与重复 --rule 返回 JSON，不改变旧脚本。
- [ ] Step 4: 重跑上述测试和既有 backend/tests_py/test_five_rule_detector.py，确认通过；仅提交任务 1 文件。

### Task 2: MinerU API 客户端、版面归一化与规则 13/14

**Files:** Create backend/pdf_rules/{mineru_api,mineru_layout,caption_rules}.py、backend/tests_py/{test_mineru_api,test_six_rule_captions}.py；modify backend/pdf_rules/engine.py。

**Interfaces:** parse_layout(pdf_path, token, http_client, page_limit=180) -> list[LayoutObject]；LayoutObject 含原 PDF 的 page_number、bbox、kind；detect_rules 接受该对象列表。

- [ ] Step 1: 写 test_mineru_api.py 的 test_upload_poll_and_zip、test_chunk_page_mapping、test_api_failure：断言请求 model_version=vlm，221 页拆成两片，第 221 页回映到原页码及 PDF 点坐标；Token 和签名 URL 不出现在异常；网络/模型/页码异常返回 unsupported。
- [ ] Step 2: 写 test_six_rule_captions.py 的 test_missing_captions、test_cross_page_and_continued_table：断言真实图/表缺题分别产生规则 13/14 的 findings；跨页图题、续表及装饰图无 findings；同页多处缺题返回不同 bbox。
- [ ] Step 3: 运行 python -m unittest discover -s backend/tests_py -p test_mineru_api.py 及 test_six_rule_captions.py，确认先失败。
- [ ] Step 4: 实现 API 适配、分页、ZIP schema 校验、图表对象和题的空间关联；仅在选中 13/14 时调用 API。重跑新增 Python 测试，确认通过并提交任务 2 文件。

### Task 3: 六规则接入现有后端报告

**Files:** Create backend/src/normative/sixRulePaperLintService.js、backend/tests/six-rule-paper-lint.test.js；modify backend/src/normative/reviewPilotPaperLintService.js。

**Interfaces:** runSixRules(pdfPath, ruleIds, {signal}) -> PaperLintResult；新增目录 ID 为 sjtu_rule_11、13、14、15、16、29；13/14 在缺少 MINERU_API_TOKEN 时 available=false。

- [ ] Step 1: 写 Vitest：目录有六条且原四条仍在；新规则 findings 的页码/bbox 全量保留；unsupported 映射 inconclusive；仅选新本地规则不需 Token；MinerU 规则不要求用户额外确认；旧 DeepSeek 确认仍有效。
- [ ] Step 2: 运行 cd backend 后 npm test -- tests/six-rule-paper-lint.test.js，确认先失败。
- [ ] Step 3: 增加 Python 子进程适配、目录和结果合并，保持现有 /run 同步路径对非 MinerU 规则兼容；重跑任务 3 与 local-five-rule-paper-lint.test.js，确认通过并提交。

### Task 4: MinerU 后台任务与前端轮询

**Files:** Create backend/src/normative/{paperLintJobRepository,paperLintJobService}.js、backend/tests/paper-lint-jobs.test.js；modify backend/src/database/init_db.js、backend/src/normative/reviewPilotPaperLintRoutes.js、backend/src/index.js、frontend/src/api/paperLint.ts、frontend/src/pages/NormativeCheckPage.tsx；create frontend/src/pages/NormativeCheckPage.jobs.test.tsx。

**Interfaces:** POST /normative/paper-lint/run 对含 13/14 的选择返回 202 {job_id,status}；GET /normative/paper-lint/jobs/:id 返回所属用户的状态、错误或已保存报告 ID；其余规则继续返回 201 报告。

- [ ] Step 1: 写后端测试：提交后可轮询、重启后续跑、失败保留、重复执行不重复建报告、任务 PDF 权限受限并在成功后清理、跨用户读取返回 404。
- [ ] Step 2: 写前端测试：202 时显示进度并轮询至报告；201 时原流程不变；MinerU 规则不显示新增确认；DeepSeek 原确认仍显示。
- [ ] Step 3: 运行对应 Vitest 文件确认先失败；实现任务表、后台调度、上限 1 的 MinerU 并发、独立超时和前端轮询。重跑新增测试，确认通过并提交。

### Task 5: 真机联调、回归与部署文档

**Files:** Modify README.md；create backend/tests_py/test_six_rule_real_pdf.py；按需修复前四项涉及的文件。

**Interfaces:** 只从进程环境读取测试 Token；本机可用 C:\Users\Adminitrator\Desktop\SJTU_Project\.secrets\mineru-token.txt 装入环境，测试输出只显示状态与发现，不显示密钥。

- [ ] Step 1: 用小型公开或开发测试 PDF 完成一次真实 API 上传、轮询、解析和报告高亮；核对 MinerU 实际 JSON schema，记录耗时与页码；失败先修适配器。
- [ ] Step 2: 人工核对六规则各至少一例阳性与阴性，记录误报、漏报及无法判定；独立测试论文保持封存，不用检测结果选样或调阈值。
- [ ] Step 3: 运行新增 Python 测试、后端相关 Vitest、前端 Vitest、类型检查和构建；确认原四规则回归通过。
- [ ] Step 4: README 写清服务器 MINERU_API_TOKEN、systemd EnvironmentFile、API 可用性和未来本地适配位置；提交并推送 pdf-next-six-rules，不合并 main 或部署线上。
