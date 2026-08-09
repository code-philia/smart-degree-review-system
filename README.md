# 智慧学位 AI 评阅辅助系统

面向学生、导师、学院管理员和学校管理员的本地可解释论文辅助系统。  
前端使用 React + Vite，后端使用 Express + SQLite，所有核心结果都由本地规则、公式和持久化数据生成。

## 核心特性

- 本地账号密码登录、会话恢复、退出登录
- 规范性检测：review-pilot PDF 版式规则、页内高亮，以及原有纯文本规则与历史报告
- 本地文本相似度与写作风险：样本库比对、Jaccard 相似度、相似片段、风险启发式评分
- 创新性量表评估：硕士/博士五维评分、证据与改进计划、评估快照
- 规则化辅助评阅：模板选择、章节检查、参考文献检查、规范问题与客观分
- 论文润色：整篇润色、局部润色、历史记录
- 师生流转：报告提交、导师待办、批阅结果
- 质量台账与画像：记录台账、筛选统计、质量仪表盘、单学生质量画像
- 管理配置：学校/学院规则发布、本地查重样本库维护

## 角色入口

- 学生端：检测、评估、评阅、润色、报告提交、结果查看
- 导师端：待批阅队列、台账、统计、质量仪表盘
- 学院端：学院规则配置、台账、统计、质量仪表盘
- 学校端：全校规则配置、本地样本库、全校台账、质量仪表盘

## 模块清单

| 模块 | 说明 |
| --- | --- |
| 本地身份认证 | 四个演示账号，HttpOnly 会话，显式幂等 seed |
| 规范性检测 | `normative-check`（PDF 快速审查）/ `normative-reports`（原有检测历史） |
| 本地相似度检测 | `duplication-detect` / `duplication-history` / `duplication-corpus` |
| 创新性量表 | `innovation-assessment` / `innovation-scoring` / `innovation-history` |
| 规则化辅助评阅 | `ai-review` / `ai-review/history` / `ai-review/results/:reviewRunId` |
| 论文润色 | `whole-polish` / `local-polish` / `polish-history` |
| 师生流转 | `student-report-submissions` / `student-report-results` / `supervisor-review-queue` |
| 台账与统计 | `ledger-records` / `ledger-stats` / `quality-dashboard` / `student-quality-portrait` |
| 规则配置 | `rule-config` |

## 演示账号

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `student01` | `ArcDemo123!` | 学生 |
| `supervisor01` | `ArcDemo123!` | 导师 |
| `college_admin01` | `ArcDemo123!` | 学院管理员 |
| `school_admin01` | `ArcDemo123!` | 学校管理员 |

## 项目结构

- `frontend/`：React、Vite、Tailwind、前端测试
- `backend/`：Express、SQLite、Vitest、Playwright
- `backend/src/app.js`：API 与静态站点托管
- `backend/src/index.js`：后端启动入口，启动时自动初始化表结构

## 本地启动

安装依赖：

```bash
cd backend
npm install

cd ../frontend
npm install
```

首次在本地使用演示账号时，显式创建缺失的演示用户：

```bash
cd backend
npm run db:seed
```

构建前端并启动后端：

```bash
cd frontend
npm run build

cd ../backend
npm run start
```

开发模式：

```bash
cd backend
npm run dev

cd ../frontend
npm run dev
```

## review-pilot PDF 规则引擎

`/normative-check` 通过同机 Python 进程调用 review-pilot 的确定性规则和按需语义规则。部署环境需要配置：

- `REVIEW_PILOT_BACKEND_DIR`：review-pilot 仓库的 `backend` 绝对路径；
- `REVIEW_PILOT_PYTHON`：可选，已安装 review-pilot 依赖的 Python 可执行文件绝对路径；未配置时优先使用该 backend 下的 `.venv/bin/python`；
- `REVIEW_PILOT_MAX_CONCURRENT_RUNS`：可选，并发运行上限，默认 `2`。
- `REVIEW_PILOT_DEEPSEEK_API_KEY`：可选的 DeepSeek 官方 API Key；只从部署环境读取，未配置时 3 条语义规则不可选择，确定性规则不受影响。

语义规则固定使用 DeepSeek 官方 `deepseek-v4-flash` 非思考模式，不提供前端模型选择，也不在 Node 层自动重试。规则只发送其选中的摘要、论点和候选论据文本，不上传原始 PDF；模型输出必须人工复核。不要把 API Key 写入仓库、普通日志或前端代码。

上传的 PDF 只写入权限受限的系统临时目录，规则运行结束后删除；结果不写入当前 SQLite 或规范检测历史。只有用户明确勾选语义规则并确认相关文本允许外发时，后端才接受外部模型调用请求。

`/local-polish` 与 `/whole-polish` 通过 Node 后端直接调用 DeepSeek 官方 API 进行润色。部署环境需要配置：

- `DEEPSEEK_API_KEY`：可选的 DeepSeek 官方 API Key；只从部署环境读取，未配置或调用失败时自动回退到本地规则润色，不影响功能可用性。

润色固定使用 DeepSeek 官方 `deepseek-chat` 模型，按“基础/标准/增强”档位使用不同的润色提示词，超时时间 30 秒。请求失败、超时或返回内容为空时会自动回退到原有的规则化润色逻辑。不要把 API Key 写入仓库、普通日志或前端代码。

## 测试

```bash
cd frontend
npm run test
```

```bash
cd backend
npm run test
```

```bash
cd backend
npm run test:e2e
```

## 数据库

- 默认数据库文件：`backend/database.db`
- 可通过 `ARC_DB_FILE` 或 `DATABASE_FILE` 覆盖
- 运行时只自动创建基础表结构，不创建或修改演示账号
- `npm run db:seed` 仅创建缺失的演示账号，不覆盖已有账号或密码
- 测试会使用隔离的 SQLite 文件
