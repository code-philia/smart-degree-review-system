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


it('renews only matching successful new typo chunks, and never treats work as a completed rule', async () => {
  const received = [], work = [];
  const stream = createRuleProgressStream(['typo_detection_check'], run => received.push(run), {
    taskId: 'private-task', onWorkProgress: event => work.push(event.completed_chunks),
  });
  const valid = { type: 'paper_lint_chunk_complete', task_id: 'private-task', rule_id: 'typo_detection_check',
    execution_status: 'completed', chunk_index: 0, completed_chunks: 1, total_chunks: 3 };
  const send = event => stream.write(Buffer.from(JSON.stringify(event) + '\n'));
  for (const event of [{ ...valid, task_id: 'other' }, { ...valid, execution_status: 'error' },
    { ...valid, completed_chunks: 2 }, { ...valid, chunk_index: -1 }, { ...valid, total_chunks: 0 }]) send(event);
  send(valid); send(valid);
  send({ ...valid, chunk_index: 1, completed_chunks: 2, total_chunks: 4 });
  send({ ...valid, chunk_index: 1, completed_chunks: 0 });
  send({ ...valid, chunk_index: 1, completed_chunks: 2 });
  send({ ...valid, chunk_index: 2, completed_chunks: 3 });
  await stream.finish();
  expect(work).toEqual([1, 2, 3]);
  expect(received).toEqual([]);
});

it('ignores chunk work without the private callback and task identity', async () => {
  const received = [];
  const stream = createRuleProgressStream(['typo_detection_check'], run => received.push(run));
  stream.write(Buffer.from(JSON.stringify({ type: 'paper_lint_chunk_complete', task_id: 'private-task',
    rule_id: 'typo_detection_check', execution_status: 'completed', chunk_index: 0, completed_chunks: 1, total_chunks: 1 }) + '\n'));
  await stream.finish();
  expect(received).toEqual([]);
});
