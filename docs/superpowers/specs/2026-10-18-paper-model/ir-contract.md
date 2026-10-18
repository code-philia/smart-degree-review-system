# Paper IR v0.1 数据契约

这是设计级契约，不是已经实现的 Python API。配套 JSON 是该契约的完整教学实例；JSON 结构校验、跨对象不变量和业务规则检查是三个不同层次。

## 1. 快照和模型版本

一个 `PaperBundle` 分四份逻辑数据：

| 部分 | 内容 | 是否可供规则直接读取 |
| --- | --- | --- |
| `paper.ir.json` | 文档结构、节点内容、源文档、来源定位、profile、观测覆盖 | 是 |
| `paper.analysis.json` | 派生符号表、绑定、事实、语义边、能力及分析版本 | 是，但必须匹配 IR 哈希 |
| `diagnostics.json` | 规则结果、位置、证据、运行状态 | 检测输出；不得回流成为原文真值 |
| `oracle.json` | 独立验证的生成样例预期、可计算约束、变异目标 | 否；仅评测器读取 |

生产快照必须记录 `schema_version`、`model_version`、`document_id`、`revision`、`source_artifacts`、`root_id`、`nodes`、`coverage`、`profile`。分析快照必须记录父 IR 字节 SHA256、构建器/语义服务版本和依赖版本。教学样例以 `authored_fixture` 代替声称已运行某个分析器。

`schema_version` 管表示和类型，`model_version` 管抽取与语义契约，`ruleset_version` 管规范解释，三者独立。增加非破坏字段使用兼容版本；改变字段/语义需迁移并保留原快照。

## 2. 节点通用结构

```json
{
  "id": "figure-1",
  "kind": "Figure",
  "children": ["caption-1"],
  "text": null,
  "attrs": {"label": "1", "scope_id": "body", "visual_kind": "bar_chart"},
  "provenance": [{"kind": "source", "source_id": "source-1", "char_start": 20, "char_end": 50}]
}
```

`children` 的顺序是规范化文档顺序，不一定等于 PDF 对象流顺序。`text` 为该节点自身持有的原文文本；子节点使用来源区间锚定，父子可能引用相同来源，但做全文拼接和计数时不能重复计算。根容器可无文本；caption 不能因 title 缺失而人为填入模型生成标题。

### 2.1 结构类型

| 类型 | 主要属性/子节点 | 说明 |
| --- | --- | --- |
| Paper | document metadata、children | 根节点；缺失部分仍可装载 |
| FrontMatter / Body / BackMatter | ordered children | 文档区域，不能仅凭页码猜定 |
| TitlePage / Title / PersonMention | lang、role、identity fields | 多语言题名与身份来源 |
| Abstract / Keywords | lang、abstract_kind、children | 文本与语义四要素分开 |
| Section / Heading / Paragraph / List / ListItem | level、number、text | 方法/综述等角色在分析层，不要求标题为固定词 |
| Figure / FigurePanel / Caption / VisualLabel | label、visual_kind、scope、asset、axis/legend | 图实体独立于图题；图题和图注可区分 role |
| Table / TableRow / TableCell | label、row/column index、rowspan/colspan、header role、unit | 单元格原始值、缺失类型和数值语义分别表达 |
| Equation / MathExpression / SymbolMention | label、expression tree、symbol lexeme | 数学式原文与表达式解析可共存；不确定解析显式记录 |
| TermDefinition / SymbolDefinition | lexeme、scope、definition、unit contract | 定义节点保留正文/符号表中的位置 |
| ReferenceUse / CitationGroup | selector、expected_kind、scope、use_role | 引用本身是节点；解析结果独立保存 |
| Bibliography / BibliographyEntry / ReadingList | bibliography kind、entry key、原始著录和字段 | 参考书目与被引文献分开；外部资源非其树子节点 |
| Appendix / Note / ToC / ToCEntry / Index / IndexEntry | label、scope、target selector、printed locator | 目录页码与 PDF 页索引独立 |
| Declaration / Acknowledgements / Biography | role、text、person spans | 正式稿和匿名稿的适用条件不同 |
| UnknownBlock | candidate kinds、raw content、reason | 识别失败也保留，不能静默丢弃 |

可选扩展由带命名空间的类型注册；编译器遇到不认识的扩展不能假定其满足规则。生产 typed schema 应拒绝未知核心字段及错误属性类型；允许 `extensions` 容纳有版本的扩展。

本文和示例图中的 `CitationUse` 是 `ReferenceUse(namespace=bibliography)` 的概念别名，不是第二个冲突的 JSON kind。`scope_id` 在编号声明上表示标签命名空间的作用域；公式内符号的词法作用域由表达式所在章节/定义关系另行确定，不把图表编号作用域当作数学符号作用域。

## 3. 来源、缺失和覆盖

来源是判定基础：

- `source`：可核对的原始文件范围。
- `derived`：规则化解析或模型抽取，带输入范围与 pass/model/prompt 版本。
- `fixture_asserted`：仅限明确标记的教学/测试数据；生产运行闭环不依赖人工修订或人工标签。
- `external_lookup`：外部元数据/摘要/正文，有 URL、获取时间、资源版本、响应状态和内容哈希。
- `synthetic`：教学/变异内容，有操作 ID 和祖先范围；不声称属于未修改 PDF 的实际内容。

PDF span：`source_id, page_index(0-based), printed_page_label, bbox, coordinate_system, rotation, transform_id, text_offsets`。坐标采用旋转归一化后页面左上原点、point 为单位，同时保留回原页变换；跨页或多区域使用 span 列表。示例使用真实存在的教学 `.txt` 字符区间，**没有捏造真实 PDF 坐标**。

缺失状态以 `Observation<T>` 表达：`observed(value)`、`confirmed_absent(search_scope, evidence)`、`unknown(reason)`、`not_applicable(reason)`。JSON 中属性省略或 null 不自动等于 confirmed_absent。

`coverage` 按页面、区域、能力和对象类记录 `complete/partial/failed/not_requested`、未处理范围和证据。这里 complete 表示达到版本化覆盖协议，不表示数学上证明 PDF 从未包含其他内容。页面全部处理与某类实体完整抽取是两件事。真实数据的缺失判断还需要质量门槛；教学 fixture 的覆盖按构造契约定义，不冒充真实 PDF 自动提取成绩。

## 4. 派生实体、符号和关系

### 4.1 符号表与绑定

`SymbolDeclaration = {entity_id, namespace, canonical_name, aliases, scope_id, defining_node_id, evidence_ids}`。

`Binding = {use_id, selector, candidates, target_ids, status, reason, resolution_policy, evidence_ids}`。`ReferenceUse.selector` 保存源内容，例如数字标记或著者年份；`Binding` 不能替代 selector。变异 selector 后旧 binding 必须失效。范围引用拆成原子 use，每个原子 use 可有多个歧义候选。

作用域解析优先级由 namespace/profile 定义；不得简单用“最近文本”取代作用域。例如“附录 A 的图 A.1”可从正文解析到附录作用域；“图 1”若分章编号不明则保留歧义。

### 4.2 语义实体

| 实体 | 最小语义 |
| --- | --- |
| ResearchGoal | 明确提出的目标、范围、可回答条件与来源 |
| MethodStep | 操作、输入、输出、条件、先后依赖与来源 |
| Claim / Result | subject、predicate、object/value、context、polarity、modality、evidence |
| Dataset / Experiment | 对象/总体/划分/版本/条件；区分文中声称与外部验证 |
| Quantity | lexical value、数值/区间、不确定度、量纲、单位、语义角色 |
| Symbol / Term | 名称、类型、作用域、定义位置、是否领域公知及其依据 |
| ExternalWork | 规范化元数据、资源版本/manifestation、标识符和查证状态 |
| CitationIntent | background/method/data/comparison/criticism 等用途及来源 |

语义实体不强制作为 AST 的树节点；通过来源锚定到一个或多个结构节点。同一份正文可支撑多个事实；事实冲突不能靠覆盖旧值消失。

### 4.3 类型化边

| 边 | 方向 | 条件 |
| --- | --- | --- |
| refers_to | ReferenceUse → 声明对象 | 用 Binding 表达缺失/歧义，不造空目标实体 |
| identifies | BibliographyEntry → ExternalWork | 本地著录与外部资源身份分开 |
| defines | 定义节点 → Term/Symbol | 有作用域和定义证据 |
| describes / uses | 语义或正文节点 → 对象/方法 | 记录用途和明示/描述性证据 |
| supports | 证据对象/Claim → Claim | 方向统一；条件一致，含支持范围 |
| answers | Conclusion/Claim → ResearchGoal | 回答的是哪一目标，完整还是部分 |
| derived_from | Result/Claim → 数据/前提 | 可追溯的数据来源和转换 |
| contradicts | Claim → Claim | 对称语义但只存一个规范方向；相同条件下才成立 |
| summarizes / synthesizes | 摘要/综述/结论 → 正文或被综述材料 | 不用纯文本相似度取代语义关系 |
| backref | Note/引用代理 → Note/引用代理/源文献 | 规则 27 检查这一关系的可达来源，不检查整个学术引用图的所有环 |

边有 `status=asserted/candidate/rejected`、证据和产生者。规则只使用其契约接受的状态；候选关系不能静默升级为确定关系。生产所有模型/提示词输出还应记录结果与输入哈希；示例的手工语义关系明确标为 authored。

## 5. 数学和表格的表示

表达式示意：`Eq(Symbol("a"), Divide(Symbol("k"), Symbol("n")))`。符号绑定在 `equation scope → enclosing section → document definitions → 明确导入的领域约定` 中解析。`k/n` 的无量纲比例不能误判为缺少长度或时间单位。

表格保存行列拓扑和多级 header，而不是一段 HTML/text。跨行列合并关系、列单位、表级共享单位、脚注和续表片段参与数值解释。空白、破折号、零、不适用、无法获取等由表注解释，不强制等价。

图像保留像素/矢量资产及分图结构；轴、系列、图例、单位等是有位置证据的对象。若未读取图中文字，17 应返回 UNKNOWN，不能根据 caption 缺少关键词便认定数据归属不明。

## 6. 不变量与修改界限

1. 节点 ID 全局唯一，根存在；所有结构节点可达，children 不重复，树无环，每个非根节点恰有一个父节点。
2. 来源文件存在且哈希匹配；字符范围、页索引和坐标范围合法；原文证据不与 synthetic 混淆。
3. `scope_id` 指向存在的作用域；实体与边端点存在，边类型的源/目标类型正确。
4. 有名称不意味着有目标；悬而未决的 ReferenceUse 必须合法保存。resolved binding 不得指向不存在节点。
5. 所有派生数据属于当前 IR 哈希及能力版本；否则拒绝加载为当前分析结果。
6. 未完成能力不能伪造 complete；无证据不得写 confirmed_absent。
7. Paper IR 和 analysis 中不得混入评测 oracle、mutant 目标标签或期望诊断。
8. 规则不得直接绕过 IR 重新打开 PDF 做匹配；需要新证据时请求前端 pass 并更新 IR。

变异可以故意造成**论文层面的**缺失/矛盾，但必须保持结构与来源契约合法。要测试损坏的 IR 本身，另建 `invalid-ir` 测试集，不混进论文违规评测。

## 7. v0.2 引用分析扩展

CitationStyle、BibliographyFieldObservation、IdentityResolution、EvidenceRecord、CitationIntent 和 RelevanceAssessment 的职责见 [31—33 阶段设计](phase1-citations.md)。外部证据是带来源、范围和时间的分析输入；UNKNOWN 与服务 ERROR 分开。所有新增类型由 Model Registry 版本化注册，新规则的缺失能力保留初次自动生成与测试。按 v0.4 范围，检测系统自修复和论文修复建议均延期，不由运行失败自动修改模型契约或生成修改建议。
