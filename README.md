# 智慧学位 AI 评阅辅助系统

面向学生、导师、学院管理员和学校管理员的本地可解释论文辅助系统。  
前端使用 React + Vite，后端使用 Express + SQLite，所有核心结果都由本地规则、公式和持久化数据生成。

## 核心特性

- 本地账号密码登录、会话恢复、退出登录
- 规范性检测：章节顺序、标点配对、重复标点、日期格式、参考文献、禁用词、长句
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
| 本地身份认证 | 四个演示账号，HttpOnly 会话，启动时幂等 seed |
| 规范性检测 | `normative-check` / `normative-reports` |
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
- `backend/src/index.js`：后端启动入口，启动时自动建表并 seed 演示账号

## 本地启动

安装依赖：

```bash
cd backend
npm install

cd ../frontend
npm install
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
- 运行时会自动创建演示账号和基础表结构
- 测试会使用隔离的 SQLite 文件
