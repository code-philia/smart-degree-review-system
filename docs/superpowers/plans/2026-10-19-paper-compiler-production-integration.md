# 论文编译网站接入与首次发布配置准备

日期：2026-10-19。状态：代码及离线网站回归已验证，供首次发布前审查；尚未修改正式服务、环境、权限或凭据，尚未发布。本方案沿用唯一开发目录和现有分支，保留原有十条规则、生产数据库、用户、报告、PDF 和缓存。

## 已实现的网站接口

现有规则配置页 `/rule-config` 增加自动迭代状态和冻结开关。页面显示“自动迭代：开启（默认）”或“自动迭代：冻结”，开关选中对应 `freeze=true`。读取失败时显示错误，不伪装为默认开启；保存失败时保留最后一次已确认状态。状态与切换仅向学校管理员和学院管理员开放，后端独立校验权限，学生及导师请求返回 403，匿名请求返回 401。

接口前缀为 `/api/normative/paper-lint`：

| 方法及路径 | 输入 | 输出或用途 |
| --- | --- | --- |
| `GET /control` | 无 | 实际生效的运行控制快照 |
| `PUT /control/freeze` | JSON `{"freeze": true}` 或 `false` | 持久化布尔开关并返回快照；字符串和数字均拒绝 |
| `GET /control/history` | 无 | 按时间顺序返回审计事件数组 |
| `POST /control/rollback` | JSON `{"version_id": "已晋级版本"}` | 显式回滚并返回快照 |

Node 控制调用固定为 `paper_compiler_cli.py control --action status|freeze|unfreeze|history|rollback --control-root PATH`，回滚另传 `--version ID`。请求不能指定运行目录、脚本或任意命令。尚未启用编译服务时返回 503，配置页面继续显示其余管理内容。

检测继续使用 `check --pdf ... --out ... --stdout-report`，并传入 `--online --control-root PATH --cache PATH --phase website --phase-budget 200 --budget 200`。Node 不根据冻结状态拒绝检测；Python 在线执行器负责阻止冻结后的修订和晋级，必要的语义 API 仍可使用原有同意流程与预算约束。目录首次发现仍使用 `PAPER_COMPILER_PACKAGE_ROOT/31`、`32`、`33` 下的 `manifest.json`；Node把全部已配置规则传作release inventory，用户所选仅控制报告子集。后续完整版本从同一父快照的 `active_path` 加载，保留其余规则并回归后再原子晋级。

报告保留 `paper-check/1.0` 协议。网页适配器优先使用显式 `runtime.report_version.suite_version`、其次 `pipeline_version` 作为结论版本标签，`runtime.current_snapshot` 单独表示当前全局活动状态，并在每条运行记录保存 `runtime_version`、`pipeline_version` 及含冻结状态和 generation 的 `runtime_snapshot`；混合旧规则的报告也保留该标签。缺少新元数据的历史报告显示兼容包说明，不再固定写成“首轮候选版本”。

对应代码：`backend/src/normative/paperCompilerService.js`、`reviewPilotPaperLintRoutes.js`、`reviewPilotPaperLintService.js`；前端为 `frontend/src/api/compilerControl.ts`、`src/components/paperLint/CompilerRuntimeControl.tsx` 和既有 `RuleConfigPage.tsx`。

## 正式服务账号的当前访问条件

正式服务运行账号为 `smartdegree:smartdegree`。下列结果来自该账号的只读 `os.access` 探测及 root 下的路径权限核对，没有读取配置或账本内容。

| 路径 | 当前权限及归属 | 对接影响 |
| --- | --- | --- |
| `/data/apps/smart-degree-review/config` | root 所有，0700 | 服务子进程不能穿过目录读取私有配置 |
| `config/paper-model-huawei.env`、`config/paper-model-evidence.env` | root 所有，0600 | 不能由服务子进程读取 |
| `/data/runtime/paper-compiler/budget.sqlite3` | root 所有，0600 | 不能读写现有累计账本 |
| `/data/runtime/paper-compiler` | root 所有，0755 | 不能创建 SQLite journal，也不能自行创建默认 online 目录 |
| 其下 `model-cache`、`analysis`、`public-evidence` | root 所有，0755 | 目录可读但不可写；目录可读不代表缓存文件可读 |
| `/data/runtime/paper-compiler/online` | 尚未创建 | 首次发布时需要准备可写的控制与版本目录 |
| `/data/results/paper-compiler` | root 所有，0755 | 不能在默认结果根目录下创建 website 子目录 |
| `/data/runtime/smart-degree-review`、`/data/cache/smart-degree-review` | 服务账号可读写并可进入 | 可承载独立的网站结果和缓存目录 |

systemd 当前为 `ProtectSystem=full`，不是把整个 `/data` 设为只读；此处主要阻碍是目录和文件访问权限。其 `ReadWritePaths` 已包含网站既有 runtime、临时和 cache 目录。若首次发布同时收紧挂载策略，应显式保留运行控制目录和同一账本父目录所需的写路径。

## 首次发布时的最小配置安排

以下为待审查安排，未实施。

1. 让服务账号仅能进入私有配置目录，并只读所需的模型和公开证据配置文件。可使用针对 `smartdegree` 的目录执行权限和文件只读 ACL，或 root 所有、专用组可读的等效权限。不要赋予服务写凭据的权限，也不把文件改为全局可读。
2. 继续使用且只使用 `/data/runtime/paper-compiler/budget.sqlite3`。为服务账号授予该文件读写权限及父目录创建 SQLite journal 所需的权限；SQLite 在写事务时不能仅靠数据库文件可写。保留现有余额和全部历史，不复制为新账本、不重置、不增加 200 元累计上限。
3. 预建 `/data/runtime/paper-compiler/online`，授予服务账号读写和进入权限，用于控制数据库与受控候选版本；保留研究产物和旧版本目录。初始可执行包的读取权限单独设置，生成程序不能任意改写生产仓库。
4. 在已有网站可写目录下准备独立结果和缓存，例如 `/data/runtime/smart-degree-review/paper-compiler-results` 和 `/data/cache/smart-degree-review/paper-compiler`，目录仅向运行账号开放。通过下列环境项接入。新 cache 只改变缓存位置，不改变账本。
5. 选定通过验证且兼容同一共享模型的初始包目录，确认其 `31`、`32`、`33` 子目录均可读；保留旧包和旧报告。首次启用前核验 CLI 控制命令、在线检测元数据、模型配置指纹及生成程序隔离执行均通过。

拟合入已有私有网站环境文件的项目如下。`PAPER_COMPILER_PACKAGE_ROOT` 必须由最终验证产物填入，不能把占位值用于发布；此表不包含任何密钥。

| 环境项 | 值或选择要求 |
| --- | --- |
| `PAPER_COMPILER_ENABLED` | 首次发布决定生效后设为 `1` |
| `PAPER_COMPILER_PYTHON` | `/data/envs/six-rule-dev/bin/python` |
| `PAPER_COMPILER_CONFIG` | 已核对并只读授权的私有模型配置路径 |
| `PAPER_COMPILER_PACKAGE_ROOT` | 选定的初始兼容包根目录，内含 `31`、`32`、`33` |
| `PAPER_COMPILER_CONTROL_ROOT` | `/data/runtime/paper-compiler/online` |
| `PAPER_COMPILER_CACHE_ROOT` | `/data/cache/smart-degree-review/paper-compiler` |
| `PAPER_COMPILER_RESULT_ROOT` | `/data/runtime/smart-degree-review/paper-compiler-results` |

Node 的 cache 默认仍为 `/data/runtime/paper-compiler`，与现有 CLI 一致；可通过环境改到表中专用缓存。Node 不传 `--ledger`，因此新缓存根不会建立新的费用账本。仍使用原有公开证据配置与鉴权安排，不将 key 写进版本、报告或本文件。

## 验证证据

所有网站测试均使用测试替身或隔离数据库，不调用收费模型。运行环境使用 `/data/envs/smartdegree-node-v22.23.2/bin/node`。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 新增 Node 控制、CLI 参数和版本标签测试 | 先 RED 后 GREEN；9 项 service 测试和 3 项权限路由测试通过 | `backend/tests/paper-compiler-online.test.js`、`paper-compiler-control-routes.test.js` |
| 新增前端冻结开关测试 | 先 RED 后 GREEN；6 项通过 | `frontend/tests/compiler-runtime-control.test.tsx` |
| 后端全量 Vitest | 240 通过，11 按既有条件跳过；56 文件通过、1 文件跳过 | `/data/tmp/compiler-node-complete-79ilpcro/backend.log` |
| 前端全量 Vitest | `--maxWorkers=4` 下 152 项、43 文件全部通过 | `/data/tmp/compiler-frontend-limited-h14zz_7j/frontend.log` |
| 前端 Vite 构建 | 2063 模块，5.50 秒，退出码 0；有既有大于 500 KB chunk 提示 | `/data/tmp/compiler-website-build-m3utqtzg/build.log` |
| 真实网站控制链路 | 真实会话和权限路由经 Node 调用 Python control；默认 false、冻结持久化、解冻和两条 history 事件通过；匿名 401、学生 403；模型配置不存在 | `/data/tmp/compiler-control-http-d0cd4zzt/control-http.log` |
| SQLite 控制模块 | 29 项通过；审计失败原子回滚及四进程单赢家另行实测 | `backend/tests_py/test_paper_compiler_runtime_control.py` |

后端全量命令为 `node node_modules/vitest/vitest.mjs run --config vitest.config.js --reporter=dot`。运行前把 `ARC_DB_FILE`、报告和任务目录指向 `/data/tmp` 的新目录，并对临时默认数据库调用现有 `initializeDatabase` 和 `seedDatabase`。这是既有 innovation unit 测试所需的 `student01` 外键数据；未经预置的全新空库会使该无自建 harness 的测试外键失败。生产数据库未参与测试。

旧 `local-five-rule-integration` 中仅有十条目录的过时断言已更新为旧十条加 R31—R33，原规则执行路径和定位验证保留。前端全并发运行曾出现既有内置案例页的一次等待超时；该文件独立 2 项通过，限制并发后的全量 152 项通过。其余日志中的 React `act` 警告与既有测试有关。

## TODO 对应和剩余验收

- T54：本次完成网站在线调用、报告版本元数据和原管理页控制接入；原有规则选择、异步任务、证据及 PDF 定位链路保留。Python 在线 CLI、真实任务阶段进度与最终端到端验收仍须联合核对，不能仅据网站单元测试勾选整项。
- T55：旧十条目录与网站全量回归已通过。真实预算耗尽、任务失败和证据不足的完整在线展示仍需 CLI 联合测试，尤其不能把后台任务的通用错误文案当成预算原因已经明确展示。
- T56、T57、T59、T64、T66、T70—T72：本次分别提供网站版本字段、控制入口及事务控制基础；实际自动反馈、修订、重建、跨规则回归和冻结中在途调用的验收由在线执行链路完成。
- T69：持久布尔开关、默认 false、管理员页面及 API 已实现；真实 HTTP 权限链经 Node 和 Python control 在隔离目录完成联合验收，可据此勾选本项。网站报告适配器已验证保留任务冻结状态与版本快照；在线 `check` 的真实输出与执行行为仍随 T59、T70—T72 联合验收。
- T58：尚未发布；只有首次发布标准和准备配置均确认后，才使用既有受限发布入口，并继续维持常驻服务及回滚能力。

首次发布前还需以 `smartdegree` 在服务约束内做只读配置探测、同账本事务、隔离控制目录持久化和无付费启动检查，再进行获授权的真实语义调用及端到端验证。发布不得执行演示数据重置，受保护 CSV 始终另受用户授权约束。

## 私有 OpenAlex 配置的权限补充

evidence loader 会拒绝配置文件的任何组/其他权限位。直接给 root0600 文件增加用户ACL可能令mask映射为0640，仍被拒绝。上线方案应由systemd以root读取原0600 evidence.env作为EnvironmentFile，并将OPENALEX_API_KEY仅注入受控service；或提供服务UID独享0400的凭据文件。不采用给该文件增加普通只读ACL的方案。模型配置、同一个费用账本及SQLite日志父目录的权限分别按实际loader核对。本次仅准备配置方案，未修改生产权限或凭据。

单任务默认5元/1200秒，通过同账本scope约束所有模型调用；原200元累计上限仍保留。成功在线版本携带最多32个已确认在线回归案例及哈希，下次晋级必须自动复检；正式独立测试不进入该库存。当前审阅修复与557/242项验证见 research/review-findings-20261019.md，发布仍待正式研究与用户上线要求。
