function jobConcurrency() {
  const engine = Number(process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS);
  const maximum = Number.isFinite(engine) && engine !== 0 ? Math.max(1, Math.floor(engine)) : 2;
  const requested = Number(process.env.PAPER_LINT_JOB_CONCURRENCY);
  return Math.min(Number.isSafeInteger(requested) && requested > 0 ? requested : maximum, maximum, 32);
}

module.exports = { jobConcurrency };
