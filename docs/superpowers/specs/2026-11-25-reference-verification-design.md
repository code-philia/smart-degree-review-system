# Reference verification and account API settings

## Confirmed scope

Reintroduce reference verification using a new `reference_verification_check` rule. Keep retired `sjtu_rule_32` code and archived data untouched and hidden. Follow RefChecker's identifier-first, multi-source metadata comparison approach and RefCheck's compact issue categories. This release does not perform model-powered web searches.

OpenAlex keys are optional and encrypted per account on the server, replaceable and deletable. Fallback order is personal OpenAlex key, configured platform OpenAlex key, then Crossref; arXiv identifiers additionally use arXiv metadata. Never publish or log secrets. All users see a versioned two-step feedback/API onboarding once; Settings can replay it without changing receipts. Chinese and English, light and dark are required. Existing unrelated copy and checks stay unchanged.

## Approach

Integrate a bounded native-PDF reference adapter and independent database-verification service into existing durable jobs, PDF locations, reports and exports. Use the upstream projects as technical/UI references, with explicit provenance. Replacing the whole application or invoking model deep search would add unapproved account and billing behavior. New database-only requests do not consume model credit. Indexed identifiers, exact title/author/year support and source URLs substantiate matches. Never infer nonexistence from provider errors or incomplete extraction.

## Results

Each entry has one category: verified, suspected, mismatch, upgrade, incomplete, unverified. Missing coverage (including Chinese, theses, books and webpages without authoritative identifier matches) stays unverified. A suspected result requires successful relevant searches and an explicit advisory; identifier conflicts are explained rather than proving nonexistence. Fields and provider availability remain visible alongside source references. All report links use allowlisted HTTP(S) source URLs and source text is escaped.

## Security and operations

AES-256-GCM with a private deployment key, user ID as authenticated data. Authenticated same-origin settings endpoints enforce account preconditions, return only configured status and masked suffix. No secrets in stored job progress, exports, errors, caches or URLs exposed to clients. Fixed provider destinations, bounded requests, cancellation, Retry-After pacing, retries and cache policy. Deployment backs up databases/config, preserves original rows and existing login variant, and verifies health/assets. Real-paper tests create no replacements for existing reports.

## Validation

## Confirmed additions during implementation

Users can additionally register and store their own optional SerpAPI key. Its Google Scholar API supplements unresolved database checks, using only that user's provider quota, with no model calls and no platform SerpAPI fallback. The same encrypted account storage and independent replacement/deletion apply. Supplementary misses remain unverified. The user explicitly confirmed that the external HTTP site is a development environment and must also allow key entry. A private `REFERENCE_SETTINGS_ALLOW_INSECURE_DEVELOPMENT=1` exception applies only there, for the exact configured origin; the campus site retains HTTPS and the default save policy requires HTTPS.

Exercise positive matches, metadata and identifier conflicts, preprint/publication equivalence, unavailable sources, key exhaustion/fallback, empty and multilingual extraction, cross-page and multi-column bibliography, private-account isolation, key replacement/deletion, both locales/themes and onboarding replay/once-per-account. Native PDF extraction only; no OCR. Use real Chinese and English archived PDFs plus deterministic provider fixtures; label live coverage honestly.
