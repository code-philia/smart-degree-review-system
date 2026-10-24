import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { runPaperLintRuleGroups } = require('../src/normative/paperLintRuleRunner');

describe('paper lint rule runner', () => {
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
