# Formal login branch update and independent external preview

**Goal:** Update `feat/login-v2-split` with current main, preserve the teammate's formal split layout, and serve it on an independent external port.

**Authority:** User explicitly requested updating this branch and deploying to another port; explicitly forbids modifying main. No design changes or new UI wording are requested.

**Architecture:** Merge main into the feature branch only. Build an isolated frontend release. A separate static/proxy process serves that release and forwards `/api` to the existing public backend on port 3000. It does not load the application/database/workers or require production secrets. Existing jAccount registered callback remains unchanged.

**Constraints:** Preserve main ref, production symlink/PID/config and existing backend data; no force pushes. Preserve illustration/layout and bilingual functionality. Keep the main campus scene component available and test it independently. Preload only the active formal illustration on this branch.

- [x] Inspect both remote refs and branch difference; merge latest main into the feature branch.
- [ ] Verify authentication/session tests, correct the missing existing accessibility label and obsolete scene tests, and bind preload to the actual formal illustration.
- [ ] Test the independent server: API path/body/cookie streaming, fixed upstream, origin handling, API misses, unavailable backend, and no private backend import.
- [ ] Run related frontend/backend tests and a clean frontend build; independently review the branch and deployment boundary.
- [ ] Fast-forward push only `feat/login-v2-split`; deploy a separate service on an available public port, verify externally and compare production/main before and after.

## Review focus

API forwarding must target port 3000, never the private administrator listener. Only the configured preview origin may be translated to the existing public origin. OAuth callback remains registered with the existing deployment; no fabricated end-to-end jAccount account test. Static resource misses must remain 404, HTML must not be cached, and main's process must not restart.
