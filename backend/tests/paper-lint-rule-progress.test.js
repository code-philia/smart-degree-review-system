import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const { createRuleProgressStream } = require('../src/normative/paperLintRuleProgress');

it('publishes UTF-8 JSONL completions before EOF, deduplicates IDs, and awaits ordered persistence', async () => {
  const received = [];
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  const stream = createRuleProgressStream(['a', 'b'], async run => {
    if (run.rule_id === 'a') await wait;
    received.push(run.message);
  });
  const event = (id, message) => JSON.stringify({ type: 'paper_lint_rule_complete', rule_run: {
    rule_id: id, execution_status: 'completed', findings: [], message,
  } }) + '\n';
  const first = Buffer.from('initialization log\n' + event('a', '中文完成'));
  const split = first.indexOf(Buffer.from('中')) + 1;
  stream.write(first.subarray(0, split));
  stream.write(first.subarray(split));
  stream.write(Buffer.from(event('a', 'duplicate') + event('unknown', 'ignored') + event('b', '第二条')));
  await Promise.resolve();
  expect(received).toEqual([]);
  release();
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(received).toEqual(['中文完成', '第二条']);
  await stream.finish();
});

it('propagates asynchronous persistence failure without an unhandled rejection', async () => {
  const stream = createRuleProgressStream(['a'], async () => { throw new Error('database unavailable'); });
  stream.write(Buffer.from(JSON.stringify({ type: 'paper_lint_rule_complete', rule_run: {
    rule_id: 'a', execution_status: 'completed', findings: [],
  } }) + '\n'));
  await expect(stream.finish()).rejects.toThrow('database unavailable');
});
