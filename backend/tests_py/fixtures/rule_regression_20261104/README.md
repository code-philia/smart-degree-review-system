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

离线模式会为错别字规则使用空模型响应，只核验 Paper Model、确定性高置信错字兜底、定位、去重和 manifest 契约；模型提示词与返回过滤仍由 `test_typo_prompt_chunks.py` 的 mock 测试覆盖。`--live-llm` 用于定时/人工观察模型效果，可能受模型版本、配额和服务波动影响。
