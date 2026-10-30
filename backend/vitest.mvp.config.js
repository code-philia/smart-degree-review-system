const { defineConfig } = require('vitest/config');

module.exports = defineConfig({
  test: {
    environment: 'node',
    include: [
      'tests/auth-password.integration.test.js',
      'tests/auth-session.integration.test.js',
      'tests/internal-readiness.test.js',
      'tests/local-five-rule-paper-lint.test.js',
      'tests/local-five-rule-integration.test.js',
      'tests/paper-lint-feedback.integration.test.js',
      'tests/paper-lint-controls.test.js',
      'tests/paper-lint-process-cancellation.test.js',
      'tests/paper-lint-repair-suggestion.integration.test.js',
      'tests/paper-lint-rule-runner.test.js',
      'tests/review-pilot-paper-lint.integration.test.js',
      'tests/rule-registry.test.js',
    ],
    exclude: ['test-e2e/**/*'],
  },
});
