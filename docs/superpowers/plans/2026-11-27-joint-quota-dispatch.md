# Joint quota dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Stop queued requests from occupying the other quota before they can dispatch.
**Architecture:** Preserve two wait queues and stable FIFO tickets; check RPM first and commit both quotas atomically at dispatch. Keep existing transport and settlement behavior.
**Tech Stack:** Python, SQLite transactions, asyncio broker, pytest/unittest.
**Spec:** docs/superpowers/specs/2026-11-27-joint-quota-dispatch-design.md

## Global Constraints

- External deployment only; no model calls or pressure test restart.
- Preserve existing report data and the immediate actual-usage settlement policy.
- Production remains paced 100 RPM with its concurrency cap; benchmark remains rolling 100 RPM without a slot cap.
- Two queues; at most one waiting queue per request; no quota or lease held while waiting.

## Review Focus

- TPM availability can change before RPM becomes ready: both must be rechecked under the dispatch lock.
- Queue transfers must retain age and avoid starvation or cyclic promotion.
- Scope cancellation immediately before dispatch must not consume either quota.
- Worker death during a request must retain the bounded unknown-usage budget.
- Legacy result directories must not resume with the changed queue policy.

### Task 1: Production and broker admission

**Files:** backend/paper_compiler/campus_requests.py; backend/tests_py/test_campus_joint_admission.py; output/archive-four64-owned-20261127/{tpm_budget.py,measure.py,check_tpm_queues.py,check_broker_socket.py}.
**Interfaces:** Keep campus_request/campus_request_slot callers unchanged. Add optional token_budget to coordinator.slot; use it for joint admission. Preserve legacy low-level token_slot/token_reservation compatibility and existing settlement semantics.

- [x] Add failing tests for RPM wait with no token reservation, RPM-first reason when both unavailable, TPM wait with no RPM consumption, rechecking after transfers, FIFO transfers, cancellation and cross-instance atomicity.
- [x] Run those tests; expect failures against the old implementation.
- [x] Implement atomic dispatch and synchronize local broker/logging/policy guards.
- [x] Run campus quota/transport tests and all offline harness checks; expect pass and no real HTTP.
- [x] Commit exact source, tests and design/plan files; archive local harness manifest separately.

### Task 2: Verify, push and deploy externally

**Files:** deployment receipts under output/joint-quota-dispatch-20261127/; existing official external publisher.
**Interfaces:** Deploy the committed official origin/main source, guarded against an unexpected active release. Capture existing DB row hashes and verify them after deployment.

- [ ] Fresh review of the complete change; fix important findings with regression tests.
- [ ] Push and verify the official main SHA.
- [ ] Deploy through the existing publisher; verify source hashes, health, old process exit and DB preservation without model requests.
- [ ] Verify benchmark controllers remain stopped and report artifacts unchanged.
