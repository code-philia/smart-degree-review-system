# 摘要数值一致性规则：正确性与可复现性

历史参考：`04208d6`。本次不部署生产、不运行真实模型批量评测。

## 执行边界

业务阶段仍是 `structure_locator` 和 `numeric_verifier`。正常路径最多进行两次逻辑模型调用；第二阶段的检索完全在本地运行。API 429 的原有传输重试可能产生额外 HTTP 请求，逐次记录。

第一阶段输入由摘要、目录条目、真实 Section ID/层级/父子关系和完整源文本块构成。按章节轮流选择完整块，记录保留和遗漏的 block ID；过大的摘要或上下文报技术错误，不截断 JSON。Paper Model 原始快照另存。

第一阶段必须返回：

```
contributions: [{id,text}]
declarations: [{id,contribution_id,text,number,metric,unit,comparison,condition,
                dataset?,method?,baseline?}]
preconditions: [{id,passed:boolean,reason,suggestion}]
mappings: [{declaration_id,chapter_id,experiment_section_ids,
            evidence:[{source_node_id,quote,page}]}]
```

三个 condition ID 恰为 `abstract_numeric`、`contribution_mapping`、`experiment_subsection`。声明及贡献必须引用摘要原文。主要研究章节必须是实际顶级 Section，实验节点必须为其严格后代。映射依据必须在本次实际提供的章节块中存在。格式、引用关系或覆盖不合法属于技术错误；合法的 false 条件属于论文前置条件未通过。

第二阶段返回 `results:[{declaration_id,status,reason,suggestion,evidence:[{candidate_id,quote,page}]}]`。status 仅为 consistent、inconsistent、inconclusive。程序为每个声明建立结果，遗漏和重复转为无法确定；未知 ID 记校验异常；有异常不能整篇通过。已完成的有效结果保留。

证据必须属于当前声明的真实候选块，页码必须精确一致，quote 在对应页源文本中必须存在。只规范化版式空白，保留英文和数值 token 边界，防止将表格中的 `8 9` 拼为 `89`；同时防止把 `89%` 中的 `9%` 作为完整数值引用。不改变数值、标点或字母。校验失败的文字不会作为有效证据输出。正文定位使用 Paper Model provenance bbox；摘要声明在可匹配布局行时增加摘要定位。多页跨界的摘要引文定位仍有局限，不能伪造精确坐标。

## Numeric Verifier 内部检索

仅搜索已映射的全部实验子章节及其后代。不调用 LLM、Embedding、外部搜索 API。

固定权重：指标/别名 6，实验条件 5，数据集 5，基线 4，方法 3，数值相同 1，表题/表格 1。首版 Top-K=6。候选不足时扩大至实验范围内最多 2K 个排序块。增加相邻两个块及附近表题，保留方法/数据集/指标标签。未命中仍进入证据不足判断，不据此判冲突。

每个候选保留 declaration_id、candidate_id、source_node_id、section_id、page、block_type、text、context（邻近候选 ID）、retrieval_score、matched_signals、rank 和原始 provenance。诊断包括 scope、完整排序、所选/遗漏块及 fallback。

`evidence_recall_at_k` 接受人工标注的源节点集合，可评估主候选 Recall@K；上下文扩展覆盖不计入该指标。单元样例不代表真实论文的证据召回率。

## 运行目录与任务关联

优先配置 `PAPER_NUMERIC_RUNS_DIR`。未配置时使用 `PAPER_LINT_REPORTS_DIR` 同级 `numeric-runs`；再回退到 backend/data/numeric-runs。目录权限 0700，文件权限 0600。

每次运行使用独立 UUID，后台任务 ID 经 `--run-id` 传入，报告 `params.trace` 保存 task_id/run_id。无需数据库迁移。业务报告继续保存于原有 result_json，历史报告保留原结构。

目录包含：

- `running.json`：开始记录；中断且无 manifest 的运行可识别为未完成。
- 顺序编号的 Paper Model、实际上下文、阶段请求、请求参数、HTTP 尝试、原始响应、解析结果、token/耗时、检索候选、阶段输出及最终报告。
- `manifest.json`：完成状态、PDF SHA256、代码提交、实现源文件哈希、Paper Model 版本、context/retrieval/prompt/contract 版本及各文件 SHA256。

不记录请求 headers/Authorization/API key。对已加载的环境凭据值做脱敏。运行数据含论文内容，应作为用户数据保护；不要提交 Git。用户上传论文及临时解析文件不修改。

离线回放：

```sh
PYTHONPATH=backend:backend/scripts python backend/scripts/replay_numeric_run.py \
  /configured/numeric-runs/<run-id>
```

回放验证文件哈希，重新构造两阶段输入，并要求与已记录 messages 相同，然后使用记录的解析响应重新执行后处理，不联网。它验证工程可重放，不承诺同一 API 再调用获得相同输出；模型别名背后的权重可能变化。调用失败的记录保留故障细节，不能伪装为成功回放。

## 版本与后续 Skill 接口

`structure_prompt(context)` 与 `verifier_prompt(structure,candidates)` 是两个指令入口。
上下文构造、检索、强制输出校验与证据绑定各有独立版本字段。后续只需增加不可变版本清单/加载器，将两个入口的指令外置，并让 run profile 固定一对 Skill 版本及内容哈希。Skill 不能替代或绕过 Python 强制校验。

比较 verifier 时应固定结构阶段结果和候选集合；比较 locator 时固定摘要及章节上下文；比较全流程时固定 PDF/IR 和检索版本。原始 Prompt 的旧上下文缺陷必须标识，不能将修复带来的收益归因于 Skill。

## 已知限制

- Paper Model 仍依赖原生文本和启发式章节树；扫描件、错误层级会降低定位能力。
- 保留表题、原生文本及相邻行，不保证表格行列/单元格可靠重建；无法确认时应由 verifier 返回 inconclusive。
- 第一次抽取遗漏尚未被模型抽取出的声明，无法靠第二阶段覆盖检查自动发现；仍需人工标注评测抽取召回率。
- 词法候选排序尚未在真实模型/真实论文标注集上校准。Top-K 和别名需要真实 Recall@K 验证。
- 原文存在和页码正确不等于推理正确；单位换算、舍入、指标和实验条件的语义核验仍依赖模型。
- 单次 verifier 调用失败保留第一阶段与候选；无法获得该次尚未返回的逐项模型结果。
- 运行记录作为独立研究数据保留，尚未实现自动保留期限；删除业务报告不会自动删除其研究运行目录。
- 本轮无自动 Skill 学习、自动迭代或生产部署。

## 验证命令

```sh
PYTHONPATH=backend:backend/scripts python -m pytest backend/tests_py/test_numeric_consistency.py -q
cd backend && npm test -- tests/numeric-review.integration.test.js
cd frontend && npm test -- tests/numeric-review-details.test.tsx
```

测试使用人工可核验的源文本、合成 PDF 与模拟模型输出；真实 API 的抽取准确率、语义映射能力、证据召回率和端到端准确率尚需小规模人工标注验证。

本轮验证记录（2026-10-31）：

- Python：36项通过。覆盖结构/证据契约、遗漏/重复/未知声明、实际合成PDF解析、检索、异常、记录脱敏、哈希校验及离线回放。
- Node：9个相关测试文件、43项通过。涵盖新规则保存读取、任务关联、建议输入、原本地规则实际调用、注册、登录、反馈、取消及报告删除。
- 前端：4个相关测试文件、9项通过。涵盖新详情、历史列表、停止任务及建议状态隔离；生产构建通过。
- 本地规则集成测试通过 FIVE_RULE_TEST_PYTHON 指定工作区 Python。更新了此前缺少新增规则的固定目录断言。
- 没有调用真实模型 API，也没有修改正式服务或数据库。

## 继续验收：校内 API 小样本（2026-10-31）

随后使用仓库生成的两页合成论文，调用校内 `deepseek-chat` 进行小规模真实验证。没有发送真实用户论文，没有部署或修改正式服务。

预验收暴露两个问题，原始失败记录均保留：模型把 preconditions 数组改成对象并返回 null 字符串；模型把 Method implementation 错当成实验子章节。修复分别为明确的输出 JSON 模板/空字符串约定，以及实验性质的原文佐证检查和更明确的章节定位指令。严格 Schema 校验未放宽。

实验性质检查仅查看已映射的子章节标题及正文，允许非标准标题通过正文评估/验证等信息得到佐证；缺少佐证时不进入第二阶段。它是保守的必要条件检查，不保证语义分类完全正确。未覆盖的术语可能造成无法验证，后续应以人工标注样本扩展。

同时修复了英文摘要跨行定位的 token 边界，并补充相邻数字不得拼接的定位回归测试。运行清单增加 working_tree_dirty，配合实现文件 SHA256 区分未提交代码。

固定检测提交 `36f396e`（调用时 tracked tree clean）最终验证：

| 合成案例 | 结果 | LLM调用数 | 耗时 | 输入tokens | 输出tokens |
|---|---|---:|---:|---:|---:|
| 摘要与正文均92.5% | 一致 | 2 | 15.69秒 | 2889 | 645 |
| 摘要92.5%，正文89.3% | 不一致 | 2 | 18.81秒 | 2873 | 709 |
| 正文只有方法实现、没有实验子章节 | 前置条件未通过 | 1 | 12.25秒 | 1161 | 394 |

最终三个案例共5次HTTP请求、8671 tokens；三个案例的保存记录均通过无API离线回放。包括预验收和保留的失败尝试，本次真实调用共12次HTTP请求、18843 tokens，没有429重试。

记录根目录：`/data/projects/legacy-rule-repair-suggestions/runtime/numeric-live-20261031`，汇总文件为 `acceptance-summary.json`。原始输入输出只在受限运行目录保留，不提交Git。

本次 Python 回归测试扩展为42项通过。此前后端43项及前端9项兼容性测试结果保留；此次没有修改前端或普通规则。

合成样本只证明基本流程和已知失败场景的处理，不代表真实论文上的准确率或召回率，也不足以支持 Skill Refinement 效果结论。
