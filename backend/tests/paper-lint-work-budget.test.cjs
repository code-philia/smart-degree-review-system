const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createRunTimeout } = require('../src/normative/paperLintRuleProgress');

function setup(t, maximumMs = 7200000) {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  const controller = new AbortController();
  const expired = [];
  assert.equal(typeof createRunTimeout, 'function', 'A real bounded progress budget is required');
  const budget = createRunTimeout({ timeoutMs:1200000, maximumMs, signal:controller.signal,
    onTimeout: () => expired.push(Date.now()) });
  t.after(() => { budget.clear(); t.mock.timers.reset(); });
  return { budget, controller, expired };
}

test('successful new work may cross twenty minutes but expires after twenty idle minutes', t => {
  const { budget, expired } = setup(t);
  t.mock.timers.tick(19 * 60000); budget.progress();
  t.mock.timers.tick(19 * 60000); assert.equal(expired.length, 0);
  t.mock.timers.tick(60001); assert.equal(expired.length, 1);
});

test('continuous work cannot exceed the absolute two-hour bound', t => {
  const { budget, expired } = setup(t);
  for (let i=0; i<7; i++) { t.mock.timers.tick(19 * 60000); budget.progress(); }
  assert.equal(expired.length, 1);
  t.mock.timers.tick(20 * 60000); budget.progress();
  assert.equal(expired.length, 1);
});

test('ordinary budgets ignore progress beyond the original hard deadline', t => {
  const { budget, expired } = setup(t, 1200000);
  t.mock.timers.tick(19 * 60000); budget.progress();
  t.mock.timers.tick(60001); assert.equal(expired.length, 1);
});

test('cancellation and cleared work cannot renew or trigger another timer', t => {
  const { budget, controller, expired } = setup(t);
  t.mock.timers.tick(19 * 60000); controller.abort(); budget.progress();
  budget.clear(); t.mock.timers.tick(7200001);
  assert.equal(expired.length, 0);
});
