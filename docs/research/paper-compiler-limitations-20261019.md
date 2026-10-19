# 论文局限与研究披露（T50，study-v5证据范围）

本说明可作为论文局限段落及补充材料引用。它依据既有冻结数据审计、组成图、ff19工作量与宿主干预记录、protocol-v8及后续400元授权；本次未读取封存oracle、正式检测预测或尚未开放的heldout结果，也不报告新的检测成绩。每项事实的文件字节SHA256与JSON定位见[refs.json](/data/results/paper-compiler/framework-20261019/research-disclosures-v5/refs.json)。本交付不代替最终结果、最终生成程序lineage或TODO验收。

**实验单位与规模。** 冻结benchmark-v4共390例：R31、R32、R33各100例标注违规变体和30例实际改变的合规对照。所有案例均为合成IR编辑；real只表示被编辑的原论文/引用语境来源真实，不表示自然发生的违规。300例违规对应三项任务，不能表述成验证了300条规则；也没有30条规则规模、成本增长或无人干预扩展性的实证。组成图展示输入覆盖，不展示检测准确率。[C01；S01–S02、S07、S12–S13]

**R33语境来源与标签。** R33真实引用语境保留2例违规和7例对照；构造语境为98例违规和23例对照。独立测试的19例违规和6例对照全部为构造语境，因此该测试不能单独证明对真实原句的泛化。构造语境有真实被引文献内容支持，但仍是模型辅助构造的虚拟引用语境；不能当作独立抽样的真实论文。明示冲突可能比自然论文中的细微引用用途更容易辨别，构造及筛选会影响任务难度。[C02；S01、S12–S13]

390例均沿用oracle 2.2的模型辅助标注与分开上下文的盲复核，既有审计核对390对独立调用链。标注与复核分离、隐藏提案预期并核对原/变局部及来源精确引句，可减少显性泄漏与不可追溯标签；它们不是独立人工gold，也不是不同模型家族的独立判断。同家族生成、标注、复核和检测可能共享知识缺口、偏好和错误。引句逐字匹配及两判一致不构成语义正确性的充分保证，不能以自洽替代外部人工或异家族验证。[C03；S01–S02、S07]

**R32证据宇宙。** R32有限受控目录实验的“不存在”仅限声明完整的114作品库；它不能证明现实世界不存在同一作品。公开检索无匹配、失败或覆盖不足仍为UNKNOWN，必须与受控负例成绩分别报告。独立的开放检索便利探针为7次查询：3个已知身份产生6次“已核实存在”，另1次自造查询为UNKNOWN，0次证明不存在。这不是7篇独立作品或precision/recall评测，探针原始记录数也不等于新增HTTP次数。[C04；S01、S14、S17]

**母本隔离与相关性。** 候选库存有18组母本，最终390例实际使用17组：6组真实PDF母本及11组从头构造的IR母本，反馈/验证/测试分别使用9/4/4组。构造IR不是另外11篇真实PDF。同母本及派生变体同split，源文件hash未发现跨split冲突；这不能消除同母本内变体、共享提示和外部文献的相关性，390例不能视作390篇独立论文。最终案例实际使用16种被引作品，其中《Attention Is All You Need》在验证和测试间重叠1种；资源库存跨split重叠7种是另一口径，不能替代实际案例证据重叠数。母本隔离不等于被引作品隔离，也不证明对全新被引作品泛化。既有350/129来源/开发历史不支持“所有heldout源全项目从未曝光”的更强主张。[C05；S01、S04]

**R31覆盖与划分修订。** R31的6例正文引文格式违规全部位于反馈集；独立测试只有1例正文格式合规对照，20例测试违规均为参考文献条目。因此独立测试主要检验书目条目格式，不能单独给出正文违规召回或宣称覆盖全部国标错误类型。R31/R32违规划分为60/20/20；R33在正式预测前依据用户“约60/20/20”要求修订为60/21/19，较原整数目标验证+1、测试−1，对照均18/6/6。修订时R33有效独特违规池为101例，不移动母本、不改标签；此选择与采样干预应保留披露。[C06–C07；S01、S06]

**benchmark-v4元数据修正。** v4相对v3修正208条生成记录链接/提案定位元数据，以匹配实际选中的相同提案和对应组件；不是重新标注208例、补造模型调用或修好208个检测错误。390对独立盲判此前已匹配；案例内容、标签、来源、分组、summary及政策不变，1261个既有冻结产物重哈希未变，失败的v3审计保留。可追溯链修复与语义/检测效果应分开陈述。[C08；S03、S05]

**观察后的宿主修正与人工投入。** ff19宿主修复发生在study-v4已观察R31反馈/验证运行失败之后，既有记录声明未见heldout预测；因此整段研究不能称为完全事前注册。修复加入实质修复历史以避免相同提示/缓存空转，并允许严格限定的JSON外层封装解码；它们属于编码代理/操作员维护的通用宿主修正，不是运行时模型自行完成的规则或Paper Model改进。重启保留18份初稿文件、390例标签/分组、旧raw、失败尝试和费用；不能把重启前后差异全部归因于自动迭代。[C09；S07–S08、S15]

规范转写、target kinds、受控库、来源缓存、构造语境、候选位置、采样配额、证据门和宿主维护均有人工/编码代理准备与决策。ff19工作量审计只是限定提交范围、文本diff和证据包代理量；重叠事件包不能相加成人工次数，静态规则ID扫描未发现编号分派也不证明绝无专用实现。完整人工动作数及人工专用detector净新增行数保持null，不能写成零。共享引文身份核验和grounding服务仍由宿主提供；本交付不把“通用框架”扩张成“完全领域无关、零人工”。[C10；S08–S10]

**费用、缓存与授权时间线。** 数据冻结时的既有累计200元快照为spent 157.922960元、committed 159.553988元，保留11条uncertain；它不是当前余额。后续独立授权receipt将同一账本全局上限提高到400元，保留3976条请求记录和uncertain，不新建账本、不追溯改写启动时200元协议；receipt时的阶段上限与全局上限另列，不能混淆。此后成本应按各实际区间和授权记录报告。[C11；S03、S11]

API请求数、token、缓存命中、HTTP次数、墙钟时间、保守计费和模型能力是不同量。已有raw/事实缓存会改变实际HTTP与成本，暖缓存不能直接外推冷启动性能；合批上下文可能改变模型答复，不能声称与单条调用等价或凭机会数推导实测速率/准确率。历史失败、额外配额尾批、宿主修正和不确定预留不得因未改善分数而删除或当作退款。本说明仅进行零新增API的证据整理，不意味整个项目零付费，也不以费用或缓存数量代替准确率、收敛或泛化结果。[C11；S03、S06–S08、S11]

引用索引：[S01](/data/results/paper-compiler/framework-20261019/benchmark-coverage-report-v4.json)、[S02](/data/results/paper-compiler/framework-20261019/benchmark-v4/final-audit-v22/acceptance.json)、[S03](/data/results/paper-compiler/framework-20261019/benchmark-v4/final-audit-v22/extended-acceptance.json)、[S04](/data/results/paper-compiler/framework-20261019/benchmark-v4/final-audit-v22/actual-groups-works-and-types.json)、[S05](/data/results/paper-compiler/framework-20261019/benchmark-v4/generation-link-correction.json)、[S06](/data/results/paper-compiler/framework-20261019/study-sampling-amendment-01.json)、[S07](/data/results/paper-compiler/framework-20261019/study-protocol-v8.json)、[S08](/data/results/paper-compiler/framework-20261019/execution-interventions-stage-addendum-04.json)、[S09](/data/results/paper-compiler/framework-20261019/effort-audit-ff19/effort-audit.json)、[S10](/data/results/paper-compiler/framework-20261019/effort-audit-ff19/审计说明.md)、[S11](/data/results/paper-compiler/framework-20261019/budget-increase-400-user-authorization-20261019.json)、[S12](/data/results/paper-compiler/framework-20261019/benchmark-figures-v4-final/figure-inputs.json)、[S13](/data/results/paper-compiler/framework-20261019/benchmark-figures-v4-final/captions.md)、[S14](/data/projects/smart-degree-review-system/docs/research/open-retrieval-diagnostics-20261019.md)、[S15](/data/results/paper-compiler/framework-20261019/framework-correction-plan-04.json)、[S17](/data/results/paper-compiler/framework-20261019/study-resources-v2.json)。冻结清单[S16](/data/results/paper-compiler/framework-20261019/benchmark-v4/manifest.json)的SHA为`7d488c15701514a31a81fa26e4e8db2b86f0e165edbc738fda0555ee1b6dc243`；本交付仅对其文件字节核对hash，未解析案例或oracle路径。
