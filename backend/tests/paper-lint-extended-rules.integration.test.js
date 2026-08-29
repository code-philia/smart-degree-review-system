import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const paperLintService = require('../src/normative/reviewPilotPaperLintService');

const engineDir = paperLintService.resolveEngineBackendDir();
const engineAvailable = fs.existsSync(path.join(engineDir, 'novref', 'domain', 'paper_lint'));
const enginePython = process.env.REVIEW_PILOT_PYTHON
  || (fs.existsSync(path.join(engineDir, '.venv', 'bin', 'python'))
    ? path.join(engineDir, '.venv', 'bin', 'python')
    : 'python3');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'paper-lint-extended-rules-'));

function createPdf(lines, filename) {
  const target = path.join(tempRoot, filename);
  const script = [
    'import fitz, json, sys',
    'doc = fitz.open()',
    'page = doc.new_page(width=595, height=842)',
    'y = 72',
    'for line in json.load(sys.stdin):',
    '    if y > 790:',
    '        page = doc.new_page(width=595, height=842)',
    '        y = 72',
    '    page.insert_text((72, y), line, fontname="helv", fontsize=10)',
    '    y += 24',
    'doc.save(sys.argv[1])',
    'doc.close()',
  ].join('\n');
  execFileSync(enginePython, ['-c', script, target], {
    cwd: engineDir,
    input: JSON.stringify(lines),
  });
  return fs.readFileSync(target);
}

function ruleRun(result, ruleId) {
  return result.result.rule_runs.find((run) => run.rule_id === ruleId);
}

afterAll(() => fs.rmSync(tempRoot, { recursive: true, force: true }));

const describeWithEngine = engineAvailable ? describe : describe.skip;

describeWithEngine('extended deterministic PDF rules', () => {
  it('publishes the two new checks in the 22-rule deterministic catalog', async () => {
    const catalog = await paperLintService.getPaperLintCatalog({ refresh: true });
    const deterministicRules = catalog.rules.filter((rule) => rule.execution_mode === 'deterministic');

    expect(deterministicRules).toHaveLength(22);
    expect(deterministicRules).toEqual(expect.arrayContaining([
      expect.objectContaining({
        rule_id: 'reference_basic_format_check',
        title: '参考文献格式一致性',
        default_enabled: true,
      }),
      expect.objectContaining({ rule_id: 'figure_reference_target_check', default_enabled: true }),
      expect.objectContaining({ rule_id: 'table_reference_target_check', default_enabled: true }),
    ]));
  });

  it.each([
    {
      name: 'GB/T 7714',
      lines: [
        '[1] A. Author. Sample article[J]. Journal, 2023, 1(2): 1-4.',
        '[2] B. Author. Sample book[M]. City: Publisher, 2022.',
        '[3] C. Author. Sample thesis[D]. University, 2021.',
      ],
    },
    {
      name: 'APA 7',
      lines: [
        'Author, A. A. (2023). Sample article. Journal Name, 1(2), 1-4.',
        'Brown, B. B. (2022). Sample book. Example Publisher.',
        'Clark, C. C. (2021). Sample report. Example Institute.',
      ],
    },
    {
      name: 'IEEE',
      lines: [
        '[1] A. Author, "Sample article," Journal Name, vol. 1, no. 2, pp. 1-4, 2023.',
        '[2] B. Brown, "Second article," Journal Name, vol. 2, no. 1, pp. 5-8, 2022.',
        '[3] C. Clark, "Third article," Proc. Example Conf., pp. 9-12, 2021.',
      ],
    },
  ])('automatically recognizes a uniform $name bibliography', async ({ name, lines }) => {
    const safeName = name.replaceAll(/[^A-Za-z0-9]+/g, '-');
    const pdfBuffer = createPdf(['Paper title', 'References', ...lines], `${safeName}.pdf`);

    const result = await paperLintService.runPaperLint({
      pdfBuffer,
      selectedRuleIds: ['reference_basic_format_check'],
    });
    const run = ruleRun(result, 'reference_basic_format_check');

    expect(run).toMatchObject({ execution_status: 'completed', outcome: 'passed' });
    expect(run.message).toContain(name);
  });

  it('reports entries that differ from the automatically detected dominant style', async () => {
    const pdfBuffer = createPdf([
      'Paper title',
      'References',
      '[1] A. Author. Sample article[J]. Journal, 2023, 1(2): 1-4.',
      '[2] B. Author. Sample book[M]. City: Publisher, 2022.',
      '[3] C. Author. Sample thesis[D]. University, 2021.',
      'Brown, B. B. (2020). Mixed style entry. Example Publisher.',
    ], 'mixed-references.pdf');

    const result = await paperLintService.runPaperLint({
      pdfBuffer,
      selectedRuleIds: ['reference_basic_format_check'],
    });
    const run = ruleRun(result, 'reference_basic_format_check');

    expect(run).toMatchObject({ execution_status: 'completed', outcome: 'issues_found' });
    expect(run.message).toContain('GB/T 7714');
    expect(run.findings.some((finding) => finding.message.includes('APA 7'))).toBe(true);
  });

  it('keeps volume-like continuation lines inside the preceding GB/T entry', async () => {
    const pdfBuffer = createPdf([
      'Paper title',
      'References',
      '[1] A. Author. Sample conference paper[C]//Neural com-',
      'putation. Volume',
      '8. 1997: 1735-1780.',
      '[2] B. Author. Sample book[M]. City: Publisher, 2022.',
    ], 'multiline-gbt-references.pdf');

    const result = await paperLintService.runPaperLint({
      pdfBuffer,
      selectedRuleIds: ['reference_basic_format_check'],
    });
    const run = ruleRun(result, 'reference_basic_format_check');

    expect(run).toMatchObject({ execution_status: 'completed', outcome: 'passed' });
    expect(run.message).toContain('GB/T 7714');
  });

  it('does not invent a dominant style when the detected styles are tied', async () => {
    const pdfBuffer = createPdf([
      'Paper title',
      'References',
      '[1] A. Author. Sample article[J]. Journal, 2023, 1(2): 1-4.',
      '[2] B. Author. Sample book[M]. City: Publisher, 2022.',
      'Brown, B. B. (2021). APA entry one. Example Publisher.',
      'Clark, C. C. (2020). APA entry two. Example Publisher.',
    ], 'tied-reference-styles.pdf');

    const result = await paperLintService.runPaperLint({
      pdfBuffer,
      selectedRuleIds: ['reference_basic_format_check'],
    });
    const run = ruleRun(result, 'reference_basic_format_check');

    expect(run).toMatchObject({
      execution_status: 'completed',
      outcome: 'issues_found',
      message: 'reference_style_inconclusive',
    });
    expect(run.findings[0].message).toContain('无法稳定判断');
  });

  it('stops before a split appendix heading instead of treating appendix prose as APA 7', async () => {
    const pdfBuffer = createPdf([
      'Paper title',
      'References',
      'A. Author. Venue-specific reference, 2023.',
      'A',
      'DATASET DETAILS',
      'WikiSQL is introduced in Zhong et al. (2017). This is body prose.',
      'Another method follows Smith et al. (2020). This is also body prose.',
    ], 'split-appendix-after-references.pdf');

    const result = await paperLintService.runPaperLint({
      pdfBuffer,
      selectedRuleIds: ['reference_basic_format_check'],
    });
    const run = ruleRun(result, 'reference_basic_format_check');

    expect(run).toMatchObject({
      execution_status: 'completed',
      outcome: 'issues_found',
      message: 'reference_style_inconclusive',
    });
    expect(run.findings[0].message).not.toContain('APA 7');
  });

  it('reports body figure and table references without matching captions', async () => {
    const pdfBuffer = createPdf([
      'Paper title',
      'The existing architecture is shown in Figure 1.',
      'Figure 2 is shown in the discussion but has no caption.',
      'The existing values are listed in Table 3.',
      'Table 4 lists missing values but has no caption.',
      'Figure 1 Existing architecture',
      'Table 3 Existing values',
      'References',
      '[1] A. Author. Sample article[J]. Journal, 2023, 1(2): 1-4.',
    ], 'missing-figure-table.pdf');

    const result = await paperLintService.runPaperLint({
      pdfBuffer,
      selectedRuleIds: ['figure_reference_target_check', 'table_reference_target_check'],
    });
    const figureRun = ruleRun(result, 'figure_reference_target_check');
    const tableRun = ruleRun(result, 'table_reference_target_check');

    expect(figureRun).toMatchObject({ execution_status: 'completed', outcome: 'issues_found' });
    expect(figureRun.findings).toHaveLength(1);
    expect(figureRun.findings[0].message).toContain('图 2');
    expect(tableRun).toMatchObject({ execution_status: 'completed', outcome: 'issues_found' });
    expect(tableRun.findings).toHaveLength(1);
    expect(tableRun.findings[0].message).toContain('表 4');
  });
});
