# Production bilingual interface and reports

User authorization: implement the approved preview in real source, preserve Chinese UI and detection logic, test real reports, push main and deploy external production. Latest selection: use the campus Qwen model only for translation. No renewed permission gate is required for this authorized scope.

## Baseline and constraints

- Verified remote main, source and release: a86e1e7dfc9b86f38167741d1cf2842ce27ea11d on 2026-11-10. Branch feat/bilingual-interface-20261110 in the ONLY source directory /data/projects/smart-degree-review-system. No additional worktrees. Existing untracked .codex-release-build/ stays untouched.
- Approved English preview: /data/tmp/bilingual-site-preview-20261110/native-ui-v2, offline SHA256 e8a26187e30000a1d7b01852d2332027bbde69a1746c79b2dc075a8b4400b84c. The preview has a mock transport: never ship that transport, sample login, generated PDF, sample reports, preview tool dock or bundle-from-production build.
- Chinese DOM/styles/messages and PDF workspace geometry must retain current behavior. English uses the approved wording, Beta, Unverified, brand dot/centering, sidebar original width, 14px/600 rule names and 14px/400 descriptions, 112x36 pagination / 32px options.
- No detector, compiler, severity, summary count, rule order, document admission or original prompt changes. No raw report JSON rewrite. Never translate filenames, document titles, original evidence/quotes, source excerpts, identifiers or location/page values.
- Use current PC SSH, existing libraries, campus credentials only on server. Do not print/commit credentials. No new commercial API, OCR or mail sends. Existing model remains deepseek-chat for detection/repair; translation explicitly uses qwen (alias qwen3.8-27b per user's campus approval).
- All integration tests use isolated DB/files/cache and disabled email. Production user/report/PDF data and configuration hashes must survive release.

## Architecture / chosen approach

Use one canonical detection result and a separate presentation translation cache. Static UI and known template strings use the reviewed dictionary. Dynamic explanation/reason/suggestion text uses Qwen translation only, with explicit fidelity instructions, exact item IDs, protected quoted/source terms and numeric validation. Chinese never triggers translation. This is the user-selected continuation of the separate-translation approach, with Qwen replacing the previously proposed default model.

Reusing the original detection call to produce bilingual prose was discussed but not selected. It changes the detection output requirements and cannot localize existing reports. Re-running detection for each UI language is rejected because conclusions must be shared and switching languages must not re-run checks.

## Backend contract

Authenticated owner-only POST /api/normative/paper-lint/reports/:reportId/translations and /jobs/:jobId/translations, JSON {locale:"en"}. No arbitrary client text translation API. Server extracts allowed presentation fields from owned saved result or job progress and saved repair suggestions. Exclude source/evidence fields and machine status/IDs. Protect literal quoted text and numeric tokens in explanations during translation. Return {locale:"en",status:"ready"|"partial"|"unavailable",translations:{[originalText]:englishText},source_hash:string,model:"qwen",message?:string}. Static dictionary-complete strings can remain in collection; bounded batches and cache must avoid wasted calls.

Store derived translations separately (new cache table/file with atomic writes is acceptable); key by exact source content, target, model and prompt version. Never update existing report results. Owner-check precedes any cache read. Dedupe in-flight work and serialize/bound Qwen requests below the shared 10 RPM service limit. Bound request size, model output and timeout. Invalid/missing/extra IDs or changed protected tokens must not be cached as success. Failures preserve canonical content and support retry; do not block detection.

Model transport uses campus SJTU_API_BASE_URL and SJTU_API_KEY, with a separate translation model setting defaulting to qwen. Reuse existing Python MaasClient/BudgetLedger infrastructure or an equivalently metered existing transport without changing its detection/repair settings. No secret values in frontend or API responses.

## Frontend contract

Implement a shared locale store/provider, approved static dictionary, protected original-text boundaries and real language switch controls. The preview JSX adapter may inform the runtime but remove all preview-only absolute paths/mocks. Use normal build imports. Only English CSS overrides. Language persists through login/navigation; all native text/controls and asynchronous errors consume current locale.

Add useReportTranslations(resource: {reportId?:string,jobId?:string}, revision?:unknown) to request the backend contract only while English and resource is ready. Store returned mappings in a bounded in-memory presentation store, clear sensitive mappings on logout/user change. Same canonical report objects remain mounted, preserving findings feedback IDs, selection and PDF view state. Refresh translations when completed rule progress or repair suggestions change; coalesce requests, no polling storms. Show a compact English translation pending/failure/retry status when arbitrary dynamic text remains untranslated. Chinese remains immediately available. Export waits for required English mappings instead of silently producing a mixed-language report.

## Export contract

Reuse original report model and layout, localizing a presentation copy and system labels in all current export formats (PDF/Word/text/Markdown/image/JSON). Protect source fields structurally rather than translating every string recursively. Do not change canonical data, page locations, evidence, filenames or document title. Display and export use the same dictionary and dynamic mapping. Real PDF and Word output must be inspected, not only string-tested.

## Acceptance

- Current remote main checked before implementation and again before push; branch integration preserves upstream updates.
- Static UI Chinese baseline regressions plus English navigation/modal/status coverage, tests for language persistence and original source protection.
- Translation endpoint unauthenticated/cross-owner rejection, cache reuse, concurrent dedupe, malformed model/timeout/retry, no canonical mutation; exact Qwen model selection.
- Real isolated report + real Qwen request proves arbitrary semantic explanations translate, original JSON/hash/IDs/counts/source remain unchanged, second request uses cache. Real PDF upload and live report route exercised without production data writes.
- Browser checks of real app login/upload/history/saved/live report, rule scope, filters/dropdowns and relevant dialogs in both languages; source PDF state/feedback preserved across switches.
- Actual English PDF and DOCX export rendering/contents checked; original quoted evidence remains unchanged.
- Related checks/build and independent code review pass; any unrelated baseline failures identified precisely and recorded.
- Standard deploy status/check, backup, release, service/HTTP/assets verification, before/after production data and config hashes. No mail send claimed or attempted.
