const { defineConfig } = require('vitest/config');

module.exports = defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.{test,spec}.{js,jsx,ts,tsx,mjs}'],
    exclude: ['test-e2e/**/*'],
  },
});
