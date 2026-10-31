import type {
  PaperLintDocumentMetrics,
  PaperLintRule,
  PaperLintRunResponse,
  PaperLintSummary,
} from '../../api/paperLint';
import type { RepairSuggestion } from '../../api/repairSuggestions';
import {
  compilerPublicationLabel,
  compilerPublicationSummary,
  flattenPaperLintFindings,
} from '../../components/paperLint/model';
import { formatChinaDateTime } from '../dateTime';
import { numericReportBlocks } from './numericDetails';

export const EXPORT_NOTICE = '检测结果仅供参考，请结合论文原文和学校要求人工复核。';
export type DetectionScopeItem = { id: string; title: string; description: string };

export function buildDetectionScope(report: PaperLintRunResponse, rules: PaperLintRule[]): DetectionScopeItem[] {
  const ids = report.selected_rule_ids?.length
    ? report.selected_rule_ids
    : report.result.rule_runs.map((run) => run.rule_id);
  const catalog = new Map(rules.map((rule) => [rule.rule_id, rule]));
  return [...new Set(ids)].map((id) => {
    const rule = catalog.get(id);
    const description = rule?.description?.trim().replace(/\s+/g, ' ');
    const characters = Array.from(description || '规则说明暂不可用（目录中未提供）。');
    return {
      id,
      title: rule?.title?.trim() || id,
      description: characters.length > 120 ? characters.slice(0, 120).join('') + '…' : characters.join(''),
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
  locations: { label: string; page: number; text: string }[];
  suggestions: string[];
  evidence: string[];
  basis: string[];
};
export type ExportReport = {
  schema_version: 1;
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
    message: string;
    finding_count: number;
    details: ReportBlock[];
  }[];
  findings: ExportFinding[];
  notice: string;
};
export type ReportBlock = {
  kind: 'title' | 'heading' | 'subheading' | 'meta' | 'text' | 'quote' | 'notice';
  text: string;
};

export function buildExportReport(
  report: PaperLintRunResponse,
  rules: PaperLintRule[],
  metrics: PaperLintDocumentMetrics | null,
  repairs: Record<string, RepairSuggestion | undefined> = {},
): ExportReport {
  const result = report.result,
    summary = result.summary;
  const title = (id: string) => rules.find((r) => r.rule_id === id)?.title || id;
  const inconclusive =
    summary.unsupported_rule_count > 0 ||
    result.rule_runs.some((r) => r.outcome === 'inconclusive' && compilerPublicationLabel(r) !== '未触发告警');
  const conclusion = summary.finding_count
    ? `发现 ${summary.finding_count} 项问题，请逐项核对。`
    : summary.error_rule_count
      ? '部分规则执行失败，请核对未完成的检测项。'
      : inconclusive
        ? '部分规则无法判定，请人工核对。'
        : compilerPublicationSummary(result) || '规则检查通过，未发现问题。';
  const severity = { error: '严重错误', warning: '警告', info: '提示' };
  return {
    schema_version: 1,
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
      status:
        compilerPublicationLabel(run) ||
        (run.execution_status === 'error'
          ? '执行失败'
          : run.execution_status === 'unsupported'
            ? '不适用'
            : { passed: '通过', issues_found: '发现问题', inconclusive: '无法判定', not_applicable: '不适用' }[
                run.outcome
              ]),
      message: run.message || '',
      finding_count: run.findings.length,
      details: numericReportBlocks(run),
    })),
    findings: flattenPaperLintFindings(result).map(({ key, finding, ruleRun }, index) => {
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
          )
            locations.push({ label, page, text: location.text_excerpt || '' });
      };
      add(finding.location, '原文定位');
      finding.anchors?.forEach((anchor) => add(anchor.location, anchor.label || anchor.role || '相关位置'));
      const repair = repairs[key],
        suggestions = finding.suggestion ? [finding.suggestion] : [];
      if (repair) {
        if (repair.status === 'suggested') suggestions.push(...repair.actions.map((a) => a.instruction));
        else
          suggestions.push(
            `AI 建议状态：${repair.status === 'insufficient_context' ? '上下文不足' : '证据存在冲突'}`,
            ...(repair.missing_context || []),
          );
        if (repair.rationale) suggestions.push(repair.rationale);
      }
      return {
        number: index + 1,
        id: finding.finding_id,
        rule_id: ruleRun.rule_id,
        rule_title: title(ruleRun.rule_id),
        severity: severity[ruleRun.severity] || ruleRun.severity,
        message: finding.message,
        locations,
        suggestions: [...new Set(suggestions)],
        evidence: (finding.evidence || []).map((e) => [e.quote, e.url].filter(Boolean).join(' — ')).filter(Boolean),
        basis: (finding.basis_details || []).map((b) => b.text || '').filter(Boolean),
      };
    }),
    notice: EXPORT_NOTICE,
  };
}

export function reportBlocks(model: ExportReport): ReportBlock[] {
  const blocks: ReportBlock[] = [
    { kind: 'title', text: '论文规范性检测报告' },
    { kind: 'meta', text: `文档名称：${model.document.filename}` },
    { kind: 'meta', text: `论文题目：${model.document.title || '未提供'}` },
    { kind: 'meta', text: `报告生成时间：${formatChinaDateTime(model.created_at, { includeSeconds: true })}` },
    { kind: 'meta', text: `检测类型：${model.detection_type}    规则版本：${model.ruleset}` },
    { kind: 'heading', text: '检测结论' },
    { kind: 'text', text: model.conclusion },
    {
      kind: 'meta',
      text: `论文总页数：${model.document.page_count ?? '未统计'}    论文总字数：${model.document.word_count ?? '未统计'}`,
    },
    {
      kind: 'meta',
      text: `错误总数：${model.summary.finding_count}    严重错误数：${model.summary.error_finding_count}    警告错误数：${model.summary.warning_finding_count}    提示错误数：${model.summary.info_finding_count}`,
    },
    { kind: 'notice', text: model.notice },
    { kind: 'heading', text: '本次检测范围' },
    { kind: 'meta', text: `已选择 ${model.scope.length} 项规则` },
    ...(model.scope.length
      ? model.scope.map((rule): ReportBlock => ({
          kind: 'text',
          text: `${rule.title}（${rule.id}）：${rule.description}`,
        }))
      : [{ kind: 'text' as const, text: '未记录检测规则，无法确认本次检测范围。' }]),
    { kind: 'heading', text: '问题清单' },
  ];
  if (!model.findings.length)
    blocks.push({ kind: 'text', text: '未发现问题条目；请同时核对上方检测结论及未完成的规则。' });
  for (const item of model.findings) {
    blocks.push(
      { kind: 'subheading', text: `${item.number}. ${item.rule_title} · ${item.severity}` },
      { kind: 'text', text: item.message },
    );
    if (!item.locations.length) blocks.push({ kind: 'meta', text: '原文定位：未提供具体页码' });
    for (const location of item.locations) {
      blocks.push({ kind: 'meta', text: `${location.label}：PDF 第 ${location.page} 页` });
      if (location.text) blocks.push({ kind: 'quote', text: location.text });
    }
    for (const text of item.basis) blocks.push({ kind: 'text', text: `检查依据：${text}` });
    for (const text of item.evidence) blocks.push({ kind: 'quote', text: `参考证据：${text}` });
    for (const text of item.suggestions) blocks.push({ kind: 'text', text: `修改建议：${text}` });
  }
  blocks.push({ kind: 'heading', text: '检测规则' });
  for (const rule of model.rules) {
    blocks.push({ kind: 'text', text: `${rule.title}：${rule.status}（${rule.finding_count} 项）` });
    if (rule.message) blocks.push({ kind: 'meta', text: rule.message });
    blocks.push(...rule.details);
  }
  return blocks;
}
export const reportText = (model: ExportReport) =>
  reportBlocks(model)
    .map((b) => b.text)
    .join('\n\n') + '\n';
const mdEscape = (text: string) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/[\\`*{}\[\]()#+.!_|-]/g, '\\$&');
export function reportMarkdown(model: ExportReport) {
  return (
    reportBlocks(model)
      .map(({ kind, text }) => {
        const value = mdEscape(text);
        if (kind === 'title') return '# ' + value;
        if (kind === 'heading') return '## ' + value;
        if (kind === 'subheading') return '### ' + value;
        if (kind === 'quote' || kind === 'notice')
          return value
            .split('\n')
            .map((line) => '> ' + line)
            .join('\n');
        return value.replace(/\n/g, '  \n');
      })
      .join('\n\n') + '\n'
  );
}
export function safeReportFilename(filename: string) {
  const clean = Array.from(
    filename
      .replace(/\.[^.]+$/, '')
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
      .trim(),
  )
    .slice(0, 100)
    .join('')
    .replace(/[. ]+$/, '');
  return (clean || '论文') + '_检测报告';
}
