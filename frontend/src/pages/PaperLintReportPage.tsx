import { FileCheck2, FileText } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  fetchPaperLintReport,
  fetchReviewPilotPaperLintRules,
  type PaperLintRule,
  type PaperLintRuleRun,
  type PaperLintRunResponse,
} from '../api/paperLint';
import { CompilerDiagnostics } from '../components/paperLint/CompilerEvidence';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { NumericReviewDetails } from '../components/paperLint/NumericReviewDetails';
import { compilerPublicationLabel, compilerPublicationSummary, flattenPaperLintFindings } from '../components/paperLint/model';
import { usePaperLintRepairSuggestions } from '../hooks/usePaperLintRepairSuggestions';
import {
  deleteFindingFeedback,
  deleteSuggestionFeedback,
  fetchFindingFeedback,
  fetchSuggestionFeedback,
  saveFindingFeedback,
  saveSuggestionFeedback,
  type FindingFeedback,
  type SuggestionFeedback,
} from '../api/feedback';
import { Card, ErrorState, LoadingState, PageHeader, StatusBadge } from '../components/ui';

const outcomeLabels = { passed: '通过', issues_found: '发现问题', inconclusive: '无法判定', not_applicable: '不适用' };
const outcomeTones = {
  passed: 'success',
  issues_found: 'warning',
  inconclusive: 'neutral',
  not_applicable: 'neutral',
} as const;


function executionStatusLabel(status: PaperLintRuleRun['execution_status']) {
  if (status === 'unsupported') return '无法判定';
  if (status === 'error') return '执行失败';
  return null;
}

function PaperLintReportPage({ mode = 'basic' }: { mode?: 'basic' | 'thirty' }) {
  const isThirty = mode === 'thirty';
  const historyPath = isThirty ? '/thirty-rules-check/reports' : '/normative-reports';
  const { reportId } = useParams();
  const [report, setReport] = useState<PaperLintRunResponse | null>(null);
  const [rules, setRules] = useState<PaperLintRule[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reportId) return;
    let cancelled = false;
    setReport(null);
    setError(null);
    void fetchPaperLintReport(reportId)
      .then((nextReport) => {
        if (!cancelled) setReport(nextReport);
      })
      .catch((loadError) => !cancelled && setError(loadError instanceof Error ? loadError.message : '报告加载失败'));
    void fetchReviewPilotPaperLintRules()
      .then((catalog) => {
        if (!cancelled) setRules(catalog.rules);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  const findings = useMemo(() => (report ? flattenPaperLintFindings(report.result) : []), [report]);
  const repairRuleIds = useMemo(
    () => new Set(rules.filter((rule) => rule.repair_supported !== false).map((rule) => rule.rule_id)),
    [rules],
  );
  const repairSuggestions = usePaperLintRepairSuggestions(reportId, repairRuleIds);
  const [findingFeedbackByKey, setFindingFeedbackByKey] = useState<Record<string, FindingFeedback | null>>({});
  const [suggestionFeedbackByFindingKey, setSuggestionFeedbackByFindingKey] = useState<Record<string, SuggestionFeedback | null>>({});

  useEffect(() => {
    if (!reportId || !findings.length) return;
    let active = true;
    void Promise.all(findings.map(async (item) => [item.key, await fetchFindingFeedback(reportId, item.ruleRun.rule_id, item.finding.finding_id)] as const))
      .then((entries) => active && setFindingFeedbackByKey(Object.fromEntries(entries)))
      .catch(() => {});
    return () => { active = false; };
  }, [reportId, findings]);

  useEffect(() => {
    if (!reportId) return;
    let active = true;
    const entries = findings
      .map((item) => [item, repairSuggestions.repairSuggestionByFindingKey[item.key]] as const)
      .filter((entry): entry is readonly [typeof entry[0], NonNullable<typeof entry[1]>] => Boolean(entry[1]?.suggestion_id));
    if (!entries.length) return;
    void Promise.all(entries.map(async ([item, suggestion]) => [item.key, await fetchSuggestionFeedback(reportId, suggestion.suggestion_id!)] as const))
      .then((next) => active && setSuggestionFeedbackByFindingKey((current) => ({ ...current, ...Object.fromEntries(next) })))
      .catch(() => {});
    return () => { active = false; };
  }, [reportId, findings, repairSuggestions.repairSuggestionByFindingKey]);

  const updateFindingFeedback = useCallback(async (item: (typeof findings)[number], value: 'positive' | 'negative') => {
    if (!reportId) return;
    try {
      const feedback = await saveFindingFeedback(reportId, item.ruleRun.rule_id, item.finding.finding_id, { feedback_value: value });
      setFindingFeedbackByKey((current) => ({ ...current, [item.key]: feedback }));
    } catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈保存失败'); }
  }, [reportId]);
  const updateFindingReason = useCallback(async (item: (typeof findings)[number], reasonCode: string | null, reasonText: string | null) => {
    if (!reportId) return;
    try {
      const feedback = await saveFindingFeedback(reportId, item.ruleRun.rule_id, item.finding.finding_id, { feedback_value: 'negative', reason_code: reasonCode, reason_text: reasonText });
      setFindingFeedbackByKey((current) => ({ ...current, [item.key]: feedback }));
    } catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈保存失败'); }
  }, [reportId]);
  const cancelFindingFeedback = useCallback(async (item: (typeof findings)[number]) => {
    if (!reportId) return;
    try { await deleteFindingFeedback(reportId, item.ruleRun.rule_id, item.finding.finding_id); setFindingFeedbackByKey((current) => ({ ...current, [item.key]: null })); }
    catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈取消失败'); }
  }, [reportId]);
  const updateSuggestionFeedback = useCallback(async (item: (typeof findings)[number], value: 'positive' | 'negative') => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!reportId || !suggestion?.suggestion_id) return;
    try { const feedback = await saveSuggestionFeedback(reportId, suggestion.suggestion_id, { feedback_value: value }); setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: feedback })); }
    catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈保存失败'); }
  }, [reportId, repairSuggestions.repairSuggestionByFindingKey]);
  const updateSuggestionReason = useCallback(async (item: (typeof findings)[number], reasonCode: string | null, reasonText: string | null) => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!reportId || !suggestion?.suggestion_id) return;
    try { const feedback = await saveSuggestionFeedback(reportId, suggestion.suggestion_id, { feedback_value: 'negative', reason_code: reasonCode, reason_text: reasonText }); setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: feedback })); }
    catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈保存失败'); }
  }, [reportId, repairSuggestions.repairSuggestionByFindingKey]);
  const cancelSuggestionFeedback = useCallback(async (item: (typeof findings)[number]) => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!reportId || !suggestion?.suggestion_id) return;
    try { await deleteSuggestionFeedback(reportId, suggestion.suggestion_id); setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: null })); }
    catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈取消失败'); }
  }, [reportId, repairSuggestions.repairSuggestionByFindingKey]);
  if (error) return <ErrorState title="报告暂不可用" message={error} />;
  if (!report) return <LoadingState label="正在加载检测报告和原文定位…" />;
  const { summary } = report.result;
  const completedRuleCount = summary.completed_rule_count ?? Math.max(
    0,
    summary.rule_count - summary.unsupported_rule_count - summary.error_rule_count,
  );
  const pdfUrl = `/api/normative/paper-lint/reports/${encodeURIComponent(reportId!)}/pdf`;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={summary.error_rule_count ? '部分检测执行失败' : '已完成检测'}
        title={
          report.result.paper_title === '上传论文'
            ? report.source_filename
            : report.result.paper_title || report.source_filename
        }
        description={`检测于 ${new Date(report.created_at).toLocaleString('zh-CN')} 完成。请优先处理严重和警告问题。`}
        breadcrumbs={[
          { label: '首页', to: '/' },
          {
            label: isThirty ? 'PDF 规则检测' : '基础规则检测',
            to: isThirty ? '/thirty-rules-check' : '/normative-check',
          },
          { label: '历史报告', to: historyPath },
          { label: '检测报告' },
        ]}
        actions={
          <Link className="text-sm font-semibold text-brand-700 hover:underline" to={historyPath}>
            返回历史报告
          </Link>
        }
      />
      <Card
        title="检测结论"
        description="以下结论用于修改前自查，不替代导师或学院的正式审核。"
        actions={
          <StatusBadge
            tone={
              summary.error_finding_count
                ? 'danger'
                : summary.warning_finding_count
                  ? 'warning'
                  : summary.unsupported_rule_count + summary.error_rule_count
                    ? 'neutral'
                    : 'success'
            }
          >
            {compilerPublicationSummary(report.result) || (summary.finding_count
              ? `待处理 ${summary.finding_count} 项`
                : summary.error_rule_count
                  ? '部分规则执行失败'
                  : summary.unsupported_rule_count
                    ? '部分规则无法判定'
                : isThirty
                  ? '规则检查通过'
                  : '基础检查通过')}
          </StatusBadge>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ['选择规则', report.selected_rule_ids.length],
            ['已完成', completedRuleCount],
            ['无法判定', summary.unsupported_rule_count],
            ['执行失败', summary.error_rule_count],
            ['问题总数', summary.finding_count],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs text-slate-500">{label}</p>
              <p className="mt-1 text-2xl font-black text-slate-900">{value}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 flex items-center gap-2 text-sm text-slate-600">
          <FileCheck2 className="size-4 text-brand-600" />
          规则版本：{report.summary.ruleset_label || '当前发布版本'} · 原文可定位问题{' '}
          {findings.filter((item) => item.finding.location || item.finding.anchors?.length).length} 项
        </p>
      </Card>
      <Card title="各规则执行状态">
        <div className="grid gap-2 md:grid-cols-2">
          {report.result.rule_runs.map((run) => (
            <div
              key={run.rule_run_id}
              className="flex items-start justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-800">
                  {rules.find((rule) => rule.rule_id === run.rule_id)?.title || run.rule_id}
                </p>
                {run.message ? <p className="mt-1 text-xs text-slate-600">{run.message}</p> : null}
                <NumericReviewDetails run={run} pdfUrl={pdfUrl} />
                <CompilerDiagnostics items={run.compiler_diagnostics} />
              </div>
              <StatusBadge tone={run.execution_status === 'error' ? 'danger' : outcomeTones[run.outcome]}>
                {compilerPublicationLabel(run) || executionStatusLabel(run.execution_status) || outcomeLabels[run.outcome]}
              </StatusBadge>
            </div>
          ))}
        </div>
      </Card>
      <div className="flex items-center gap-2">
        <FileText className="size-5 text-brand-600" />
        <h2 className="text-lg font-black text-slate-900">逐项处理问题</h2>
      </div>
      <PaperLintWorkspace
        file={{ name: report.source_filename, url: pdfUrl }}
        openPdfUrl={pdfUrl}
        findings={findings}
        rules={rules}
        repairSuggestionByFindingKey={repairSuggestions.repairSuggestionByFindingKey}
        repairSuggestionLoadingKey={repairSuggestions.repairSuggestionLoadingKey}
        repairSuggestionLoadingByFindingKey={repairSuggestions.repairSuggestionLoadingByFindingKey}
        repairSuggestionErrorByFindingKey={repairSuggestions.repairSuggestionErrorByFindingKey}
        onLoadRepairSuggestion={repairSuggestions.loadRepairSuggestion}
        onGenerateRepairSuggestion={repairSuggestions.generateRepairSuggestion}
        supportsRepairSuggestion={repairSuggestions.supportsRepairSuggestion}
        forceNewRepairSuggestion
        findingFeedbackByKey={findingFeedbackByKey}
        suggestionFeedbackByFindingKey={suggestionFeedbackByFindingKey}
        onFindingFeedback={updateFindingFeedback}
        onFindingFeedbackReason={updateFindingReason}
        onFindingFeedbackCancel={cancelFindingFeedback}
        onSuggestionFeedback={updateSuggestionFeedback}
        onSuggestionFeedbackReason={updateSuggestionReason}
        onSuggestionFeedbackCancel={cancelSuggestionFeedback}
      />
    </div>
  );
}

export default PaperLintReportPage;
