# R32 SerpAPI verification

R32 calls `EvidenceGateway.lookup_rule32` -> `SerpApiScholar.lookup_many` ->
`https://serpapi.com/search.json` with the Google Scholar engine. Other rules may
still use public sources. `PAPER_COMPILER_LIVE_EVIDENCE_PROVIDERS` does not select
the R32 provider and should not contain `serpapi`.

The service must load `SERPAPI_API_KEY` (or the existing `SERPAPI_CONFIG` private
file). `PAPER_COMPILER_REFERENCE_LIBRARY` optionally selects its persistent cache;
the default is `<compiler cache>/public-evidence/reference-library`.

Both analysis cache policies now identify the Scholar route, so old public-source
analysis is not reused as evidence of a Scholar request. A cached Scholar result
is still usable without a new paid request. A persisted exhausted-quota marker
blocks uncached requests until an administrator reviews it after quota renewal.

## Isolated verification

Run `python backend/scripts/probe_serpapi.py` for a synthetic quota response. Its
JSON says `live: false`; this does not verify the real account balance.

For a real probe, an administrator should first stage this code in a root-owned
release. Set `RELEASE` to that release, then run as root:

```bash
systemd-run --unit=smart-degree-serpapi-probe --collect --wait --pipe \
  --property=User=smart-degree-svc \
  --property=Group=smart-degree-svc \
  --property=EnvironmentFile=/srv/smart-degree/config/serp.env \
  /srv/smart-degree/workspace/.venv/bin/python \
  "$RELEASE/backend/scripts/probe_serpapi.py" --live
```

This loads only the SerpAPI credentials into the service user, uses a temporary
library, and queries a public synthetic example rather than any uploaded paper.
It makes up to three real searches and may consume quota. Output includes only
the provider, live flag, request host/count and sanitized status. It never prints
request URLs, credentials or result contents. `quota_exhausted` with `live: true`
and a request count above zero confirms the real account returned a quota error.
`provider_unavailable` is not proof of quota exhaustion.

## Result semantics

Quota exhaustion is preserved as `SERPAPI_QUOTA_EXHAUSTED` through parallel
prefetch and rule evaluation. The rule remains `inconclusive`, and the API and
UI show "SerpAPI 额度已用尽". Unresolved entries are informational notices,
not confirmed missing citations. Exported reports preserve the same distinction.
No database migration or production data rewrite is required.
