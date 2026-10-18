# 人工投入、扩展性与标签局限阶段审计

本文件记录 T49/T50 的阶段证据，不是正式实验验收。审计不运行生成、检测、标签或付费 API，不修改 core、benchmark、任务输入、论文、受保护 CSV 或 TODO。最终候选与正式 study 仍需后续验收。

机器审计：`/data/results/paper-compiler/framework-20261019/human-effort-audit.json`。逐文件路径、SHA256、diff、初稿比较和覆盖记录：同目录 `human-effort-audit-detail-20261019.json`。初次审计原始记录另存 `human-effort-audit-detail-20261019.raw.json`；最终 detail 注明 advertised/host registry 的识别修正及新增 purpose 协议校正。证据以 hash 限定快照，持续更新的同名文件不自动视为同一版本。

## 初稿来源与正式基线资格

对象仅为 `study-v2/initial/task-*/synthesis-response.json` 和同目录 package，未将旧 `rules-reviewed-v17`、旧 DSL 或 first-round 手写包列为新生成结果。比较直接核对 `raw.code.encode('utf-8')` 与 `checks.py` 字节、program-spec 全部对应字段及 manifest code hash，没有执行程序。

| 规则 | raw 物理行／非空行 | code/spec 对应 | 阶段性质 |
|---|---:|---|---|
| 31 | 124／112 | 字节及全部对应字段相同 | 已保存初稿，未宣称行为验收通过 |
| 32 | 30／30 | 字节及全部对应字段相同 | 历史初稿；basis 含构造 policy，排除正式基线 |
| 33 | 47／47 | 未生成 package，无法比较 | raw 保留，失败不重抽，不手补代码 |

31 code SHA256：`669e1409041b5f7e94acee4c519625ed5871218216702dd0a0ed0c1557721744`；32：`7d639e83a64ef71812eba387a8d4ddaca835b1e1035dc10fd525c41f62058d0a`。相等证明所存包未相对所存 raw code 改写，不单独证明模型权重、完整调用来源或程序正确。syntax-pass 不能改称行为验收或上线资格。

33 raw 声明 `citation_relevance` 生成 request；宿主 registry 已保留该名，但当次 advertised input registry 未列出它。与宿主 existing-name 拒绝策略的冲突仅作静态记录；审计不重试、不改 raw，也不将未生成包记为成功。

三份保存输入的 generation_guidance 都为空，但这不证明 prompt 全部隔离：32 的 basis 中有 `controlled-identity-admissibility`，包含变异构造有效性、负例生成、valid=false/UNKNOWN 和对照约束。该污染必须披露，旧32答复只能留作历史，不能继续作为正式首稿基线。已记录的协议校正将该条标为 `purpose=mutation_admission`，通过通用 purpose 投影从检测规范输入中剔除；框架同步整合仍按独立任务验收。31/33须核对 clean 输入相等后保留原答复，33失败不重抽；仅32从 clean 规范第一次生成，不多抽择优。此“待clean”状态已由下述study-v3准备事件更新；原始污染32记录和此前待办快照保留。正式行为评测仍待完成。

## 新 core 分支、旧兼容路径和共享领域代码

限定范围为 commit `2718261`→`0fdedf6e8e19edf1e7bcf74475fea732b04bb4c7` 新增的13个 paper_compiler Python模块，并单列后续通用 `task_inputs.py`。对 AST 中字符串 `31/32/33` 和 If/IfExp 条件扫描，13个模块中此类字符串及编号分支均为0；新 purpose helper 也无此类字面量。seed=31、32字节／MB上限、hash窗口等整数命中单列，不当作编号分派。范围和每个文件hash均在detail中保存。

这是限定语法审计，不证明不存在通过别名、动态构造或其它路径表达的专门逻辑，更不能推出人工专用代码总量为零。`program_analysis.py`、`identity.py`、`evidence.py` 有人工维护的引文领域服务：联合身份核验、有限目录、ReferenceUse双向grounding、明确冲突接受政策及检索缓存。这些是共享领域代码，不能全称为领域无关设施或本次自动生成的detector。

旧路径单列、未由本审计修改：`experiment.py` 的31/32/33手写recipe，`standards.py` 的按编号规范转写，`validation.py` 的固定编号控制，以及 CLI 的旧31 partitioned编译兼容条件。前三文件在上述base→HEAD范围未变化；CLI有通用改动，不把整个CLI diff归为某条新规则的专用代码。这些路径的产物不混入新study生成来源。

## 可核验代码范围与不能核验的完整人工次数

文本物理行／非空行不等于逻辑SLOC、工时、逐字作者归属或完整会话投入。base→HEAD的 paper_compiler/scripts diff为增加4389、删除71；快照时未提交工作区另有增加333、删除93。逐文件分为共享框架、共享引文领域服务及兼容适配器；这些不是某条规则的人工detector行数。新purpose helper属于后续未提交校正，另存hash和范围，不回填到旧提交计数。编码代理协助实现的框架代码与运行时模型生成rule code分列。

| 保留的任务准备脚本 | 文件范围 | 物理行／非空行 | 性质 |
|---|---|---:|---|
| prepare-resources.py | 1–96 | 96／94 | 任务、规范、有限库、缓存及seed组织 |
| generate-contexts-v2.py | 1–60 | 60／60 | 构造语境请求、精确quote-ID校验与来源记录 |
| select-candidate-targets.py | 1–41 | 41／41 | 待独立核验的候选源位置选择 |
| 所选范围合计 | — | 197／195 | 任务导向实验准备，不是生成detector |

这些results目录脚本没有版本化创建基线，净新增人工专用LOC保持null；197不冒充git净新增或纯逻辑代码。旧generate-contexts.py不重复计入合计；两份存档文本直接diff为19增、9删。prepare-resources保留较早步骤，后续JSON另有修改，不声称重跑旧脚本即可重建当前输入。其它runner／诊断／合并脚本另存清单，不将保留的多版本全文累加成某条规则的新增量。

有10个证据包：规范转写；任务scope/guidance；有限库与公共资源；构造语境quote政策；31候选位置；32身份／前缀约束；33真实anchors/body；证据角色与历史重验；component／采样偏好；此次32 purpose隔离校正。证据包可能包含多次操作，多个修改也可能同属一次动作。完整会话人工动作总数和可靠动作下界均为null，不能刊为“零人工”或“恰好十次”；也无法据git author拆分人类与编码代理实际投入。

现有 `--interventions` 只计events，不能表达完整性；其 interventions=10仅为已记录证据包，不能脱离本说明当完整人工次数。三项task_specific_code事件故意不填lines_added，使净新增总量为null；文件范围计数留detail。未改工具或为字段伪造数字。

## 人工任务数据和实验驱动修正

当前v2准备输入并非只有一句自然语言：31明确四种target kinds，32选BibliographyEntry及controlled_catalog，33选ReferenceUse且允许real/constructed。v2共19项basis（31为15、32为3、33为1），包括项目解释和上述待投影的构造条款，不能一概称为国标原文。规范转写、可选／有则必备、电子媒介例外、OL OCR修正和换行解释有操作员／编码代理审阅。

tasks-pre-roles、tasks-v2-pre-source-anchors和tasks-v2的存档证实局部原／变证据、身份准入、整身份替换、编号前缀、真实anchors及正文范围调整。资源、候选母本、缓存和seed也由人为配置组织；候选不是gold，但仍影响可生成性与选择偏差。

通用框架的人工修正包括changed-span/evidence-role、盲标签契约、valid不等于违规、历史checkpoint重验、source-group split、共享首稿和program_only/joint公平比较、延后test、runtime冻结和预算限制。保存包与raw一致不能推出整条流程零干预。新task planner尚未重新规划这批已准备任务，其能力入口不能抵消本实验真实的手工配置。

## 标签、受控宇宙与真实／构造语境

31/32已存protocol-2.1配置申明相同deepseek-v4.1-flash／20260910；路径和hash在detail，未读取私有key。分离generator、labeler、blind-review请求及隐藏proposal claim能减少显性泄漏，但不构成独立人类gold或不同模型家族；同模型知识与错误可能相关。现存label_provenance亦标model_assisted／same_model_family_correlated_errors，不能把自洽当独立正确性。

32当前资源的114条catalog只对声明完整的有限宇宙有效。open检索未命中／失败／覆盖不足仍为UNKNOWN；受控排除与开放世界身份核验须分列，有限库成绩不能扩张成真实世界不存在性的准确率。

33当前有12份constructed父本，须与真实原句分层。模型辅助构造语境可能更明确且贴近所给来源，不能替代自然语境验证。方法、背景、定义、比较、批评、反驳及跨学科借鉴可能合规；题名／主题差异、摘要缺细节或全文不可达都不足以证明不相关。

源论文group disjoint不等于外部被引作品disjoint。历史smoke-v4相关性审计记录6个cached_source_content单元跨split复用；不是最终protocol-2.1的新计数，最终overlap目前null，冻结后须重算。不能据此宣称对全新被引作品泛化，或把同源多个mutant当独立论文样本计算置信区间。

当前33资源47条source中40为cached_body_before_references、6为truncated_cached_body，另1为规范／未标覆盖；39条citation seed是位置而非独立全文作品数。source-body inventory另列8条缺少摘要头的记录。片段／截断／缓存正文不代表整个作品、全部对象或开放文献覆盖；全文、摘要、截断和不可核验须分别报告。

## 阶段状态和规模结论

detail捕获时合并benchmark为incomplete、17条记录（31为10、32为7、33为0，controls未满足）。这是动态准备快照，不是最终样本量或性能。仅三个任务有保存初稿raw，33无package且旧32因输入policy污染排除正式基线；没有正式study最终胜率、收敛或泛化结论。

30／300任务的规模、成功率、成本或人工增长规律尚未验证。未来需要新任务的前瞻性自然语言输入、planner实际使用、资源与人工调整审计、独立评测和失败记录。本阶段审计不表示T49实验完成；后续必须补clean正式首稿／最终候选raw对比、正式分层与overlap、完整干预记录及独立标签核验。


## 更新：clean 初稿已准备，正式评测未运行

`study-v3/initial-preparation.json` 记录了这次实际准备，canonical `tasks-v3.json` SHA256为 `284bd6318d71cb313b138474617225605f7f027ab37db365df820eca51b9881a`。本次只新增一次32的clean规范生成，未读取benchmark样例、未择优重抽。31和33的initial目录已按相对文件清单逐字比较，全部文件与study-v2一致；33仍是保留raw的ProgramError，未重抽或补写。

新32的raw code为27物理行／27非空行，与新package/checks.py字节完全相同；program-spec全部对应字段相同，manifest code hash一致。program version为 `2f2bdd4dc525b79918806299052a35ebfa6db0b4ee60a011969a73acdad82eca`，code SHA256为 `143e3a8c265d17c0f7f5e76f1f4fd056dcc18c0e661d474bcefd891e21639a40`。其保存input.basis仅有phase1-existence和controlled-environment-v2，不含controlled-identity-admissibility，也没有purpose=mutation_admission条目。旧污染32的raw/code相等记录保持历史性质，不覆盖为这份新初稿。

准备记录的同账本差额为1次API、0.013494 CNY（prompt 4079 tokens、completion 667 tokens），既有不确定预留数保持8；这里只归属该次initial-preparation区间，不记为正式study费用或性能。原始准备记录、input/raw/code/manifest的路径及hash均追加到detail的clean_initial_preparations。原来的10个证据包和完整会话动作数null保持不变，执行事件另列，不把API次数转换成人工干预次数。

这次状态是“clean初稿已准备、formal evaluation pending”；未跑heldout，不记录性能或宣称T49完成。最终候选、正式分层/overlap和实验结论仍待后续补充。旧审计raw快照未改动。
