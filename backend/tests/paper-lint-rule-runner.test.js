import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { runPaperLintRuleGroups } = require('../src/normative/paperLintRuleRunner');

describe('paper lint rule runner', () => {
  it('waits for every parallel detector to stop before returning the first failure', async () => {
    let release;
    const slow = new Promise(resolve => { release = resolve; });
    let settled = false;
    const first = new Error('cancelled');
    const execution = runPaperLintRuleGroups({
      pdfPath: '/tmp/input.pdf', selectedRuleIds: ['sjtu_rule_18', 'sjtu_rule_15'],
      runners: { local_pdf: async () => { throw first; }, six_pdf: () => slow },
    }).catch(error => { settled = true; return error; });
    await new Promise(resolve => setTimeout(resolve, 25));
    const returnedBeforeCleanup = settled;
    release({ rule_runs: [] });
    expect(await execution).toBe(first);
    expect(returnedBeforeCleanup).toBe(false);
  });
  it('dispatches registry families without changing detector ownership', async () => {
    const calls = [];
    const result = await runPaperLintRuleGroups({
      pdfPath: '/tmp/input.pdf',
      selectedRuleIds: ['sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_15', 'legacy_rule'],
      runners: {
        local_pdf: async (_path, ids) => { calls.push(['local', ids]); return { rule_runs: ids.map((rule_id) => ({ rule_id })) }; },
        six_pdf: async (_path, ids) => { calls.push(['six', ids]); return { rule_runs: ids.map((rule_id) => ({ rule_id })) }; },
        legacy_bridge: async (_path, ids) => { calls.push(['legacy', ids]); return { rule_runs: ids.map((rule_id) => ({ rule_id })) }; },
      },
    });
    expect(calls).toEqual([
      ['local', ['sjtu_rule_18', 'sjtu_rule_22']],
      ['six', ['sjtu_rule_15']],
      ['legacy', ['legacy_rule']],
    ]);
    expect(result.flatMap((part) => part.rule_runs).map((run) => run.rule_id)).toEqual([
      'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_15', 'legacy_rule',
    ]);
  });
});
