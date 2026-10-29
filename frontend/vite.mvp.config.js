import baseConfig from './vite.config.js';

export default {
  ...baseConfig,
  test: {
    ...baseConfig.test,
    include: [
      'tests/auth-password.test.tsx',
      'tests/auth-session.test.tsx',
      'tests/local-four-rule-history.test.tsx',
      'tests/paper-lint-job-controls.test.tsx',
      'tests/paper-lint-history-controls.test.tsx',
      'tests/local-four-rule-report.test.tsx',
      'tests/paper-lint-finding-order.test.ts',
      'tests/paper-lint-findings-navigation.test.tsx',
      'tests/paper-lint-geometry.test.ts',
      'tests/paper-lint-pane-navigation.test.tsx',
      'tests/paper-lint-repair-isolation.test.tsx',
      'tests/paper-lint-viewer-navigation.test.tsx',
      'tests/paper-lint-workspace-navigation.test.tsx',
    ],
  },
};
