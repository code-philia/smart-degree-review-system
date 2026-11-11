import apiClient from '../src/api';
import { clearReportTranslations } from '../src/i18n/reportTranslations';
import { Blob as NodeBlob } from 'node:buffer';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { unzipSync, strFromU8 } from 'fflate';
import { buildExportReport, reportBlocks, reportText } from '../src/utils/reportExport/model';
import { localizeExportReport, collectExportTranslationTexts } from '../src/utils/reportExport/presentation';
import { createReportFile } from '../src/utils/reportExport/formats';
import { addTranslations, clearTranslations, setLocale, getLocale, translate } from '../src/i18n/locale.js';
import { fixture } from './fixtures/reportExport';
const source = '检测结果    提示\n格式规范';
function modelFixture() {
  const report = structuredClone(fixture);
  report.source_filename = '检测结果    提示.pdf';
  report.result.paper_title = source;
  const run = report.result.rule_runs[0];
  run.message = '需要核对任意动态说明。';
  run.findings[0].message = '发现“检测结果”需要核对 12 项。';
  run.findings[0].location!.text_excerpt = '参考证据：检测结果';
  run.findings[0].evidence = [{ id: 'e', quote: '参考证据：检测结果', url: 'https://example.com/原文' }];
  const numeric = structuredClone(run);
  numeric.rule_id = 'abstract_numeric_consistency_check';
  numeric.findings = [];
  numeric.params = {
    preconditions: ['abstract_numeric', 'contribution_mapping', 'experiment_subsection'].map((id) => ({
      id,
      passed: true,
      status: 'passed',
    })),
    contributions: [{ id: 'c1', text: source }],
    mappings: [{ declaration_id: 'd1', chapter_title: source, experiment_titles: ['检测结果', '提示    格式规范'] }],
    numeric_results: [
      {
        declaration_id: 'd1',
        declaration: { text: source, contribution_id: 'c1' },
        status: 'consistent',
        reason: '摘要数值与正文实验结果一致。',
        suggestion: '请核对任意新增建议。',
      },
    ],
  };
  report.result.rule_runs.push(numeric);
  return buildExportReport(report, [], null);
}
const translations = {
  '需要核对任意动态说明。': 'Review this arbitrary explanation.',
  '发现“检测结果”需要核对 12 项。': 'Review 12 items concerning “检测结果”.',
  已有本地建议: 'Existing local suggestion',
  检查依据: 'Check basis',
  '摘要数值与正文实验结果一致。': 'Abstract values agree with the experimental results.',
  '请核对任意新增建议。': 'Review the newly generated suggestion.',
  另一个位置: 'Other location',
};
beforeEach(() => vi.stubGlobal('Blob', NodeBlob));
afterEach(() => {
  setLocale('zh');
  clearReportTranslations();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it('localizes presentation fields, preserving source values, identifiers and numbers', () => {
  addTranslations(translations);
  setLocale('en');
  const model = modelFixture(),
    snapshot = JSON.stringify(model);
  const english = localizeExportReport(model),
    text = reportText(english);
  expect(text).toContain(translate('文档名称') + ': 检测结果    提示.pdf');
  expect(text).toContain('Thesis title: ' + source);
  expect(text).toContain('Review 12 items concerning “检测结果”.');
  expect(text).toContain('Research contribution: ' + source);
  expect(text).toContain('Research chapter: ' + source + '; Experimental subsection: 检测结果、提示    格式规范');
  expect(text).toContain('Claim 1: ' + source + ' · Consistent');
  const quotes = reportBlocks(english)
    .filter((b) => b.kind === 'quote')
    .map((b) => b.text);
  expect(quotes).toContain('参考证据：检测结果');
  expect(quotes).toContain(translate('参考证据') + ': 参考证据：检测结果 — https://example.com/原文');
  expect(JSON.stringify(model)).toBe(snapshot);
  expect(english.document).toEqual(model.document);
  expect(english.report_id).toBe(model.report_id);
  expect(english.findings[0].id).toBe(model.findings[0].id);
  expect(english.findings[0].locations[0].page).toBe(3);
  expect(Object.getOwnPropertyNames(english)).toEqual(Object.getOwnPropertyNames(model));
});
it('collects dynamic explanations without collecting source or evidence strings', () => {
  const required = collectExportTranslationTexts(modelFixture());
  expect(required).toContain('需要核对任意动态说明。');
  expect(required).toContain('请核对任意新增建议。');
  expect(required).not.toContain(source);
  expect(required).not.toContain('参考证据：检测结果');
});
it('retains Chinese model, blocks and filename without requiring English translations', async () => {
  setLocale('zh');
  const model = modelFixture(),
    snapshot = JSON.stringify(model);
  expect(localizeExportReport(model)).toBe(model);
  expect(reportText(model)).toContain('研究贡献：' + source);
  const file = await createReportFile(model, 'json');
  expect(file.filename).toBe('检测结果    提示_检测报告.json');
  const exported = JSON.parse(await file.blob.text());
  expect(exported.reports[0]).toEqual(JSON.parse(JSON.stringify(model)));
  expect(exported.reports).toHaveLength(1);
  expect(exported.reports[0].language).toBe('zh-CN');
  expect(JSON.stringify(model)).toBe(snapshot);
});
it('blocks incomplete English exports with a retry message instead of mixed dynamic prose', async () => {
  setLocale('en');
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
    data: { locale: 'en', status: 'partial', translations: {}, source_hash: 'test-hash', model: 'qwen' },
  });
  await expect(createReportFile(modelFixture(), 'text')).rejects.toThrow(/translat|retry/i);
  expect(post).toHaveBeenCalledWith(
    '/normative/paper-lint/reports/export-report/translations',
    { locale: 'en' },
    expect.any(Object),
  );
});
it('creates actual English text, Markdown, JSON and editable Word retaining evidence', async () => {
  addTranslations(translations);
  setLocale('en');
  const model = modelFixture();
  for (const format of ['text', 'markdown', 'json', 'docx'] as const) {
    const file = await createReportFile(model, format),
      bytes = new Uint8Array(await file.blob.arrayBuffer());
    const content =
      format === 'docx' ? strFromU8(unzipSync(bytes)['word/document.xml']) : new TextDecoder().decode(bytes);
    expect(content).toContain('Review 12 items concerning');
    expect(content).toContain('参考证据：检测结果');
    expect(file.filename).toContain('检测结果    提示');
    if (format === 'docx') expect(content).toContain(translate('论文规范性检测报告'));
  }
});

it('keeps explicitly original/source basis text even when it exactly collides with UI copy', () => {
  setLocale('en');
  const report = structuredClone(fixture);
  report.result.rule_runs[0].findings[0].basis_details = [{ id: 'source', kind: 'original_excerpt', text: '检测结果' }];
  const model = buildExportReport(report, [], null);
  expect(collectExportTranslationTexts(model)).not.toContain('检测结果');
  expect(localizeExportReport(model).findings[0].basis).toEqual(['检测结果']);
});
it('captures the export language and mapping snapshot before asynchronous Word generation', async () => {
  addTranslations(translations);
  setLocale('en');
  const file = await createReportFile(modelFixture(), 'docx', {
    onProgress: () => {
      setLocale('zh');
      clearTranslations();
    },
  });
  const xml = strFromU8(unzipSync(new Uint8Array(await file.blob.arrayBuffer()))['word/document.xml']);
  expect(xml).toContain('Review 12 items concerning');
  expect(xml).toContain('Thesis title:');
  expect(xml).not.toContain('论文题目：');
});

it('waits for missing report mappings and keeps its chosen language if the UI switches while waiting', async () => {
  const { ['发现“检测结果”需要核对 12 项。']: missing, ...present } = translations;
  addTranslations(present);
  setLocale('en');
  const post = vi.spyOn(apiClient, 'post').mockImplementation(async () => {
    setLocale('zh');
    return {
      data: {
        locale: 'en',
        status: 'ready',
        translations: { '发现“检测结果”需要核对 12 项。': missing },
        source_hash: 'report-revision',
        model: 'qwen',
      },
    };
  });
  const file = await createReportFile(modelFixture(), 'text');
  expect(await file.blob.text()).toContain('Review 12 items concerning “检测结果”.');
  expect(await file.blob.text()).toContain('Thesis title:');
  expect(getLocale()).toBe('zh');
  expect(post).toHaveBeenCalledTimes(1);
});

it('preserves original standard and project basis clauses from the compiler catalog', () => {
  setLocale('en');
  for (const kind of ['standard', 'project']) {
    const report = structuredClone(fixture);
    report.result.rule_runs[0].findings[0].basis_details = [{ id: 'catalog-clause', kind, text: '检测结果' }];
    const model = buildExportReport(report, [], null);
    expect(collectExportTranslationTexts(model)).not.toContain('检测结果');
    expect(localizeExportReport(model).findings[0].basis).toEqual(['检测结果']);
  }
});
it('localizes generated AI suggestion statuses without requesting machine-status translations', async () => {
  addTranslations(translations);
  setLocale('en');
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
    data: { locale: 'en', status: 'ready', translations: {}, source_hash: 'test', model: 'qwen' },
  });
  for (const status of ['上下文不足', '证据存在冲突']) {
    const model = modelFixture();
    model.findings[0].suggestions.push(`AI 建议状态：${status}`);
    const file = await createReportFile(model, 'text');
    expect(await file.blob.text()).toContain('AI suggestion status: ' + translate(status));
  }
  expect(post).not.toHaveBeenCalled();
});

it('uses singular and plural numerical claim counts while preserving the Chinese summary', () => {
  addTranslations(translations);
  setLocale('en');
  const one = modelFixture();
  expect(reportText(localizeExportReport(one))).toContain('1 claim verified;');
  expect(reportText(localizeExportReport(one))).not.toContain('1 claims verified;');
  const report = structuredClone(fixture);
  report.result.rule_runs = [
    {
      ...report.result.rule_runs[0],
      rule_id: 'abstract_numeric_consistency_check',
      findings: [],
      params: {
        preconditions: ['abstract_numeric', 'contribution_mapping', 'experiment_subsection'].map((id) => ({
          id,
          passed: true,
        })),
        numeric_results: [
          { declaration_id: 'd1', status: 'consistent' },
          { declaration_id: 'd2', status: 'consistent' },
        ],
      },
    },
  ];
  const two = buildExportReport(report, [], null);
  expect(reportText(localizeExportReport(two))).toContain('2 claims verified;');
  expect(reportText(two)).toContain('共核验 2 项论点；一致 2 项；');
  expect(reportText(one)).toContain('共核验 1 项论点；一致 1 项；');
});

it('localizes only the known generated combined-ruleset fallback and preserves real version metadata', () => {
  setLocale('en');
  const report = structuredClone(fixture);
  report.result.paper_title = '当前本地版本';
  report.result.ruleset = {
    id: 'smart-degree-combined-pdf-lint',
    name: '基础规则检测',
    version_number: 1,
    version_label: '当前本地版本',
  };
  const original = JSON.stringify(report);
  expect(localizeExportReport(buildExportReport(report, [], null)).ruleset).toBe('Current local version');
  expect(localizeExportReport(buildExportReport(report, [], null)).document.title).toBe('当前本地版本');
  expect(buildExportReport(report, [], null).ruleset).toBe('当前本地版本');
  expect(JSON.stringify(report)).toBe(original);
  report.result.ruleset.version_label = '当前本地版本 · 引用规则 中文发布-v7、compiler-abc';
  expect(localizeExportReport(buildExportReport(report, [], null)).ruleset).toBe(
    'Current local version · Reference checks 中文发布-v7、compiler-abc',
  );
  report.result.ruleset.id = 'user-authored-catalog';
  expect(localizeExportReport(buildExportReport(report, [], null)).ruleset).toBe(
    '当前本地版本 · 引用规则 中文发布-v7、compiler-abc',
  );
  report.result.ruleset.id = 'smart-degree-combined-pdf-lint';
  report.result.ruleset.version_label = '正式版本：当前本地版本';
  expect(localizeExportReport(buildExportReport(report, [], null)).ruleset).toBe('正式版本：当前本地版本');
});
