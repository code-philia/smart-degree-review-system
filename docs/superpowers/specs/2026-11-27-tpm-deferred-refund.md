# Hold TPM reservations through asynchronous gateway settlement

The external eight-paper typo benchmark received a TPM429 even though its local
budget was below300000. Two response receipts had just released7654 and7576
reserved tokens locally. The next8663-token request saw local remaining17191,
while the gateway reported remaining1961: exactly15230 tokens less. Published
LiteLLM1.87 success settlement runs through an asynchronous logging callback;
response receipt is not an acknowledgement that this refund has completed.

Keep the independent TPM-budget and RPM-dispatch queues. For every sent request,
retain at least its estimated input plus declared output reservation until60
seconds after completion. Valid actual input/output usage can increase this
balance but cannot reduce it early, including successful zero-usage responses.
Billing and displayed actual token usage remain based on confirmed usage.
Unknown outcomes retain the estimate; known rejection or preflight cancellation
may refund immediately. Unsent cancellation still releases its reservation.

Persist a once-only policy marker. When upgrading an existing token ledger,
hold admission for one full window to cover old prematurely reduced balances.
Existing in-flight leases, heartbeat renewal, deadlines, RPM pacing and API-slot
behavior stay unchanged. Full-window reservations trade throughput for avoiding
unacknowledged refunds; no short arbitrary refund delay is assumed safe.

Apply the same rule to the isolated benchmark broker. Record its settlement
policy and reject resuming a run with a different policy. Restart at r4-c8 with
fresh caches and receipts; retain the earlier15 completed groups with their old
release/policy provenance, archive the failed/later groups, then continue through
all64-paper tiers. Do not deploy to the campus host.

Validation: exact15230-token incident, zero-usage success, once-only migration,
known rejection, larger actual usage, in-flight retention, cancellation, separate
queue metrics, real cross-process coordination and a real60-second offline
broker window. Review the patch, publish through the existing release tool,
verify source hashes and service/data health, then resume the authorized test.
