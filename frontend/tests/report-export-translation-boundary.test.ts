import { Blob as NodeBlob } from 'node:buffer';
import { createRequire } from 'node:module';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { buildExportReport } from '../src/utils/reportExport/model';
import { createReportFile } from '../src/utils/reportExport/formats';
import { collectExportTranslationTexts, localizeExportReport } from '../src/utils/reportExport/presentation';
import { addTranslations, setLocale, translate } from '../src/i18n/locale.js';
import { clearReportTranslations } from '../src/i18n/reportTranslations';
import { fixture } from './fixtures/reportExport';

const require = createRequire(import.meta.url);
const { createTranslationService } = require('../../backend/src/normative/reportTranslationService.js');
let cacheDir: string;
beforeEach(async () => {
  vi.stubGlobal('Blob', NodeBlob);
  cacheDir = await mkdtemp(join(tmpdir(), 'report-export-boundary-'));
});
afterEach(async () => {
  setLocale('zh');
  clearReportTranslations();
  vi.unstubAllGlobals();
  await rm(cacheDir, { recursive: true, force: true });
});

it.each([
  ['inconsistent', 'The claim contradicts evidence:'],
  ['inconclusive', 'The evidence is unclear:'],
])(
  'exports the actual backend sanitized %s numeric mapping without changing source evidence',
  async (status, expected) => {
    const report = structuredClone(fixture);
    report.id = 'numeric-owner-boundary-' + status;
    report.selected_rule_ids = ['abstract_numeric_consistency_check'];
    const originalExcerpt = '摘要原文 D1:A1 第12页保持不变。';
    const originalEvidence = '实验原文 D1:A1 第12页保持不变。';
    report.result.rule_runs = [
      {
        ...report.result.rule_runs[0],
        rule_id: 'abstract_numeric_consistency_check',
        findings: [],
        params: {
          preconditions: [{ id: 'abstract_numeric', passed: true }],
          contributions: [{ id: 'c1', text: '原始研究贡献' }],
          numeric_results: [
            {
              declaration_id: 'd1',
              status,
              declaration: { text: '原始数值论点', contribution_id: 'c1' },
              reason: 'D1:A1在第12页与摘要数值不一致。',
              suggestion: '请核对原始实验数据。',
              evidence: [{ candidate_id: 'D1:A1', page: 12, quote: originalEvidence }],
              abstract_anchors: [
                {
                  anchor_id: 'abstract',
                  location: { type: 'pdf_page', page_number: 3, text_excerpt: originalExcerpt },
                },
              ],
              evidence_anchors: [
                { anchor_id: 'D1:A1', location: { type: 'pdf_page', page_number: 12, text_excerpt: originalEvidence } },
              ],
            },
          ],
        },
      },
    ];
    const canonicalBefore = JSON.stringify(report);
    const ownerLookups: string[][] = [];
    // Only the external model transport is replaced. Extraction, ownership lookup,
    // protected tokens, answer validation, cache, mapping store and exporters are real.
    const translate = createTranslationService({
      cacheDir,
      loadReport: async (id: string, user: string) => {
        ownerLookups.push([id, user]);
        return id === report.id && user === 'fixture-owner' ? report : null;
      },
      loadRepairs: async () => [],
      maxBatches: 10,
      model: async (items: { id: string; text: string }[]) => ({
        items: items.map(({ id, text }) => {
          const markers = (text.match(/__P\d+__/g) || []).join(' ');
          const prefix = text.startsWith('论点与论据不一致：')
            ? 'The claim contradicts evidence:'
            : text.startsWith('论据不明确：')
              ? 'The evidence is unclear:'
              : 'Translated explanation:';
          return { id, text: prefix + ' ' + markers + ' verified against the abstract.' };
        }),
      }),
    });
    const response = await translate({ reportId: report.id, userId: 'fixture-owner', locale: 'en' });
    expect(response.status).toBe('ready');
    expect(ownerLookups).toEqual([[report.id, 'fixture-owner']]);
    expect(response.translations).not.toHaveProperty(originalExcerpt);
    expect(response.translations).not.toHaveProperty(originalEvidence);
    expect(response.translations).not.toHaveProperty('原始数值论点');
    const model = buildExportReport(report, [], null);
    expect(model.findings).toHaveLength(1);
    const derived = model.findings[0];
    expect(derived.message).not.toMatch(/D1:A1|第12页/);
    expect(response.translations[derived.message]).toContain(expected);
    addTranslations(response.translations);
    setLocale('en');
    const english = localizeExportReport(model);
    expect(english.findings[0].message).toBe(response.translations[derived.message]);
    expect(english.findings[0].message).not.toMatch(/D1:A1|第12页|[\u3400-\u9fff]/);
    expect(english.findings[0].locations.map((item) => item.page)).toEqual([3, 12]);
    expect(english.findings[0].locations.map((item) => item.text)).toEqual([originalExcerpt, originalEvidence]);
    for (const format of ['json', 'text'] as const) {
      const file = await createReportFile(model, format);
      const content = await file.blob.text();
      expect(content).toContain(expected);
      expect(content).toContain(originalExcerpt);
      expect(content).toContain(originalEvidence);
    }
    expect(JSON.stringify(report)).toBe(canonicalBefore);
  },
);

it.each(['检测结果', '提示'])(
  'preserves the literal typo correction %s despite approved UI dictionary collisions',
  async (correction) => {
    const report = structuredClone(fixture);
    report.id = 'typo-boundary-' + correction;
    report.selected_rule_ids = ['typo_detection_check'];
    const originalExcerpt = '需核对的原文词';
    const sourceDescription = '提示';
    report.result.rule_runs = [
      {
        ...report.result.rule_runs[0],
        rule_id: 'typo_detection_check',
        findings: [
          {
            finding_id: 'typo-literal',
            rule_id: 'typo_detection_check',
            message: '疑似错别字：' + originalExcerpt,
            suggestion: correction,
            location: { type: 'pdf_page', page_number: 3, text_excerpt: originalExcerpt },
            anchors: [
              {
                anchor_id: 'source',
                role: 'source_span',
                label: '相关位置',
                description: sourceDescription,
                location: { type: 'pdf_page', page_number: 4, text_excerpt: sourceDescription },
              },
            ],
          },
        ],
      },
    ];
    const canonicalBefore = JSON.stringify(report);
    const service = createTranslationService({
      cacheDir,
      loadReport: async (id: string, user: string) => (id === report.id && user === 'fixture-owner' ? report : null),
      loadRepairs: async () => [],
      maxBatches: 10,
      model: async (items: { id: string; text: string }[]) => ({
        items: items.map(({ id, text }) => ({
          id,
          text: 'English explanation ' + (text.match(/__P\d+__/g) || []).join(' ') + '.',
        })),
      }),
    });
    const response = await service({ reportId: report.id, userId: 'fixture-owner', locale: 'en' });
    expect(response.status).toBe('ready');
    expect(response.translations[correction]).toBe(correction);
    expect(response.translations[sourceDescription]).toBe(sourceDescription);
    addTranslations(response.translations);
    setLocale('en');
    expect(translate(correction)).not.toBe(correction); // Global UI copy still uses reviewed English.
    const model = buildExportReport(report, [], null),
      english = localizeExportReport(model);
    expect(english.findings[0].suggestions).toEqual([correction]);
    expect(collectExportTranslationTexts(model)).not.toContain(correction);
    expect(collectExportTranslationTexts(model)).not.toContain(sourceDescription);
    expect(english.findings[0].message).toContain(originalExcerpt);
    expect(english.findings[0].locations.map((item) => item.text)).toEqual([originalExcerpt, sourceDescription]);
    for (const format of ['json', 'text'] as const) {
      const file = await createReportFile(model, format),
        content = await file.blob.text();
      if (format === 'json')
        for (const report of JSON.parse(content).reports) expect(report.findings[0].suggestions).toEqual([correction]);
      else expect(content).toContain('Suggested action: ' + correction);
      expect(content).toContain(sourceDescription);
    }
    expect(JSON.stringify(report)).toBe(canonicalBefore);
  },
);
