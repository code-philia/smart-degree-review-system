# R09 / R10 / R11 规则回归资产

本目录只保存可审查的预期（manifest），不提交约 355 MB 的 PDF 归档。完整数据集由
`RULE_REGRESSION_PDF_ROOT` 指向；该目录应直接包含 manifest 中的 PDF 文件。

运行离线、确定性回归（默认，不调用模型 API）：

```sh
RULE_REGRESSION_PDF_ROOT=/path/to/extracted/cases \
PYTHONPATH=backend:backend/scripts .venv/bin/python \
backend/scripts/run_rule_regression.py
```

运行真实模型观察性回归（不建议作为合并门禁）：

```sh
RULE_REGRESSION_PDF_ROOT=/path/to/extracted/cases \
PYTHONPATH=backend:backend/scripts .venv/bin/python \
backend/scripts/run_rule_regression.py --live-llm
```

离线模式在真实 PDF 上运行 Paper Model，并使用固定响应验证规则处理和报告契约。
R11 核对保留侧证据、删除侧文本及最终差异类型和短文案。GitHub Actions 每次运行无数据依赖的规则契约测试。
PDF 资产由有权访问论文的自托管 runner 挂载，运行前按 manifest 校验 SHA-256。
在该 runner 上解包 PDF，添加 `paper-rule-fixtures` 标签，并把仓库 Actions 变量
`RULE_REGRESSION_PDF_ROOT` 指到解包目录。随后从 `main` 手动运行 Rule regressions，
即可执行九份 PDF 的离线回归。

如需单独复跑 R11，可以追加 `--case R11_v1 --case R11_v2 --case R11_v3`。
离线模式验证程序链路。`--live-llm` 用于人工或定时评估真实模型的召回与误报，受配额和服务波动影响。
