# Numbered reference-list guidance

When a reference-related check has the unsupported reason “未可靠识别编号参考文献表”, show exactly “请按国标要求对参考文献列表进行编号，确认内容完整且可读取后重新检测。” instead of generic missing-section advice. Synchronize deterministic English. Keep detector results, stored reports, warning identity/counts, other prerequisites and API/resource-failure guidance unchanged.

1. Add failing tests for reference rules22/24/31/32/33, historical metadata variants, actual Chinese/English warning cards and exports; preserve unrelated warnings.
2. Add the narrow branch in the shared presentation helper and English copy.
3. Run related frontend/backend tests and an independent review.
4. Push main and deploy external through the existing Publisher; verify source/data integrity, public resources and actual built warning copy.
