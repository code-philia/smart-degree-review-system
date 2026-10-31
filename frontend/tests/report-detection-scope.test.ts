import { Blob as NodeBlob } from 'node:buffer';
import { strFromU8, unzipSync } from 'fflate';
import { afterEach, expect, it, vi } from 'vitest';
import type { PaperLintRule, PaperLintRunResponse } from '../src/api/paperLint';
import { createReportFile } from '../src/utils/reportExport/formats';
import { buildExportReport, reportBlocks, reportMarkdown, reportText } from '../src/utils/reportExport/model';
import { renderReportPages } from '../src/utils/reportExport/renderPages';
import { fixture } from './fixtures/reportExport';

const rule = (id: string, title: string, description: string): PaperLintRule => ({
  rule_id: id, title, description, default_severity: 'warning', default_enabled: true,
  execution_mode: 'deterministic', uses_external_model: false, available: true,
});
const catalog = [
  rule('sjtu_rule_15', '图表编号', '核对图表编号与正文引用是否对应。'),
  rule('sjtu_rule_17', '英文摘要', '检查英文摘要中的语言表达。'),
  rule('unselected', '未选择的规则', '这项规则没有在本次选择。'),
];
const selectedReport = {
  ...fixture,
  selected_rule_ids: ['sjtu_rule_17', 'sjtu_rule_15', 'sjtu_rule_17'],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('exports only the actual selected scope in selection order and removes duplicate IDs', () => {
  const model = buildExportReport(selectedReport, catalog, null);
  expect(model.scope).toEqual([
    { id: 'sjtu_rule_17', title: '英文摘要', description: '检查英文摘要中的语言表达。' },
    { id: 'sjtu_rule_15', title: '图表编号', description: '核对图表编号与正文引用是否对应。' },
  ]);
  expect(model.rules).toHaveLength(1);
  expect(model.summary).toEqual(fixture.result.summary);
});

it.each([{ name: 'empty', ids: [] }, { name: 'absent', ids: undefined }])('uses executed IDs for a legacy report whose selections are $name', ({ ids }) => {
  const report = { ...fixture, selected_rule_ids: ids } as PaperLintRunResponse;
  report.result = { ...fixture.result, rule_runs: [fixture.result.rule_runs[0], fixture.result.rule_runs[0]] };
  expect(buildExportReport(report, catalog, null).scope).toEqual([
    { id: 'sjtu_rule_15', title: '图表编号', description: '核对图表编号与正文引用是否对应。' },
  ]);
});

it('keeps a selected ID without a catalog entry or execution result and states the missing description honestly', () => {
  const report = { ...fixture, selected_rule_ids: ['archived-rule'] };
  expect(buildExportReport(report, catalog, null).scope).toEqual([
    { id: 'archived-rule', title: 'archived-rule', description: '规则说明暂不可用（目录中未提供）。' },
  ]);
});

it.each([
  { name: 'missing description', title: '图表编号', description: undefined,
    expected: { id: 'sjtu_rule_15', title: '图表编号', description: '规则说明暂不可用（目录中未提供）。' } },
  { name: 'missing title', title: undefined, description: '核对图表编号与正文引用是否对应。',
    expected: { id: 'sjtu_rule_15', title: 'sjtu_rule_15', description: '核对图表编号与正文引用是否对应。' } },
  { name: 'null title and description', title: null, description: null,
    expected: { id: 'sjtu_rule_15', title: 'sjtu_rule_15', description: '规则说明暂不可用（目录中未提供）。' } },
])('keeps scope available with a catalog entry containing $name', ({ title, description, expected }) => {
  const partialCatalog = [{ ...catalog[0], title, description }] as unknown as PaperLintRule[];
  expect(buildExportReport(fixture, partialCatalog, null).scope).toEqual([expected]);
});

it('uses concise catalog descriptions without broken Unicode or extra whitespace', () => {
  const description = ' 检查\n  ' + '论文🙂'.repeat(60);
  const model = buildExportReport(fixture, [rule('sjtu_rule_15', '图表编号', description)], null);
  expect(model.scope[0].description.startsWith('检查 论文🙂')).toBe(true);
  expect(Array.from(model.scope[0].description)).toHaveLength(121);
  expect(model.scope[0].description.endsWith('…')).toBe(true);
  expect(model.scope[0].description).not.toMatch(/[\r\n\uFFFD]/);
});

it('adds a scope section with the same titles and descriptions to shared blocks, Markdown and plain text', () => {
  const model = buildExportReport(selectedReport, catalog, null);
  const blocks = reportBlocks(model);
  const start = blocks.findIndex((block) => block.text === '本次检测范围');
  expect(start).toBeGreaterThan(0);
  const end = blocks.findIndex((block, index) => index > start && block.kind === 'heading');
  const scopeText = blocks.slice(start, end).map((block) => block.text).join('\n');
  expect(scopeText).toContain('已选择 2 项规则');
  expect(scopeText).toContain('英文摘要（sjtu_rule_17）：检查英文摘要中的语言表达。');
  expect(scopeText).toContain('图表编号（sjtu_rule_15）：核对图表编号与正文引用是否对应。');
  expect(scopeText).not.toMatch(/未选择的规则|通过|执行失败|无法判定/);
  expect(reportText(model)).toContain(scopeText.split('\n').at(-1));
  expect(reportMarkdown(model)).toContain('## 本次检测范围');
  expect(reportMarkdown(model)).toContain('检查英文摘要中的语言表达。');
});

it('includes scope in genuine Markdown, TXT, JSON and editable DOCX files', async () => {
  vi.stubGlobal('Blob', NodeBlob);
  const model = buildExportReport(selectedReport, catalog, null);
  for (const format of ['markdown', 'text', 'json', 'docx'] as const) {
    const file = await createReportFile(model, format);
    const content = format === 'docx'
      ? strFromU8(unzipSync(new Uint8Array(await file.blob.arrayBuffer()))['word/document.xml'])
      : await file.blob.text();
    if (format === 'json') expect(JSON.parse(content).scope).toEqual(model.scope);
    else expect(content).toContain('本次检测范围');
    expect(content).toContain('检查英文摘要中的语言表达。');
    expect(content).not.toContain('未选择的规则');
  }
});

it('draws the same scope in the shared page renderer used by PDF and image exports', async () => {
  const drawn: string[] = [];
  const context = {
    measureText: (text: string) => ({ width: Array.from(text).length * 10 }),
    fillText: (text: string) => drawn.push(text),
    fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D);
  let pages = 0;
  for await (const _page of renderReportPages(buildExportReport(selectedReport, catalog, null))) pages += 1;
  expect(pages).toBeGreaterThan(0);
  const text = drawn.join('\n');
  expect(text).toContain('本次检测范围');
  expect(text).toContain('英文摘要（sjtu_rule_17）：检查英文摘要中的语言表达。');
  expect(text).not.toContain('未选择的规则');
});

it('states that scope is unrecorded when both selection and execution records are absent', () => {
  const report = { ...fixture, selected_rule_ids: [], result: { ...fixture.result, rule_runs: [] } };
  const model = buildExportReport(report, catalog, null);
  expect(model.scope).toEqual([]);
  expect(reportText(model)).toContain('未记录检测规则，无法确认本次检测范围。');
});
