# R09 / R10 规则回归资产

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

离线模式不会调用模型，而是按 manifest 提供符合当前 JSON 协议的模拟“发现候选”和“候选复核”响应；它核验 Paper Model、文本定位、单字归一化、二次复核接入、去重和 manifest 契约。它不证明模型本身的召回率。`--live-llm` 用于定时或人工观察真实模型效果，可能受模型版本、配额和服务波动影响。
