import { Blob as NodeBlob } from 'node:buffer';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { unzipSync, strFromU8 } from 'fflate';
import apiClient from '../src/api';
import { buildExportReport, reportBlocks, reportSignature, safeReportFilename } from '../src/utils/reportExport/model';
import { createReportFile } from '../src/utils/reportExport/formats';
import { collectExportTranslationTexts, localizeExportReport } from '../src/utils/reportExport/presentation';
import { addTranslations, setLocale } from '../src/i18n/locale.js';
import { clearReportTranslations } from '../src/i18n/reportTranslations';
import { fixture } from './fixtures/reportExport';

function ready(model = buildExportReport(fixture, [], null)) {
  addTranslations(
    Object.fromEntries(
      collectExportTranslationTexts(model).map((text, index) => [text, `English explanation ${index}.`]),
    ),
  );
  return model;
}
beforeEach(() => vi.stubGlobal('Blob', NodeBlob));
afterEach(() => {
  setLocale('zh');
  clearReportTranslations();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it.each(['zh', 'en'])('omits blank and engine fallback thesis titles only from printed %s metadata', async (locale) => {
  setLocale(locale);
  for (const title of ['', ' \t\n ', '上传论文', ' \t上传论文\n ']) {
    const model = ready();
    model.document.title = title;
    const before = JSON.stringify(model);
    const selected = locale === 'en' ? localizeExportReport(model, 'en') : model;
    expect(reportBlocks(selected).some((block) => /^(?:论文题目：|Thesis title: )/.test(block.text))).toBe(false);
    const file = await createReportFile(model, 'json');
    expect(JSON.parse(await file.blob.text()).reports[0].document.title).toBe(title);
    expect(JSON.stringify(model)).toBe(before);
  }
  for (const title of ['实际论文原始题名', 'Original Thesis Title', '上传论文（修订稿）']) {
    const model = ready();
    model.document.title = title;
    const before = JSON.stringify(model);
    const selected = locale === 'en' ? localizeExportReport(model, 'en') : model;
    expect(reportBlocks(selected)).toContainEqual(
      expect.objectContaining({ kind: 'meta', text: (locale === 'en' ? 'Thesis title: ' : '论文题目：') + title }),
    );
    expect(JSON.stringify(model)).toBe(before);
  }
});

it('keeps the uploaded filename recognizable and selects only the report suffix by export language', () => {
  expect(safeReportFilename('中文论文.pdf', 'en')).toBe('中文论文_Review_Report');
  expect(safeReportFilename('中文论文.pdf')).toBe('中文论文_检测报告');
});

it.each(['zh', 'en'])('exports only the complete %s edition selected when export starts', async (locale) => {
  const model = ready(),
    before = JSON.stringify(model);
  setLocale(locale);
  const json = JSON.parse(await (await createReportFile(model, 'json')).blob.text());
  expect(json.schema_version).toBe(1);
  expect(json.reports.map((report: any) => report.language)).toEqual([locale === 'en' ? 'en' : 'zh-CN']);
  const [selected] = json.reports;
  if (locale === 'en') expect(selected.findings[0].message).toMatch(/^English explanation/);
  else expect(selected.findings[0].message).toBe(model.findings[0].message);
  expect(selected.findings[0].locations).toEqual(
    model.findings[0].locations.map((location: any) => ({ ...location, label: expect.any(String) })),
  );
  expect(selected.findings[0].evidence).toEqual(model.findings[0].evidence);
  expect(selected.findings[0].id).toBe(model.findings[0].id);
  expect(selected.signature.institution).toBe(
    locale === 'en'
      ? 'Shanghai Jiao Tong University Graduate Degree Information System'
      : '上海交通大学研究生学位信息系统',
  );
  expect(JSON.stringify(model)).toBe(before);
  for (const format of ['text', 'markdown'] as const) {
    const content = await (await createReportFile(model, format)).blob.text();
    expect(content).toContain(locale === 'en' ? '1 Review summary' : '1 检测综述');
    expect(content).not.toContain(locale === 'en' ? '论文规范性检测报告' : 'Thesis compliance report');
    expect(content).toContain(format === 'markdown' ? '2\\.1' : '2.1');
    expect(content).toContain(format === 'markdown' ? '3\\.1' : '3.1');
    expect(content).toContain('原文证据');
  }
});

it('retains long scope descriptions, raw execution state, all warning results and serializable source provenance', () => {
  const report = structuredClone(fixture);
  report.result.rule_runs.push({
    ...report.result.rule_runs[0],
    rule_id: 'unavailable-check',
    execution_status: 'unsupported',
    outcome: 'inconclusive',
    findings: [],
    message: '未完成核验',
  });
  report.selected_rule_ids!.push('unavailable-check');
  report.result.rule_runs[0].findings[0].basis_details = [{ id: 'source', kind: 'original_excerpt', text: '提示' }];
  const description = '规则说明必须完整保留。'.repeat(40);
  const model = buildExportReport(report, [{ rule_id: 'sjtu_rule_15', title: '完整规则', description } as any], null);
  expect(model.scope[0].description).toBe(description);
  expect(model.rules[1]).toMatchObject({ execution_status: 'unsupported', outcome: 'inconclusive' });
  expect(model.findings.some((finding) => finding.severity === '规则未实现警告')).toBe(true);
  expect(JSON.parse(JSON.stringify(model)).findings[0].source_basis_indices).toEqual([0]);
  const blocks = reportBlocks(model);
  expect(blocks.find((block) => block.kind === 'subheading')?.text).toContain('(警告)');
  expect(blocks.filter((block) => block.kind === 'heading')).toHaveLength(3);
});

it('uses the same displayed numeric findings and execution warnings for every report and rule count', () => {
  const report = structuredClone(fixture);
  report.selected_rule_ids = ['abstract_numeric_consistency_check'];
  report.result.rule_runs = [
    {
      ...report.result.rule_runs[0],
      rule_id: 'abstract_numeric_consistency_check',
      findings: [],
      params: {
        preconditions: [{ id: 'abstract_numeric', passed: true }],
        numeric_results: [
          { declaration_id: 'one', status: 'inconsistent', reason: '数值不一致' },
          { declaration_id: 'two', status: 'inconclusive', reason: '证据不完整' },
        ],
      },
    },
  ];
  const model = buildExportReport(report, [], null);
  expect(model.findings).toHaveLength(2);
  expect(model.summary.finding_count).toBe(model.findings.length);
  expect(model.rules[0].finding_count).toBe(model.findings.length);
  expect(model.summary.warning_finding_count).toBe(
    model.findings.filter((finding) => finding.severity === '警告').length,
  );
  expect(model.summary.info_finding_count).toBe(model.findings.filter((finding) => finding.severity === '提示').length);
  report.result.rule_runs[0].params = {
    preconditions: [{ id: 'abstract_numeric', passed: false, reason: '缺少数值论点' }],
  };
  const unfinished = buildExportReport(report, [], null);
  expect(unfinished.summary.finding_count).toBe(unfinished.findings.length);
  expect(unfinished.summary.execution_warning_count).toBe(
    unfinished.findings.filter((finding) => finding.severity === '规则未实现警告').length,
  );
  expect(unfinished.rules[0].finding_count).toBe(unfinished.findings.length);
});

it('fails closed for incomplete English explanations from the English UI', async () => {
  setLocale('en');
  vi.spyOn(apiClient, 'post').mockResolvedValue({
    data: { locale: 'en', status: 'partial', translations: {}, source_hash: 'test', model: 'qwen' },
  });
  await expect(createReportFile(buildExportReport(fixture, [], null), 'text')).rejects.toThrow(
    /translation.*ready|retry/i,
  );
});

it.each(['text', 'markdown', 'json', 'docx'] as const)(
  'exports Chinese %s without English translation and retains the captured locale',
  async (format) => {
    setLocale('zh');
    const post = vi.spyOn(apiClient, 'post');
    const file = await createReportFile(buildExportReport(fixture, [], null), format, {
      onProgress: () => setLocale('en'),
    });
    const content =
      format === 'docx'
        ? strFromU8(unzipSync(new Uint8Array(await file.blob.arrayBuffer()))['word/document.xml'])
        : await file.blob.text();
    expect(content).toContain('上海交通大学研究生学位信息系统');
    expect(content).not.toContain('Thesis compliance report');
    expect(post).not.toHaveBeenCalled();
  },
);

it('uses the locale captured by the export action before asynchronous saved-data reads', async () => {
  const model = ready();
  setLocale('zh');
  const file = await createReportFile(model, 'json', { locale: 'en' });
  expect(JSON.parse(await file.blob.text()).reports.map((report: any) => report.language)).toEqual(['en']);
  expect(file.filename).toContain('_Review_Report');
});

it.each(['pdf', 'image'] as const)(
  'downloads the authenticated server LaTeX %s artifact with one selected model and cancellation',
  async (format) => {
    const model = ready(),
      controller = new AbortController();
    const artifact = new NodeBlob(['server artifact'], {
      type: format === 'pdf' ? 'application/pdf' : 'application/zip',
    });
    const post = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValue({ data: artifact, headers: { 'content-type': artifact.type } });
    const file = await createReportFile(model, format, { signal: controller.signal });
    expect(post).toHaveBeenCalledWith(
      '/normative/paper-lint/reports/export-report/export',
      {
        format,
        model: expect.objectContaining({
          schema_version: 1,
          reports: [expect.objectContaining({ language: 'zh-CN' })],
        }),
      },
      expect.objectContaining({ responseType: 'blob', signal: controller.signal, timeout: 300000 }),
    );
    expect(file.blob).toBe(artifact);
    expect(file.filename.endsWith(format === 'pdf' ? '.pdf' : '.zip')).toBe(true);
  },
);

it.each([400, 413, 429, 503, 504])(
  'shows a complete English export error for HTTP %s including JSON blob responses',
  async (status) => {
    const model = ready();
    setLocale('en');
    vi.spyOn(apiClient, 'post').mockRejectedValue({
      response: {
        status,
        data: new NodeBlob([JSON.stringify({ message: '报告导出暂不可用，请稍后重试。' })], {
          type: 'application/json',
        }),
      },
    });
    await expect(createReportFile(model, 'pdf')).rejects.toThrow(/export|report/i);
    try {
      await createReportFile(model, 'image');
    } catch (error) {
      expect(String(error)).not.toMatch(/[\u3400-\u9fff]/);
    }
  },
);

it.each(['pdf', 'image'] as const)(
  'requests one English server %s edition with the captured filename suffix',
  async (format) => {
    setLocale('en');
    const model = ready();
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: new NodeBlob(['artifact'], { type: format === 'pdf' ? 'application/pdf' : 'application/zip' }),
      headers: {},
    });
    const file = await createReportFile(model, format, { onProgress: () => setLocale('zh') });
    const payload = post.mock.calls[0][1] as any;
    expect(payload.model.reports).toHaveLength(1);
    expect(payload.model.reports[0].language).toBe('en');
    expect(file.filename).toContain('_Review_Report');
    expect(file.filename).not.toContain('_检测报告');
  },
);

it.each(['zh', 'en'])(
  'creates native %s Word paragraphs with stable article typography and one report title',
  async (locale) => {
    setLocale(locale);
    const model = ready();
    const file = await createReportFile(model, 'docx');
    const parts = unzipSync(new Uint8Array(await file.blob.arrayBuffer()));
    const xml = strFromU8(parts['word/document.xml']);
    const properties = strFromU8(parts['docProps/core.xml']);
    expect(properties).toContain(locale === 'en' ? 'Thesis compliance report' : '论文规范性检测报告');
    expect(properties).not.toContain(locale === 'en' ? '论文规范性检测报告' : 'Thesis compliance report');
    expect(xml).toContain(
      locale === 'en'
        ? 'Shanghai Jiao Tong University Graduate Degree Information System'
        : '上海交通大学研究生学位信息系统',
    );
    expect(xml).not.toContain(locale === 'en' ? '论文规范性检测报告' : 'Thesis compliance report');
    expect(xml).toContain('w:val="Title"');
    expect(xml).toContain('w:val="Heading1"');
    expect(xml).toContain('w:val="Heading2"');
    expect(xml).toContain('w:line="400"');
    expect(xml).toContain('w:lineRule="exact"');
    expect(xml).toContain('w:firstLine="480"');
    expect(xml).toContain('w:val="both"');
    expect(xml).toContain('<w:sz w:val="44"');
    expect(xml).toContain('<w:left w:val="single"');
    expect(xml).toContain('w:before="520"');
    expect(xml).not.toContain('<w:tbl>');
    const document = new DOMParser().parseFromString(xml, 'application/xml');
    expect(
      [...document.getElementsByTagName('w:pStyle')].filter((style) => style.getAttribute('w:val') === 'Title'),
    ).toHaveLength(1);
    expect(
      [...document.getElementsByTagName('w:pageBreakBefore')].filter((node) => node.getAttribute('w:val') !== 'false'),
    ).toHaveLength(0);
    const finding = [...document.getElementsByTagName('w:p')].find((paragraph) =>
      paragraph.textContent?.startsWith('2.1 '),
    )!;
    const status = [...finding.getElementsByTagName('w:r')].find(
      (run) => run.textContent === (locale === 'en' ? ' (Warnings)' : ' (警告)'),
    );
    expect(status?.getElementsByTagName('w:b')[0]?.getAttribute('w:val')).toBe('false');
  },
);

it('preserves original or localized source location labels together with the PDF page', () => {
  const model = buildExportReport(fixture, [], null);
  model.findings[0].locations[1].label = '实验论据位置';
  addTranslations({ 实验论据位置: 'Experimental evidence location' });
  expect(reportBlocks(model).find((block) => block.text === '第二处证据')?.sourceLabel).toBe(
    '实验论据位置 · PDF 第 5 页',
  );
  expect(
    reportBlocks(localizeExportReport(model, 'en')).find((block) => block.text === '第二处证据')?.sourceLabel,
  ).toBe('Experimental evidence location · PDF p. 5');
});

it('keeps original basis passages as distinct quotations and marks only explicit unique typo spans', () => {
  const report = structuredClone(fixture);
  const run = report.result.rule_runs[0];
  run.rule_id = 'typo_detection_check';
  run.findings[0].message = '疑似错别字：检側';
  run.findings[0].location!.text_excerpt = '原文检側结果';
  run.findings[0].basis_details = [{ id: 'standard', kind: 'standard', text: '标准原文必须保持。' }];
  const model = buildExportReport(report, [], null);
  expect(model.findings[0].locations[0]).toMatchObject({ text: '原文检側结果', marks: [{ start: 2, end: 4 }] });
  expect(reportBlocks(model).some((block) => block.kind === 'quote' && block.text === '标准原文必须保持。')).toBe(true);
  expect(report.result.rule_runs[0].findings[0].location!.text_excerpt).toBe('原文检側结果');
  expect(model.findings[0].source_basis_indices).toEqual([0]);
});

it('flows extracted source lines in left-aligned Word quotes while keeping body prose justified', async () => {
  setLocale('zh');
  const model = buildExportReport(fixture, [], null);
  model.findings[0].locations[0].text = '第一行很短。\n第二行同样短。';
  const before = JSON.stringify(model);
  const file = await createReportFile(model, 'docx');
  const parts = unzipSync(new Uint8Array(await file.blob.arrayBuffer()));
  const settings = strFromU8(parts['word/settings.xml']);
  expect(settings).toContain('<w:doNotExpandShiftReturn/>');
  const document = new DOMParser().parseFromString(strFromU8(parts['word/document.xml']), 'application/xml');
  const quote = [...document.getElementsByTagName('w:p')].find((paragraph) =>
    paragraph.textContent?.includes('第一行很短。'),
  )!;
  expect(quote.textContent).toContain('第一行很短。第二行同样短。');
  expect(quote.getElementsByTagName('w:br')).toHaveLength(0);
  expect(quote.getElementsByTagName('w:jc')[0].getAttribute('w:val')).toBe('left');
  const body = [...document.getElementsByTagName('w:p')].find((paragraph) =>
    paragraph.textContent?.includes('问题中文'),
  )!;
  expect(body.getElementsByTagName('w:jc')[0].getAttribute('w:val')).toBe('both');
  expect(body.getElementsByTagName('w:ind')[0].getAttribute('w:firstLine')).toBe('480');
  expect(quote.getElementsByTagName('w:spacing')[0].getAttribute('w:line')).toBe('400');
  expect(JSON.stringify(model)).toBe(before);
});

it('strips illegal C0 controls only at printed output boundaries after slicing source highlights', async () => {
  setLocale('zh');
  const model = buildExportReport(fixture, [], null);
  const text = '原文\u0000\u0001错字\u0008\u000b\u000c\u000e\u001f末尾\t下一行\n结尾';
  const start = text.indexOf('错字');
  model.findings[0].locations[0] = { label: '原文定位', page: 3, text, marks: [{ start, end: start + 2 }] };
  const before = JSON.stringify(model);
  for (const format of ['text', 'markdown', 'docx', 'json'] as const) {
    const file = await createReportFile(model, format);
    if (format === 'json') {
      expect(JSON.parse(await file.blob.text()).reports[0].findings[0].locations[0].text).toBe(text);
      continue;
    }
    const content =
      format === 'docx'
        ? strFromU8(unzipSync(new Uint8Array(await file.blob.arrayBuffer()))['word/document.xml'])
        : await file.blob.text();
    expect(content).not.toMatch(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/);
    if (format === 'docx') {
      const doc = new DOMParser().parseFromString(content, 'application/xml');
      expect(doc.getElementsByTagName('parsererror')).toHaveLength(0);
      const marked = [...doc.getElementsByTagName('w:r')].filter((run) => run.getElementsByTagName('w:shd').length);
      expect(marked.map((run) => run.textContent).join('')).toBe('错字');
      expect(doc.documentElement.textContent).toContain('原文错字末尾');
    } else expect(content).toContain('原文错字末尾\t下一行');
  }
  expect(JSON.stringify(model)).toBe(before);
});

it('keeps the final scope description with its count without chaining the next scope entry', async () => {
  setLocale('en');
  const model = ready();
  const file = await createReportFile(model, 'docx');
  const content = strFromU8(unzipSync(new Uint8Array(await file.blob.arrayBuffer()))['word/document.xml']);
  const doc = new DOMParser().parseFromString(content, 'application/xml');
  const paragraphs = [...doc.getElementsByTagName('w:p')];
  const countIndex = paragraphs.findIndex((p) => p.textContent === 'This check records 1 result.');
  expect(countIndex).toBeGreaterThan(0);
  const previous = paragraphs[countIndex - 1].getElementsByTagName('w:keepNext')[0];
  expect(previous?.getAttribute('w:val')).not.toBe('false');
  expect(previous).toBeTruthy();
  expect(paragraphs[countIndex].getElementsByTagName('w:keepNext')[0]?.getAttribute('w:val')).toBe('false');
  expect(paragraphs[countIndex - 1].getElementsByTagName('w:spacing')[0].getAttribute('w:line')).toBe('400');
});

it('reflows Word source quotes and typo snippets without altering raw models or highlight targets', async () => {
  setLocale('zh');
  const model = buildExportReport(fixture, [], null);
  const text = '第一段原文\n错字定位。\n\n（1）列表项目\n正文续行。';
  const start = text.indexOf('错字'),
    end = start + 2;
  model.findings[0].locations[0] = { label: '原文定位', page: 3, text, marks: [{ start, end }] };
  model.findings[0].message = '疑似错别字：一个CVE\n漏洞';
  model.findings[0].suggestions = ['原始\n替换文本'];
  model.findings[0].source_suggestion_indices = [0];
  const before = JSON.stringify(model);
  const file = await createReportFile(model, 'docx');
  const parts = unzipSync(new Uint8Array(await file.blob.arrayBuffer()));
  const doc = new DOMParser().parseFromString(strFromU8(parts['word/document.xml']), 'application/xml');
  const quote = [...doc.getElementsByTagName('w:p')].find((p) => p.textContent?.includes('第一段原文'))!;
  expect(quote.textContent).toContain('第一段原文错字定位。（1）列表项目正文续行。');
  expect(quote.getElementsByTagName('w:br')).toHaveLength(2);
  const marked = [...quote.getElementsByTagName('w:r')].filter((run) => run.getElementsByTagName('w:shd').length);
  expect(marked.map((run) => run.textContent).join('')).toBe('错字');
  const message = [...doc.getElementsByTagName('w:p')].find((p) => p.textContent?.includes('疑似错别字：一个CVE'))!;
  expect(message.getElementsByTagName('w:br')).toHaveLength(0);
  expect(message.textContent).toBe('疑似错别字：一个CVE漏洞');
  const advice = [...doc.getElementsByTagName('w:p')].find((p) => p.textContent?.includes('修改建议：原始'))!;
  expect(advice.getElementsByTagName('w:br')).toHaveLength(0);
  expect(advice.textContent).toBe('修改建议：原始替换文本');
  expect(JSON.stringify(model)).toBe(before);
});

it.each(['zh', 'en'])('keeps the official user-facing domain in the %s report signature on development hosts', (locale) => {
  vi.stubGlobal('window', { location: { origin: 'http://121.36.247.138:3000' } });
  expect(reportSignature(locale === 'en').website).toBe('https://thesis-review.sjtu.edu.cn');
  const model = ready();
  model.signature!.website = 'http://121.36.247.138:3000';
  const selected = locale === 'en' ? localizeExportReport(model, 'en') : model;
  expect(reportBlocks(selected).find((block) => block.role === 'website')?.text).toBe('https://thesis-review.sjtu.edu.cn');
});
