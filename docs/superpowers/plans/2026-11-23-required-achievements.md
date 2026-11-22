# Required publication and research achievement section

**Goal:** Add the school-required publication/research-achievement section to the existing core-section check and publish the requested bilingual description.

**Scope:** The user supplied the school template and explicitly authorized implementation, real-paper verification, push, and external deployment. The template lists “学术论文和科研成果目录” and “攻读学位期间发表的学术论文目录”. Keep the existing rule ID, severity, admission gate, and saved reports. This requirement applies to theses, not research articles.

**Approach:** Extend native IR rule 34, using exact normalized heading aliases with source-backed layout evidence. Reuse the current parser rather than add model calls or a second parser. Reject prose, references, contents-only entries, and page furniture as evidence. Unreadable back pages cannot prove absence. Keep the change local to this rule where possible.

**Copy:** 按国标和学校规范检查论文必备组成部分，兼容空格与拆字标题。

**English:** Check the required thesis sections against national and university standards, allowing for spaced and split-character headings.

## Tasks

- [ ] Add failing native IR/PDF tests: missing/present, school aliases, English equivalent, spaced/split headings, contents-only, prose, scanned back pages, research articles, and live IR deletion.
- [ ] Add failing catalog/translation tests for exact description and school-specific missing-section advice.
- [ ] Implement the smallest native check and copy change; update the complete synthetic fixture with the newly required section.
- [ ] Run relevant Python, backend, and frontend regressions; compare any unrelated failures with the exact base.
- [ ] Freshly parse all 100 original archived PDFs, run rule 34 only, inspect every new missing-section result against the PDF. Use separate altered copies to verify actual missing-section detection; preserve originals and stored database rows.
- [ ] Independent whole-change review; fix verified issues and rerun relevant checks.
- [ ] Commit, fast-forward main, push the verified SHA, deploy through the existing Publisher, and verify public resources, copy, service health, original reports/PDFs, and private configuration.

## Review focus

1. Contents or running-header mention must not satisfy a missing body section.
2. Alternate school headings must pass without paper IDs or page whitelists.
3. Scanned back matter must remain unconfirmed rather than become a false missing-section alarm.
4. A journal/conference paper does not inherit a university thesis requirement.
5. All existing rule outputs remain identical except this newly required part and the requested description/advice.
