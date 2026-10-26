# 三条新增 PDF 规则验证（2026-26-10）

本记录补充规则 36（关键词数量）的开发验证。规则 31/34/35 的既有验证见 [three-local-rules-validation-20261025.md](../research/three-local-rules-validation-20261025.md)。

| 规则 | 单元测试 | 100 变异体测试 | 真实归档抽查 | 结论 |
| --- | --- | --- | --- | --- |
| 36 关键词数量 | `test_fast_local_checks` 28 项通过；其中规则 36 新增 8 项：3/8 个通过、2/9 个不通过、跨行关键词合并、无关键词块、正文冒号标签忽略、局部覆盖不误报 | 100/100 检出：50 个母本，50 个 `too_few_2` + 50 个 `too_many_9`；TP=100、FN=0、FP=0、Precision=1.0、Recall=1.0 | 479 篇归档中 2 篇真实违规：马欣贝 9 个、方宇航 2 个；HYUNSOO PARK、李浩宇的正文“关键词：”误标在页界保护后不再报 | 可合入 |

## 规则范围

- 仅检查中文“关键词/关键字”标签。
- 仅检查前置部分；正文、附录和模板中的“关键词：”不触发。
- 跨行续写先合并，再按 `；;，,、` 切分。
- 缺少关键词块不判违规，缺失项由规则 34 负责。
- 部分覆盖时只检查可读文本，不把无法读取当成缺失。

## 复现

单元测试：

```bash
cd backend
/data/envs/six-rule-dev/bin/python -m unittest discover -s tests_py -p test_fast_local_checks.py -v
```

100 变异体测试（`--reuse` 仅在缓存存在时使用；否则省略）：

```bash
cd /data/home/paper-rules-dev/smart-degree-review-system
/data/envs/six-rule-dev/bin/python backend/scripts/evaluate_fast_local_rules.py \
  --archive-root '/data/pdfs/archive479/新系统-归档论文' \
  --reuse /data/results/three-local-rules-20261025-v4 \
  --output <可写目录> \
  --workers 8
```

## 回归基线

- 后端 `npm run test:mvp`：39 项通过、2 项跳过。
- 后端全量测试：345 项通过、12 项跳过、6 项失败；6 项均为 `tests/paper-lint-jobs.test.js` 的既有失败。
- 前端 `npm run test:mvp`：37 项通过；`npm run build` 通过。
- Python 本地规则测试：28 项通过。
