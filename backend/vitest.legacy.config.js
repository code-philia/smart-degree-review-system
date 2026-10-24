const { defineConfig } = require('vitest/config');

// Legacy/non-MVP tests remain runnable, but are intentionally not part of the
// MVP gate. They document retired rule catalogs and older background-job
// contracts which must be migrated separately rather than weakened or deleted.
module.exports = defineConfig({
  test: {
    environment: 'node',
    include: [
      'tests/paper-lint-jobs.test.js',
      'tests/paper-lint-extended-rules.test.js',
      'tests/review-pilot-six-rule-budget.test.js',
      'tests/retired-rule-*.test.js',
    ],
    exclude: ['test-e2e/**/*'],
  },
});
