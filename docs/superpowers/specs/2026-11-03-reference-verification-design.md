# Free multi-source reference verification

Approved scope: the user requested the previously proposed free multi-source lookup, supplied three independent OpenAlex credentials, excluded Semantic Scholar, and authorized main push and campus deployment.

Use the existing evidence gateway and strict identity resolver. Prefer exact DOI/arXiv identities and OpenAlex title lookup; fall back to Crossref, DataCite and Europe PMC. Persist public evidence in a shared bounded-TTL cache and pace each source independently. Keep credentials only in the private campus configuration, never in URLs, logs, reports or Git. Balance OpenAlex requests deterministically across the supplied keys, respecting each key's limits. No paid subscriptions or Semantic Scholar.

A matching title alone is insufficient. Public empty responses, rate limits and timeouts never prove nonexistence. Preserve UNKNOWN with actionable reasons. Publish R32 PASS only when actual per-reference PASS records and complete bibliography coverage support it; preserve positive-publication behavior for other rules. Existing historical reports remain immutable; explain their retained diagnostic reasons in the UI and allow incremental reruns to refresh unresolved evidence.

Alternatives: retaining SerpAPI alone preserves the quota single point of failure; replacing it with one free provider retains a different single point of failure. Reusing the existing free-provider gateway best fits the approved scope. DBLP/ChinaXiv are not claimed operational until their machine endpoints are verified.
