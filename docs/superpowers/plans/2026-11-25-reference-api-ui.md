# Reference API interface refinement

**Goal:** Reduce the clutter in the two-step introduction and API configuration, and move API configuration from preferences to a dedicated key icon in the top bar.

**Scope:** Existing React/Radix components and styles only. Keep account encryption, database verification, existing reports and account guide receipts unchanged. Preserve existing copy except the necessary bilingual correction to the moved entry point. Provide a local preview before publication.

**Design:** Use the existing toolbar icon size and spacing for KeyRound. Open one dedicated dialog with a clear title, two grouped provider cards, compact status badges, aligned fields/actions, and one shared privacy explanation. Keep interface preferences and guide replay in Settings. The guide uses Chinese as its primary typography and English as its supporting line, a quiet two-provider explanation, and clearly separated primary/skip actions. Reference guidance: Carbon form anatomy/alignment, GOV.UK details, Atlassian onboarding modal.

**Tradeoffs:** A dedicated dialog is preferred to another Settings section because the user explicitly requested a separate top-bar entry; a full page would interrupt the current report/upload workflow. Maintain both provider forms together so no configuration is hidden behind another navigation step.

- [x] Reproduce the missing separate key entry with an integration test.
- [x] Extract a dedicated ReferenceSettingsDialog and update toolbar, guide destination, focus return, close/account-change cleanup.
- [x] Reorganize provider forms and guide typography, spacing, bilingual actions; preserve save/delete behavior.
- [x] Validate candidate keys against the free authenticated OpenAlex/SerpAPI endpoints before saving. Distinguish invalid keys from temporary failures; preserve old ciphertext. Align the scoped frontend PUT timeout with the backend deadline.
- [x] Apply the user's exact rule title/description and synchronize English copy.
- [x] Run focused component/integration checks and build; check actual browser geometry, desktop/narrow and light/dark.
- [x] Prepare a local mock-only preview; do not publish this revision before the user reviews it.

Verification: frontend35/35; backend104/104; GUI8/8 configurations and extra invalid/transient-message browser checks. Live invalid keys rejected by both providers; real existing OpenAlex and SerpAPI keys accepted by the staged validator under the actual campus service identity, no saved-key/report writes or paid searches. Independent review found one request-deadline mismatch; reproduced RED, fixed with scoped12s PUT timeout and confirmed by reviewer. Full backend suite retains unrelated failures; no claim of a fully green repository.

Preview: http://127.0.0.1:5278/reports/pdf/gui-reference-audit (isolated demonstration data).

User revision 2: title the second step “规则：引用文献是否不存在” / “Rule: Nonexistent cited references”; explain purpose and two setup steps instead of the source-fallback disclosure; make both languages of Skip turn blue together; use “保存密钥” / “Save key” for both providers including replacement; remove the fallback paragraph and masked-hint wording; match the SerpAPI introduction to the OpenAlex format. Frontend35 and eight GUI combinations pass; the hover-color assertion verifies both languages in both themes. Saving still validates before writing and failed validation still preserves the previous key.

Subsequent user copy refinements: provider introduction/label/link now share one localized template (Chinese uses 密钥 throughout). The introduction explains the finite shared public search quota and optional personal quota, with sentence-level line breaks to avoid orphaned final characters. No quota amounts invented and no runtime billing/fallback changes.
