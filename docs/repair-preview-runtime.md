# Repair preview runtime

本地预览服务的完整非敏感运行配置保存在：

`/data/projects/legacy-rule-repair-suggestions/runtime/repair-preview/backend.env`

该文件集中记录：

- 3001 本地监听地址；
- 预览业务数据库、任务目录和报告目录；
- 同时用于四条规则检测和 PDF 证据提取的 PyMuPDF Python 环境；
- AI 修复建议使用的 Python 环境；
- Huawei MaaS 配置文件路径；
- 模型费用账本、响应缓存、结果目录和预算。

真实密钥不写入该环境文件，仍保存在 `config/huawei.env`。

启动预览服务时使用固定脚本，避免手工遗漏变量：

```bash
bash /data/projects/legacy-rule-repair-suggestions/repo/backend/scripts/start_repair_preview.sh
```

不要直接用裸 `node src/index.js` 启动，否则规则检测和 AI 修复建议可能退回系统 Python，导致 PyMuPDF、模型配置或费用账本不可用。
