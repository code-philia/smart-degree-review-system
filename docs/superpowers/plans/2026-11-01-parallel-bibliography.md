# Parallel Bibliography Extraction Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this single task with test-driven development and a final code review.

**Goal:** Remove the measured Rule 32 bibliography extraction bottleneck without changing detection evidence or prompts.

**Architecture:** Run independent campus model extraction batches with at most eight workers. Merge answers on the caller thread in source order. Preserve the shared account limiter, request cache, model error handling, and task deadlines.

**Tech Stack:** Python standard library ThreadPoolExecutor and existing pytest fixtures.

**Spec:** The user's request to optimize response time follows the measured serial bibliography bottleneck. Preserve existing detector semantics; deploy tested changes to the public server.

## Global Constraints

- Keep 8 concurrent campus HTTP requests and 90 request starts per minute across processes.
- Preserve non-campus request ordering, batch content, prompts, cache keys, source quotes, and accounting.
- Do not use OCR or add model calls to local detectors.
- Commit and push English Conventional Commits on main; preserve production data and in-flight work during release activation.

## Review Focus

- Responses finish out of order: findings and evidence must still match the serial result.
- One batch has a recoverable ModelError: its entries remain unknown and independent batches complete.
- A fatal deadline or budget error: propagate it and cancel requests that have not started.
- No client or non-campus client: retain existing serial behavior.
- Many entries: bound outstanding work rather than queue every request at once.

### Task 1: Parallel campus bibliography batches

**Files:** Modify backend/paper_compiler/analysis.py; add backend/tests_py/test_bibliography_parallelism.py.

- [ ] Write overlap, result-equivalence, isolated-error and fatal-error tests; observe overlap fail on serial code.
- [ ] Add bounded parallel campus batch requests, retaining ordered caller-thread result validation.
- [ ] Run bibliography, extraction, accounting, shared-limiter and compiler regressions; compare existing failures against baseline.
- [ ] Review the change and benchmark identical extraction inputs under serial and parallel scheduling.
- [ ] Commit, push main, deploy with the existing publisher, verify health, concurrency and preserved history.
