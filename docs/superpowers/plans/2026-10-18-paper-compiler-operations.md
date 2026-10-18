# Paper compiler development operations

Development checkout: /data/projects/smart-degree-review-system. Python: /data/envs/six-rule-dev/bin/python. Production stays disabled for these packages until the user reviews the frozen first round.

## API use and pipeline
1. PDF glyph/layout observations build source-linked Paper IR. The model selects ambiguous bibliography boundaries; no legacy detector judges the paper.
2. Original natural-language rules and verified standard clauses go to the metered Huawei model for RuleSpec. Typed Rule IR lowers deterministically to constrained Python; independent controls gate each package.
3. Shared analysis uses the API to extract quoted bibliography fields, resolve supported ambiguous identities and judge each local citation purpose against public content. Deterministic parsing, type/field checks, hashing and the generated checks do not call the model.
4. Public Crossref, DataCite, OpenAlex, Europe PMC and eligible arXiv content supply evidence. Search absence is UNKNOWN.
5. Runtime reports PASS/VIOLATION/UNKNOWN/NOT_APPLICABLE/ERROR with exact source or synthetic provenance. No repair suggestions or production self-repair.
6. The experiment harness edits IR content, keeps sealed oracles outside the child detector, rebuilds analysis and scores the exact new target. Independent oracle prompts use the same model family: correlated errors remain a limitation.

## Commands
Run from the backend directory. Use scripts/paper_compiler_cli.py (the unique filename avoids collisions with legacy scripts-path imports).
- budget --ledger /data/runtime/paper-compiler/budget.sqlite3 --budget 1000
- build --pdf INPUT.pdf --out NEW.ir.json
- compile --rule-id 31 --partitioned --out NEW_PACKAGE_DIRECTORY
- check --ir INPUT.ir.json --package PACKAGE31 --package PACKAGE32 --package PACKAGE33 --out NEW.report.json --analysis-out NEW.analysis.json
- batch --manifest FROZEN_INPUTS.json --workers 3 --package PACKAGE --out NEW_BATCH_DIRECTORY
- evaluate --manifest SEALED_CASES.json --package PACKAGE --out NEW_EVALUATION_DIRECTORY

Common options: --config PRIVATE_CONFIG --ledger SHARED_LEDGER --budget 1000 --phase NAME --phase-budget CAP --cache CACHE_ROOT --evidence-snapshot SNAPSHOT_ID.
Never print the private configuration. Ledger authorization is immutable; timeouts retain uncertain reservations. Default pilot phase is capped at CNY 5. Later authorized phases share the same cumulative CNY 1000 cap; never create another ledger to evade it.

The website adapter is disabled by default. PAPER_COMPILER_ENABLED, PAPER_COMPILER_PYTHON, PAPER_COMPILER_PACKAGE_ROOT and the private config must be supplied only after the user's release decision. No new compiler-management page is added. External processing consent applies to both individual and archive requests.

## Frozen experiment
paper_compiler.experiment.inventory hashes all PDFs, deduplicating by content. run_round freezes source hashes, package manifests, the entire ordered inventory, settings and replacement-source evidence, then evaluates in groups of up to three until each rule has 100 distinct real parents or the candidate inventory/budget is exhausted. All exclusions and unassessed parents are reported.
R31: source type-marker deletion and a preserved-marker line-break control.
R32: verified real-work identity with a wrong DOI when available, otherwise a harmless line break. These positive controls do not establish detection of fabricated references. There is no exhaustive public negative catalogue.
R33: replace one bound bibliography entry with a separately verified public work; accept the negative only after a separate prompt validates original support, incompatible replacement scope, alternatives and exact quotes. At most three candidate uses per parent; rejected candidates are preserved. Same-model validation is not a human gold standard.
Candidate limits, source coverage and the chosen replacement work limit generalization. Report both all-real-parent counts and negative-only counts; do not disguise R32's negative shortfall.
Interrupted/error parent attempts are retained without implicit retries. Start another separately versioned round for later code changes. No scores from development pilots are mixed into round-001.

## Result and source safety
Never overwrite either copy of 30条规则_变异检测结果.csv. SHA256: 946308c0c010e061fafdedbebe352c6f511f818401510941e571dd91b79ff3ad.
Save new artifacts under /data/results/paper-compiler. No source PDF edits, no production activation, no new worktree.
The old Python suite had 144 failures before this work; compare exact failed test IDs instead of claiming a clean full suite.


## 审查修复后的冻结约定
- 正式批次为每个 round 使用独立 evidence-snapshot 标识，首次获取的公开元数据、正文及失败响应原样保留；TTL 不会刷新本轮记录。另一轮需使用新标识。
- 冻结清单记录有效 endpoint、model、declared version、适配器/计费版本的指纹，不记录密钥。子进程检查指纹，模型配置变化拒绝续跑。
- 规则包所声明的能力决定执行与缓存键；生成能力也经过正常 enrich→check 路径，运行前核对代码散列。原始文献文本变更后重新建立编号和分析事实。
- available_fields 是公开元数据已证实存在的字段集合，通常不完整；集合中缺少字段不能证明原作品没有该字段。
- 报告及页面保留具体标准条款 ID 与条款摘要。正文引用的顺序编码制与著者—出版年制分别判断，物理换行不改变标点匹配。
- 有 started/result/attempt 的批任务通过持久记录恢复，不重复收费工作；仅有 started 的中断任务保留中断状态。
- 首轮结果需分别列出真实父本数、真实负例父本数、正负例结果、UNKNOWN、错误和排除。R32 的存在性正例不能被表述为不存在文献检出率。


## 公开来源配额与批次速度
不同来源可并行查询，返回记录仍按固定来源顺序排列。所有开发进程共用缓存根下的来源锁和限速状态，同一来源最多一个在途请求，每秒最多一次；arXiv 保留全局三秒间隔。HTTP 429 的 Retry-After 跨进程生效；无明确时间时指数退避。等待期不反复请求，不同查询保存 request_sent=false 的不可用记录，判定保持 UNKNOWN。
2026-10-18 的匿名 OpenAlex IP 日额度已耗尽，实际响应含剩余额度 0 与恢复等待时间。没有创建账号、购买文献服务或使用其他身份绕过限制；其余公开来源继续工作。批次报告需披露该证据覆盖缺口。
来源：[Crossref 公共接口速率及并发限制](https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/)、[Crossref 2026 请求类型细分](https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137)、[DataCite 限速](https://support.datacite.org/docs/rate-limit)、[OpenAlex 认证与额度](https://help.openalex.org/api/authentication/)。
