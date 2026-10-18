# R32 真实开放检索诊断（2026-10-19）

该诊断调用项目真实 `EvidenceGateway` 和身份匹配函数；未传入受控库，未调用 DeepSeek，未执行正式生成检测程序。它与受控库的100个违规 mutant 实验分别报告。

固定选择受控资源来源中按稳定顺序找到的 IEEE、ACM、arXiv DOI 前缀各1个真实身份；每个分别做 DOI＋题名、仅题名查询，另加1个明确标为探针的自造查询。该便利样本不是总体准确率或召回率评测；自造查询的现实世界真值未设定。

| 查询 | 查询形式 | 身份结果 | 原始记录数 | 耗时（秒） |
|---|---|---|---:|---:|
| open-1 | doi_and_title | 已核实存在 | 16 | 3.443 |
| open-2 | title_only | 已核实存在 | 13 | 1.842 |
| open-3 | doi_and_title | 已核实存在 | 16 | 3.369 |
| open-4 | title_only | 已核实存在 | 13 | 1.527 |
| open-5 | doi_and_title | 已核实存在 | 17 | 3.472 |
| open-6 | title_only | 已核实存在 | 14 | 1.538 |
| open-7 | fabricated_query_probe | UNKNOWN | 5 | 1.955 |

共7个查询：6个已核实存在、1个 UNKNOWN、0个‘已证明不存在’。总实测耗时17.191秒。开放检索未命中或不匹配不会被转换为不存在；这些数字不作为 precision／recall。

使用 Crossref、DataCite、OpenAlex、Europe PMC。原始记录含供应方 HTTP 状态、检索时间、公开 URL、响应哈希和来源组。缓存复用记录可能重复出现，因此表内记录数不等于新发 HTTP 次数；本次新发 HTTP 总次数未单独计量。

原始产物：`/data/results/paper-compiler/framework-20261019/open-retrieval-20261019/`。`inputs.json` 固定取样和输入，`open-1.json`—`open-7.json` 保存查询、证据与身份结果，`summary.json` 引用逐文件 SHA256。快照 `open-retrieval-20261019-v1` 固定本次公开响应。

边界：没有模型辅助身份裁决，也没有独立人工标签；6条正例查询来自3个已知身份，并非6篇独立论文。正式 R32 受控库闭环和最终程序的开放原论文扫描结果仍须分别完成。
