# Reference verification latency

Optimize the existing rule without weakening identity, source provenance, explicit arXiv version matching, frozen snapshots, or provider admission limits.

1. Batch uncached exact arXiv metadata IDs in groups of at most 20, deduplicating IDs and populating the existing per-ID cache. Keep the existing single-connection/three-second admission policy. A failed batch must leave ordinary source fallbacks available.
2. Deduplicate identical reference queries within a run. Use at most eight lookup workers while preserving the existing OpenAlex four-request semaphore and per-source rate locks. Keep evidence and identity writes on the caller thread.
3. Add regressions for batching, missing/wrong versions, cache/frozen behavior, query deduplication, bounded parallel work and error isolation. Measure request counts and a reproducible latency fixture; run the affected evidence and analysis checks before committing and pushing main.

Successful caches and historical report data retain their semantics. No paid-model extraction policy or request-protection record is changed.

## Validation

- New regressions reproduced missing batching/deduplication and an unnecessary successful-cache refresh before their respective fixes.
- 165 related extraction, identity, evidence, cache, frozen-snapshot and publication checks passed.
- Live cold-cache exact arXiv metadata benchmark for three known works: sequential 7.287 seconds / three requests; batch 1.261 seconds / one request. Both returned metadata for all three. This does not measure full-report latency.
- Deterministic fixture: forty uncached identifiers plus duplicates require two HTTP requests; a repeat requires zero additional requests.
- Independent review found no critical or important issues. Remote main remains `8dbd2ca` before integration.
