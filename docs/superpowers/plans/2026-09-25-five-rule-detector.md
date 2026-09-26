# 五条 PDF 规则检测器实施计划

**目标：**在本仓库实现单篇 PDF 检测，并准备好对本地 500 份 mutant 开始批量评测。

**技术路线：**PyMuPDF 只提取文字和坐标；共用版面解析；规则 6、18、22、24、28 各自判断。检测器只接收待测 PDF。评测程序才读取母本、mutant 和变异计划。

## 任务

- [x] 先写五条规则的行为测试，确认未实现时失败。
- [x] 实现 backend/scripts/five_rule_detector.py：单篇 PDF、规则选择、证据页码和位置、无法确定状态。
- [x] 实现 backend/scripts/evaluate_five_rules.py：读取最终 manifest，独立检测母本和 mutant，输出逐项结果和汇总；支持 --limit 预试跑。
- [x] 用五条真实样本和回归测试验证，再核对 500 项清单及运行命令。

**边界：**这一阶段完全本地运行，不接 DeepSeek、MinerU 或线上服务；不修改 PDF、不上线。
