import { describe, expect, it } from 'vitest';
import type { PaperLintRuleRun } from '../src/api/paperLint';
import { genericExecutionWarnings, numericExecutionWarnings, paperLintPresentation } from '../src/components/paperLint/model';

const numericRule = 'abstract_numeric_consistency_check';
const run = (value: Partial<PaperLintRuleRun>): PaperLintRuleRun => ({ rule_id: numericRule, rule_run_id: 'run', severity: 'warning', execution_status: 'completed', outcome: 'not_applicable', findings: [], ...value });

describe('execution warning feedback identities', () => {
  it('adapts each visible numeric warning to a stable, collision-free feedback target', () => {
    const rawId = `execution-warning:${numericRule}:precondition:abstract_numeric`;
    const input = run({ execution_status: 'error', findings: [{ finding_id: rawId, rule_id: numericRule, message: 'raw' }], params: { preconditions: [
      { id: 'abstract_numeric', passed: false }, { id: 'contribution_mapping', passed: false, status: 'skipped' }, { id: 'abstract_numeric', passed: false },
    ] } });
    const before = JSON.stringify(input);
    const targets = numericExecutionWarnings(input).map(warning => warning.feedbackTarget);
    expect(targets.map(item => item?.finding.finding_id)).toEqual([`${rawId}:2`, `${rawId}:3`, `execution-warning:${numericRule}:failure`]);
    expect(new Set(targets.map(item => item?.key)).size).toBe(3);
    expect(targets.every(item => item?.ruleRun.rule_id === numericRule)).toBe(true);
    expect(JSON.stringify(input)).toBe(before);
    expect(numericExecutionWarnings(input).map(warning => warning.feedbackTarget?.key)).toEqual(targets.map(item => item?.key));
  });

  it.each([{ execution_status: 'error' }, { params: { failure: 'timeout' } }, { params: { validation_errors: [{ declaration_id: 'd1' }] } }] as Partial<PaperLintRuleRun>[])('gives numeric execution failures a feedback identity', value => {
    expect(numericExecutionWarnings(run(value)).map(warning => warning.feedbackTarget?.finding.finding_id))
      .toEqual([`execution-warning:${numericRule}:failure`]);
  });

  it('keeps resource-warning identities unchanged by the shared report presentation', () => {
    const input = run({ rule_id: 'sjtu_rule_32', params: { reference_resources_unavailable: true }, findings: [
      { finding_id: 'reference-info-blocked', rule_id: 'sjtu_rule_32', message: '未完成', prompt_only: true },
      { finding_id: 'real-reference', rule_id: 'sjtu_rule_32', message: '已检索', reference_review: 'supported_suspicion' },
    ] });
    const before = JSON.stringify(input);
    const result = paperLintPresentation({ rule_runs: [input], summary: {} } as never);
    expect(genericExecutionWarnings(result.rule_runs)[0].feedbackTarget?.finding.finding_id)
      .toBe('execution-warning:sjtu_rule_32:generic');
    expect(JSON.stringify(input)).toBe(before);
  });

  it('adapts generic execution warnings, excluding successful and skipped runs', () => {
    const warnings = genericExecutionWarnings([
      run({ rule_id: 'keyword_count_check', execution_status: 'unsupported' }),
      run({ rule_id: 'sjtu_rule_32', params: { reference_resources_unavailable: true } }),
      run({ rule_id: 'sjtu_rule_18', outcome: 'passed' }),
    ]);
    expect(warnings.map(warning => warning.feedbackTarget?.finding.finding_id)).toEqual([
      'execution-warning:keyword_count_check:generic', 'execution-warning:sjtu_rule_32:generic',
    ]);
  });
});
