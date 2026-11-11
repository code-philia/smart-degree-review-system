# 后端反馈与全用户报告导出

这些工具只供有服务器登录权限的维护人员使用，不新增网页或 HTTP 下载接口，也不放宽现有用户的报告权限。

## 固定目录

所有路径相对后端实际数据库所在目录，避免发布新版本时丢失文件：

- feedback/feedback.csv：所有当前有效反馈，可用 Excel 筛选。
- feedback/feedback.json：同一类数据的结构化副本，原始输入不改写。
- admin-export/latest.json：最近一次完整成功导出的目录和数量。
- admin-export/snapshot-*/index.csv、index.json：所有用户的报告索引。
- snapshot-*/000001/report.json：数据库保存的完整报告数据。
- snapshot-*/000001/report.md：供维护人员直接阅读的文字副本。
- snapshot-*/000001/source.pdf：对应的原始上传 PDF。

反馈包括使用反馈、检测结果评价、修复建议评价，以及对应用户、文件、规则、原因、创建和更新时间。CSV 时间统一为北京时间，JSON 同时保留原始时间字段。为防止 Excel 把用户文字当公式执行，CSV 的危险开头会加单引号；JSON 保留原值。

反馈在服务启动、成功提交、修改及撤回后更新。数据库仍是唯一真实来源。导出写盘失败不会丢弃已保存反馈；修复磁盘或权限后可手动重建。手工删除报告、用户或直接改数据库后，也应重建当前反馈快照。文件按当前有效数据汇总，不是永久事件审计日志。

## 命令

在 backend 目录中，以服务账号或获授权维护账号执行，并使用与服务一致的数据库和论文目录配置：

    ARC_DB_FILE=/absolute/path/database.db node src/adminExport.js feedback

    ARC_DB_FILE=/absolute/path/database.db \
    PAPER_LINT_REPORTS_DIR=/absolute/path/paper-lint-reports \
    node src/adminExport.js reports

只生成报告 JSON、文字副本和索引，不复制 PDF：

    ARC_DB_FILE=/absolute/path/database.db \
    PAPER_LINT_REPORTS_DIR=/absolute/path/paper-lint-reports \
    node src/adminExport.js reports --index-only

命令以 SQLite 只读方式打开现有数据库，不启动网站、检测任务或邮件程序。每次报告导出使用独立目录，成功后才更新 latest.json，旧导出不会覆盖。

## 交接到内网

1. 部署本版本代码，沿用内网自己的数据库及 PAPER_LINT_REPORTS_DIR；不要复制外网开发数据库覆盖内网数据。
2. 由维护人员执行上述命令。feedback/ 和 admin-export/ 自动创建在内网数据库旁，不需要修改前端。
3. 用 SCP/SFTP 取得 CSV 或整个 snapshot 目录。目录权限 0700、数据文件 0600；如需其他维护账号访问，由服务器管理员授权。
4. 保持目录在私有数据区，不得挂到 nginx、frontend/dist、公共静态资源或公开下载目录。
5. 报告导出可能较大，先确认空间。根据索引的 pdf_status 判断 PDF 是否复制成功；missing 表示原文件已缺失，outside_upload_root 表示路径不在配置的论文目录内，不能宣称取得了这些 PDF。

本工具提供维护用报告数据、文字副本和原始论文 PDF；学生端既有 LaTeX PDF/Word 等导出样式不变。快照与正在发生的删除可能存在时间差，需要当前状态时重新执行。旧快照由维护人员按学校保留策略清理。

已有历史论文目录不在当前配置目录中时，可由维护人员显式设置 ADMIN_EXPORT_PDF_ROOTS 为额外允许的目录列表（Linux 使用冒号分隔）。工具按真实路径验证，不复制目录范围外的文件。请只填写实际论文目录，不要填写系统根目录。
