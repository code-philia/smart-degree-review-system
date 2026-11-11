import { markFindingSources, markRulesetPresentation, reportLocale, reportTranslator } from './presentation';
import type {
  PaperLintDocumentMetrics,
  PaperLintRule,
  PaperLintRunResponse,
  PaperLintSummary,
} from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import {
  documentCheckId,
  documentCheckTitle,
  isDocumentBlocked,
  compilerPublicationLabel,
  compilerPublicationSummary,
  flattenPaperLintFindings,
  paperLintPresentation,
  numericExecutionWarnings,
  genericExecutionWarnings,
  referenceResourcesUnavailable,
  comparePaperLintRuleIds,
  type PaperLintFindingItem,
} from '../../components/paperLint/model';
import { formatChinaDateTime } from '../dateTime';
import { numericReportBlocks } from './numericDetails';

export const EXPORT_NOTICE = '检测结果仅供参考，请结合论文原文和学校要求人工复核。';
export type DetectionScopeItem = { id: string; title: string; description: string };

export function buildDetectionScope(report: PaperLintRunResponse, rules: PaperLintRule[]): DetectionScopeItem[] {
  if (isDocumentBlocked(report.result.rule_runs)) return [];
  const selectedIds = report.selected_rule_ids?.length
    ? report.selected_rule_ids
    : report.result.rule_runs.map((run) => run.rule_id);
  const automaticIds = report.result.rule_runs
    .filter((run) => run.params?.automatic_core_check === true)
    .map((run) => run.rule_id);
  const ids = [...selectedIds, ...automaticIds];
  const catalog = new Map(rules.map((rule) => [rule.rule_id, rule]));
  return [...new Set(ids)].map((id) => {
    const rule = catalog.get(id);
    const description = automaticIds.includes(id)
      ? '系统自动执行核心章节结构检查，不受前端勾选影响。'
      : rule?.description?.trim().replace(/\s+/g, ' ');
    return {
      id,
      title: rule?.title?.trim() || (id === 'required_section_completeness_check' ? '核心章节完整性' : id),
      description: description || '规则说明暂不可用（目录中未提供）。',
    };
  });
}

export type ExportFinding = {
  number: number;
  id: string;
  rule_id: string;
  rule_title: string;
  severity: string;
  message: string;
  locations: { label: string; page: number; text: string; marks?: { start: number; end: number }[] }[];
  suggestions: string[];
  evidence: string[];
  basis: string[];
  source_basis_indices?: number[];
  source_suggestion_indices?: number[];
};
export type ExportReport = {
  schema_version: 1;
  language?: 'zh-CN' | 'en';
  signature?: { system: string; institution: string; website: string };
  report_id: string;
  document: { filename: string; title: string; page_count: number | null; word_count: number | null };
  detection_type: string;
  created_at: string;
  ruleset: string;
  conclusion: string;
  summary: PaperLintSummary;
  scope: DetectionScopeItem[];
  rules: {
    id: string;
    title: string;
    status: string;
    execution_status?: string;
    outcome?: string;
    message: string;
    finding_count: number;
    details: ReportBlock[];
  }[];
  findings: ExportFinding[];
  notice: string;
};
export type ReportBlock = {
  kind: 'title' | 'heading' | 'subheading' | 'meta' | 'text' | 'quote' | 'notice' | 'label';
  text: string;
  role?: 'document' | 'metadata' | 'signature' | 'signature_school' | 'website' | 'advice' | 'scope';
  status?: string;
  marks?: { start: number; end: number }[];
  sourceLabel?: string;
};
export type ExportReportBundle = { schema_version: 1; reports: [ExportReport] };

export function reportSignature(english = false) {
  return {
    system: english ? 'Smart Degree · AI Review Assistant' : '智慧学位 AI 评阅辅助系统',
    institution: english
      ? 'Shanghai Jiao Tong University Graduate Degree Information System'
      : '上海交通大学研究生学位信息系统',
    website: 'https://thesis-review.sjtu.edu.cn',
  };
}

export function buildExportReport(
  report: PaperLintRunResponse,
  rules: PaperLintRule[],
  metrics: PaperLintDocumentMetrics | null,
  repairs: Record<string, RepairSuggestion | undefined> = {},
): ExportReport {
  const result = paperLintPresentation(report.result),
    summary = result.summary;
  const title = (id: string) =>
    id === documentCheckId ? documentCheckTitle : rules.find((r) => r.rule_id === id)?.title || id;
  const inconclusive =
    summary.unsupported_rule_count > 0 ||
    result.rule_runs.some(
      (r) =>
        r.outcome === 'inconclusive' &&
        !(r.rule_id === 'sjtu_rule_32' && r.execution_status === 'completed' && !referenceResourcesUnavailable(r)) &&
        compilerPublicationLabel(r) !== '未触发告警',
    );
  const conclusion = isDocumentBlocked(result.rule_runs)
    ? 'Paper Model 编译失败。所有论文规则均未检测，请查看严重级别的具体原因。'
    : summary.finding_count > (summary.execution_warning_count ?? 0)
      ? `发现 ${summary.finding_count} 项问题，请逐项核对。`
      : summary.error_rule_count
        ? '部分规则执行失败，请核对未完成的检测项。'
        : inconclusive
          ? '部分规则无法判定，请人工核对。'
          : compilerPublicationSummary(result) || '规则检查通过，未发现问题。';
  const severity = { error: '严重', warning: '警告', info: '提示' };
  const warningItems: (PaperLintFindingItem & { executionWarning: boolean })[] = result.rule_runs.flatMap((run) =>
    (run.rule_id === 'abstract_numeric_consistency_check'
      ? numericExecutionWarnings(run)
      : genericExecutionWarnings([run])
    ).flatMap((warning) =>
      warning.feedbackTarget
        ? [
            {
              ...warning.feedbackTarget,
              finding: {
                ...warning.feedbackTarget.finding,
                message: warning.reason,
                suggestion: warning.suggestion,
                // Examples are quoted source illustrations; retain them verbatim.
                evidence: warning.example ? [{ id: 'execution-example', quote: warning.example }] : [],
                basis_details: [warning.explanation, warning.note]
                  .filter(Boolean)
                  .map((text, index) => ({ id: `execution-basis-${index}`, text })),
              },
              executionWarning: true,
            },
          ]
        : [],
    ),
  );
  const findingItems = [
    ...flattenPaperLintFindings(result).map((item) => ({ ...item, executionWarning: false })),
    ...warningItems,
  ];
  const order = (item: (typeof findingItems)[number]) =>
    item.executionWarning ? 2 : ({ error: 0, warning: 1, info: 3 }[item.ruleRun.severity] ?? 3);
  findingItems.sort(
    (a, b) =>
      order(a) - order(b) ||
      comparePaperLintRuleIds(a.ruleRun.rule_id, b.ruleRun.rule_id) ||
      (a.finding.location?.page_number ?? Number.MAX_SAFE_INTEGER) -
        (b.finding.location?.page_number ?? Number.MAX_SAFE_INTEGER) ||
      a.index - b.index,
  );
  return markRulesetPresentation(
    {
      schema_version: 1,
      language: 'zh-CN',
      signature: reportSignature(),
      report_id: report.id,
      document: {
        filename: report.source_filename,
        title: result.paper_title,
        page_count: metrics?.page_count ?? null,
        word_count: metrics?.text_available ? (metrics.word_count ?? null) : null,
      },
      detection_type: '规范性检测',
      created_at: report.created_at,
      ruleset: result.ruleset.version_label || result.ruleset.name,
      conclusion,
      summary,
      scope: buildDetectionScope(report, rules),
      rules: result.rule_runs.map((run) => ({
        id: run.rule_id,
        title: title(run.rule_id),
        execution_status: run.execution_status,
        outcome: run.outcome,
        status:
          compilerPublicationLabel(run) ||
          (run.execution_status === 'error'
            ? '执行失败'
            : run.execution_status === 'unsupported'
              ? '未能检测'
              : { passed: '通过', issues_found: '发现问题', inconclusive: '无法判定', not_applicable: '不适用' }[
                  run.outcome
                ]),
        message: run.message || '',
        finding_count: findingItems.filter((item) => item.ruleRun.rule_id === run.rule_id).length,
        details: numericReportBlocks(run),
      })),
      findings: findingItems.map(({ key, finding, ruleRun, executionWarning }, index) => {
        const locations: ExportFinding['locations'] = [];
        const add = (location: typeof finding.location, label: string) => {
          if (!location) return;
          const pages =
            location.type === 'pdf_bbox'
              ? [location.page_number, ...location.rects.map((r) => r.page_number)]
              : [location.page_number];
          for (const page of [...new Set(pages)])
            if (
              Number.isInteger(page) &&
              page > 0 &&
              !locations.some((x) => x.page === page && x.text === (location.text_excerpt || ''))
            ) {
              const text = location.text_excerpt || '';
              const typo =
                ruleRun.rule_id === 'typo_detection_check'
                  ? /^(?:疑似错别字|疑似错字)[：:]\s*(.+)$/.exec(finding.message)?.[1]?.trim()
                  : undefined;
              const start = typo ? text.indexOf(typo) : -1;
              // Only an explicit, unique source span can receive a visual mark.
              // Avoid ambiguous offsets for supplementary Unicode characters.
              const marks =
                typo && start >= 0 && text.indexOf(typo, start + typo.length) < 0 && !/[\uD800-\uDFFF]/.test(text)
                  ? [{ start, end: start + typo.length }]
                  : undefined;
              locations.push({ label, page, text, ...(marks ? { marks } : {}) });
            }
        };
        add(finding.location, '原文定位');
        finding.anchors?.forEach((anchor) => add(anchor.location, anchor.label || anchor.role || '相关位置'));
        const repair = repairs[key],
          suggestions = finding.suggestion ? [finding.suggestion] : [];
        if (repair && !finding.prompt_only) {
          if (repair.status === 'suggested') suggestions.push(...repair.actions.map((a) => a.instruction));
          else
            suggestions.push(
              `AI 建议状态：${repair.status === 'insufficient_context' ? '上下文不足' : '证据存在冲突'}`,
              ...(repair.missing_context || []),
            );
          if (repair.rationale) suggestions.push(repair.rationale);
        }
        return markFindingSources(
          {
            number: index + 1,
            id: finding.finding_id,
            rule_id: ruleRun.rule_id,
            rule_title: title(ruleRun.rule_id),
            severity: executionWarning ? '规则未实现警告' : severity[ruleRun.severity] || ruleRun.severity,
            message: finding.message,
            locations,
            suggestions: [...new Set(suggestions)],
            evidence: (finding.evidence || []).map((e) => [e.quote, e.url].filter(Boolean).join(' — ')).filter(Boolean),
            basis: (finding.basis_details || []).map((b) => b.text || '').filter(Boolean),
          },
          (finding.basis_details || [])
            .filter((b) => Boolean(b.text))
            .flatMap((b, index) =>
              /source|excerpt|quote|original|standard|project/i.test(b.kind || '') ? [index] : [],
            ),
          // The typo detector's original suggestion is replacement source text;
          // later repair actions remain presentation instructions.
          ruleRun.rule_id === 'typo_detection_check' && finding.suggestion ? [0] : [],
        );
      }),
      notice: EXPORT_NOTICE,
    },
    result.ruleset,
  );
}

export const stripExportControls = (text: string) => text.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '');

export const reportText = (model: ExportReport) =>
  stripExportControls(
    reportBlocks(model)
      .map((b) => (b.sourceLabel ? b.sourceLabel + '  ' + b.text : b.text))
      .join('\n\n') + '\n',
  );
const mdEscape = (text: string) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/[\\`*{}\[\]()#+.!_|-]/g, '\\$&');
export function reportMarkdown(model: ExportReport) {
  return stripExportControls(
    reportBlocks(model)
      .map(({ kind, text, sourceLabel }) => {
        const value = mdEscape(sourceLabel ? sourceLabel + '  ' + text : text);
        if (kind === 'title') return '# ' + value;
        if (kind === 'heading') return '## ' + value;
        if (kind === 'subheading') return '### ' + value;
        if (kind === 'label') return '**' + value + '**';
        if (kind === 'quote' || kind === 'notice')
          return value
            .split('\n')
            .map((line) => '> ' + line)
            .join('\n');
        return value.replace(/\n/g, '  \n');
      })
      .join('\n\n') + '\n',
  );
}
export function safeReportFilename(filename: string, locale = 'zh') {
  const clean = Array.from(
    filename
      .replace(/\.[^.]+$/, '')
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
      .trim(),
  )
    .slice(0, 100)
    .join('')
    .replace(/[. ]+$/, '');
  return (clean || (locale === 'en' ? 'Thesis' : '论文')) + (locale === 'en' ? '_Review_Report' : '_检测报告');
}

// Labels and source values remain separate: evidence is never translated or parsed.
export function reportBlocks(model: ExportReport): ReportBlock[] {
  const en = reportLocale(model) === 'en';
  const t = reportTranslator(model) ?? ((value: string) => value);
  const L = (zh: string, english: string) => (en ? english : zh);
  const join = (values: string[]) => values.filter(Boolean).join(en ? ' ' : '');
  const s = model.summary;
  const titleMetadata: ReportBlock[] =
    model.document.title?.trim() && model.document.title.trim() !== '上传论文'
      ? [{ kind: 'meta', role: 'metadata', text: L('论文题目：', 'Thesis title: ') + model.document.title }]
      : [];
  const blocks: ReportBlock[] = [
    { kind: 'title', text: L('论文规范性检测报告', 'Thesis compliance report') },
    { kind: 'meta', role: 'document', text: L('检测文件：', 'Document: ') + model.document.filename },
    ...titleMetadata,
    {
      kind: 'meta',
      role: 'metadata',
      text:
        L('报告生成时间：', 'Report generated: ') +
        formatChinaDateTime(model.created_at, { includeSeconds: true }) +
        ' (UTC+08:00)' +
        L(
          ` · ${model.document.page_count ?? '未统计'} 页，${model.document.word_count ?? '未统计'} 字`,
          ` · ${model.document.page_count ?? 'Not counted'} pages; ${model.document.word_count ?? 'Not counted'} characters`,
        ),
    },
    { kind: 'heading', text: L('1 检测综述', '1 Review summary') },
    {
      kind: 'text',
      text: L(
        `本次记录 ${s.finding_count} 项检测结果：严重 ${s.error_finding_count}、警告 ${s.warning_finding_count}、规则未实现警告 ${s.execution_warning_count ?? 0}、提示 ${s.info_finding_count}。`,
        `This review records ${s.finding_count} ${s.finding_count === 1 ? 'result' : 'results'}: Critical: ${s.error_finding_count}; Warnings: ${s.warning_finding_count}; Unverified: ${s.execution_warning_count ?? 0}; Info: ${s.info_finding_count}.`,
      ),
    },
    { kind: 'text', text: model.conclusion },
    {
      kind: 'text',
      text: L(
        '请结合原文复核下列问题与建议。以下页码均为 PDF 文件页码；检测范围及执行情况见第三节。',
        'Review the findings against the thesis text. Page references use physical PDF page numbers. Section 3 lists the review scope and execution status.',
      ),
    },
    { kind: 'heading', text: L('2 检测发现与修改建议', '2 Findings and suggested actions') },
  ];
  if (!model.findings.length)
    blocks.push({ kind: 'text', text: t('未发现问题条目；请同时核对上方检测结论及未完成的规则。') });
  for (const item of model.findings) {
    blocks.push({
      kind: 'subheading',
      status: item.severity,
      text: `2.${item.number} ${item.rule_title} (${item.severity})`,
    });
    blocks.push({ kind: 'text', text: item.message });
    item.basis.forEach((text, index) =>
      blocks.push({ kind: item.source_basis_indices?.includes(index) ? 'quote' : 'text', text }),
    );
    for (const location of item.locations) {
      const label = L(`${location.label} · PDF 第 ${location.page} 页`, `${location.label} · PDF p. ${location.page}`);
      if (location.text) blocks.push({ kind: 'quote', text: location.text, sourceLabel: label, marks: location.marks });
      else blocks.push({ kind: 'meta', text: label });
    }
    if (!item.locations.length)
      blocks.push({ kind: 'meta', text: L('原文定位：未提供具体页码', 'Source location: No specific page provided') });
    if (item.suggestions.length)
      blocks.push({
        kind: 'text',
        role: 'advice',
        text: L('修改建议：', 'Suggested action: ') + join(item.suggestions),
      });
    for (const text of item.evidence) blocks.push({ kind: 'quote', text: t('参考证据') + L('：', ': ') + text });
  }
  blocks.push(
    { kind: 'heading', text: L('3 检测范围与执行情况', '3 Review scope and execution') },
    {
      kind: 'text',
      text: L(
        '执行状态不等同于问题等级。未能检测或无法判定的项目不能视为通过。',
        'Execution status is separate from finding categories. Incomplete or inconclusive checks must not be treated as passed.',
      ),
    },
    {
      kind: 'text',
      text: L('本次检测采用规则版本：', 'Rule version used for this review: ') + model.ruleset + L('。', '.'),
    },
  );
  const scopeIds = [...new Set([...model.scope.map((rule) => rule.id), ...model.rules.map((rule) => rule.id)])];
  if (!scopeIds.length) blocks.push({ kind: 'text', text: t('未记录检测规则，无法确认本次检测范围。') });
  for (const [index, id] of scopeIds.entries()) {
    const scope = model.scope.find((rule) => rule.id === id),
      run = model.rules.find((rule) => rule.id === id);
    const status = run?.status || L('未完成', 'Incomplete');
    blocks.push({
      kind: 'subheading',
      role: 'scope',
      status,
      text: `3.${index + 1} ${scope?.title || run?.title || id} (${status})`,
    });
    if (scope?.description) blocks.push({ kind: 'text', text: scope.description });
    if (run) {
      if (run.message) blocks.push({ kind: 'text', text: run.message });
      blocks.push({
        kind: 'text',
        text: L(
          `本项记录 ${run.finding_count} 项检测结果。`,
          `This check records ${run.finding_count} ${run.finding_count === 1 ? 'result' : 'results'}.`,
        ),
      });
      blocks.push(...run.details);
    }
  }
  const signature = model.signature ?? reportSignature(en);
  blocks.push(
    { kind: 'text', text: model.notice },
    { kind: 'meta', role: 'signature', text: signature.system },
    { kind: 'meta', role: 'signature_school', text: signature.institution },
    { kind: 'meta', role: 'website', text: reportSignature(en).website },
  );
  return blocks;
}
