import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require = createRequire(import.meta.url);
const service = require('../src/normative/reviewPilotPaperLintService');

const oldBackend = process.env.REVIEW_PILOT_BACKEND_DIR;
const oldPython = process.env.FIVE_RULE_PYTHON;
const fixture = path.resolve(__dirname, 'fixtures/local-four-rule-sample.pdf');

beforeEach(() => {
  process.env.REVIEW_PILOT_BACKEND_DIR = path.resolve(__dirname, 'fixtures/no-review-pilot-backend');
  if (process.env.FIVE_RULE_TEST_PYTHON) process.env.FIVE_RULE_PYTHON = process.env.FIVE_RULE_TEST_PYTHON;
});
afterEach(() => {
  if (oldBackend === undefined) delete process.env.REVIEW_PILOT_BACKEND_DIR;
  else process.env.REVIEW_PILOT_BACKEND_DIR = oldBackend;
  if (oldPython === undefined) delete process.env.FIVE_RULE_PYTHON;
  else process.env.FIVE_RULE_PYTHON = oldPython;
});

describe('four local rules in the existing basic-check flow', () => {
  it('shows the four selectable rules even when review-pilot is not installed', async () => {
    const catalog = await service.getPaperLintCatalog({ refresh: true });
    expect(catalog.rules.map((rule) => rule.rule_id)).toEqual([
      'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28',
    ]);
    expect(catalog.rules.every((rule) => rule.available && !rule.uses_external_model)).toBe(true);
  });

  it('retries the existing catalog after a temporary fallback', async () => {
    const enginePath = path.join(process.env.REVIEW_PILOT_BACKEND_DIR, 'novref', 'domain', 'paper_lint');
    const exists = vi.spyOn(fs, 'existsSync');
    try {
      await service.getPaperLintCatalog({ refresh: true });
      const firstCount = exists.mock.calls.filter(([candidate]) => candidate === enginePath).length;
      await service.getPaperLintCatalog();
      const secondCount = exists.mock.calls.filter(([candidate]) => candidate === enginePath).length;
      expect(secondCount).toBeGreaterThan(firstCount);
    } finally {
      exists.mockRestore();
    }
  });

  it.skipIf(!process.env.FIVE_RULE_TEST_PYTHON)('stops a run at its total deadline', async () => {
    const previous = process.env.PAPER_LINT_RUN_TIMEOUT_MS;
    process.env.PAPER_LINT_RUN_TIMEOUT_MS = '1';
    try {
      await expect(service.runPaperLint({
        pdfBuffer: fs.readFileSync(fixture), selectedRuleIds: ['sjtu_rule_22'],
      })).rejects.toMatchObject({ status: 504 });
    } finally {
      if (previous === undefined) delete process.env.PAPER_LINT_RUN_TIMEOUT_MS;
      else process.env.PAPER_LINT_RUN_TIMEOUT_MS = previous;
    }
  }, 20000);

  it.skipIf(!process.env.FIVE_RULE_TEST_PYTHON)('runs selected rules on an uploaded PDF without review-pilot and keeps both exact positions', async () => {
    const { result, selectedRuleIds } = await service.runPaperLint({
      pdfBuffer: fs.readFileSync(fixture),
      selectedRuleIds: ['sjtu_rule_22', 'sjtu_rule_24'],
    });
    expect(selectedRuleIds).toEqual(['sjtu_rule_22', 'sjtu_rule_24']);
    expect(result.rule_runs.map((run) => [run.rule_id, run.outcome])).toEqual([
      ['sjtu_rule_22', 'issues_found'], ['sjtu_rule_24', 'issues_found'],
    ]);
    expect(result.rule_runs[0].findings[0].location).toMatchObject({ type: 'pdf_bbox', page_number: 1 });
    expect(result.rule_runs[1].findings[0].location).toMatchObject({ type: 'pdf_bbox', page_number: 2 });
    expect(result.summary).toMatchObject({ rule_count: 2, finding_count: 2 });
  }, 20000);
});
describe('mixed report ordering', () => {
  it('keeps selected rule order and recomputes counts after joining local and existing findings', () => {
    const localRun = { rule_run_id: 'run_local', rule_id: 'sjtu_rule_22', severity: 'warning',
      execution_status: 'completed', evidence_mode: 'native', outcome: 'issues_found',
      findings: [{ finding_id: 'local-1' }] };
    const existingRun = { rule_run_id: 'run_existing', rule_id: 'chinese_title_format_check', severity: 'warning',
      execution_status: 'completed', evidence_mode: 'derived', outcome: 'passed', findings: [] };
    const result = service.mergePaperLintResults(
      { type: 'paper_lint', paper_title: '测试论文', ruleset: { id: 'original' }, rule_runs: [existingRun] },
      { type: 'paper_lint', rule_runs: [localRun] },
      ['sjtu_rule_22', 'chinese_title_format_check'],
    );
    expect(result.rule_runs.map((run) => run.rule_id)).toEqual(['sjtu_rule_22', 'chinese_title_format_check']);
    expect(result.paper_title).toBe('测试论文');
    expect(result.summary).toMatchObject({ rule_count: 2, finding_count: 1,
      issue_rule_count: 1, derived_rule_count: 1 });
  });
});