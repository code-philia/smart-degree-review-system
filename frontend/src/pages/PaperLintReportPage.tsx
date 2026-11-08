import { REVIEW_ROUTES } from '../nav/reviewRoutes';
import { ArrowLeft, FileText } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  fetchPaperLintReport,
  fetchPaperLintDocumentMetrics,
  fetchReviewPilotPaperLintRules,
  type PaperLintDocumentMetrics,
  type PaperLintRule,
  type PaperLintRunResponse,
} from '../api/paperLint';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { isDocumentBlocked, compilerPublicationLabel, compilerPublicationSummary, flattenPaperLintFindings, paperLintFeedbackItems, paperLintPresentation, referenceResourcesUnavailable } from '../components/paperLint/model';
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
import { Card, ErrorState, LoadingState, StatusBadge } from '../components/ui';
import { formatChinaDateTime } from '../utils/dateTime';
import { ReportExportDialog } from '../components/paperLint/ReportExportDialog';
import { IncrementalRerunDialog } from '../components/paperLint/IncrementalRerunDialog';
import { DetectionScope } from '../components/paperLint/DetectionScope';
import { REPORT_DOCUMENT_TEXT } from '../components/paperLint/documentTypography';

function PaperLintReportPage({ mode = 'basic' }: { mode?: 'basic' | 'thirty' }) {
  const isThirty = mode === 'thirty';
  const historyPath = isThirty ? REVIEW_ROUTES.history : '/normative-reports';
  const { reportId } = useParams();
  const [searchParams] = useSearchParams();
  const [report, setReport] = useState<PaperLintRunResponse | null>(null);
  const [rules, setRules] = useState<PaperLintRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<PaperLintDocumentMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);

  useEffect(() => {
    if (!reportId) return;
    let cancelled = false;
    setReport(null);
    setError(null);
    setMetrics(null);
    setMetricsLoading(true);
    void fetchPaperLintReport(reportId)
      .then((nextReport) => {
        if (!cancelled) setReport({ ...nextReport,
          selected_rule_ids: nextReport.selected_rule_ids ?? nextReport.result.rule_runs.map(run => run.rule_id),
          result: paperLintPresentation(nextReport.result) });
      })
      .catch((loadError) => !cancelled && setError(loadError instanceof Error ? loadError.message : '报告加载失败'));
    void fetchPaperLintDocumentMetrics(reportId)
      .then((nextMetrics) => {
        if (!cancelled) setMetrics(nextMetrics);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setMetricsLoading(false);
      });
    void fetchReviewPilotPaperLintRules()
      .then((catalog) => {
        if (!cancelled) setRules(catalog.rules);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  const feedbackReportId = report?.id === reportId ? reportId : null;
  const findings = useMemo(() => (report ? flattenPaperLintFindings(report.result) : []), [report]);
  const feedbackItems = useMemo(() => (report && feedbackReportId ? paperLintFeedbackItems(report.result) : []), [report, feedbackReportId]);
  const repairRuleIds = useMemo(
    () => new Set(rules.filter((rule) => rule.repair_supported !== false).map((rule) => rule.rule_id)),
    [rules],
  );
  const repairSuggestions = usePaperLintRepairSuggestions(reportId, repairRuleIds);
  const [findingFeedbackByReportId, setFindingFeedbackByReportId] = useState<Record<string, Record<string, FindingFeedback | null>>>({});
  const findingFeedbackByKey = feedbackReportId ? findingFeedbackByReportId[feedbackReportId] || {} : {};
  const [suggestionFeedbackByFindingKey, setSuggestionFeedbackByFindingKey] = useState<Record<string, SuggestionFeedback | null>>({});

  useEffect(() => {
    if (!feedbackReportId || !feedbackItems.length) return;
    let active = true;
    void Promise.allSettled(feedbackItems.map(async (item) => [item.key, await fetchFindingFeedback(feedbackReportId, item.ruleRun.rule_id, item.finding.finding_id)] as const))
      .then((results) => active && setFindingFeedbackByReportId(current => ({ ...current, [feedbackReportId]: Object.fromEntries(
        results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []),
      ) })))
      .catch(() => {});
    return () => { active = false; };
  }, [feedbackReportId, feedbackItems]);

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
    if (!feedbackReportId) return;
    try {
      const feedback = await saveFindingFeedback(feedbackReportId, item.ruleRun.rule_id, item.finding.finding_id, { feedback_value: value });
      setFindingFeedbackByReportId(current => ({ ...current, [feedbackReportId]: { ...current[feedbackReportId], [item.key]: feedback } }));
    } catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈保存失败'); }
  }, [feedbackReportId]);
  const updateFindingReason = useCallback(async (item: (typeof findings)[number], reasonCode: string | null, reasonText: string | null) => {
    if (!feedbackReportId) throw new Error('请重新打开检测报告后提交反馈');
    const feedback = await saveFindingFeedback(feedbackReportId, item.ruleRun.rule_id, item.finding.finding_id, { feedback_value: 'negative', reason_code: reasonCode, reason_text: reasonText });
    setFindingFeedbackByReportId(current => ({ ...current, [feedbackReportId]: { ...current[feedbackReportId], [item.key]: feedback } }));
  }, [feedbackReportId]);
  const cancelFindingFeedback = useCallback(async (item: (typeof findings)[number]) => {
    if (!feedbackReportId) return;
    try { await deleteFindingFeedback(feedbackReportId, item.ruleRun.rule_id, item.finding.finding_id); setFindingFeedbackByReportId(current => ({ ...current, [feedbackReportId]: { ...current[feedbackReportId], [item.key]: null } })); }
    catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈取消失败'); }
  }, [feedbackReportId]);
  const updateSuggestionFeedback = useCallback(async (item: (typeof findings)[number], value: 'positive' | 'negative') => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!reportId || !suggestion?.suggestion_id) return;
    try { const feedback = await saveSuggestionFeedback(reportId, suggestion.suggestion_id, { feedback_value: value }); setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: feedback })); }
    catch (cause) { window.alert(cause instanceof Error ? cause.message : '反馈保存失败'); }
  }, [reportId, repairSuggestions.repairSuggestionByFindingKey]);
  const updateSuggestionReason = useCallback(async (item: (typeof findings)[number], reasonCode: string | null, reasonText: string | null) => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!reportId || !suggestion?.suggestion_id) throw new Error('请重新加载修复建议后提交反馈');
    const feedback = await saveSuggestionFeedback(reportId, suggestion.suggestion_id, { feedback_value: 'negative', reason_code: reasonCode, reason_text: reasonText });
    setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: feedback }));
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
  const inconclusiveRuns = report.result.rule_runs.filter((run) =>
    run.outcome === 'inconclusive' && !(run.rule_id === 'sjtu_rule_32' && run.execution_status === 'completed' && !referenceResourcesUnavailable(run)) && compilerPublicationLabel(run) !== '未触发告警');
  const hasInconclusiveRules = summary.unsupported_rule_count > 0 || inconclusiveRuns.length > 0;
  const unavailableReasons = [...new Set(report.result.rule_runs
    .filter((run) => run.execution_status === 'unsupported' || run.execution_status === 'error' || inconclusiveRuns.includes(run))
    .map((run) => run.message).filter(Boolean))];
  const metricsPlaceholder = metricsLoading ? '统计中…' : '未统计';
  const pdfUrl = `/api/normative/paper-lint/reports/${encodeURIComponent(reportId!)}/pdf`;
  const numericReviewRun = report.result.rule_runs.find(run => run.rule_id === 'abstract_numeric_consistency_check');
  const documentBlocked = isDocumentBlocked(report.result.rule_runs);
  const isSemanticReport = Boolean(numericReviewRun && report.result.rule_runs.length === 1);
  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-5">
      <Link to={historyPath} className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 motion-reduce:transition-none">
        <ArrowLeft className="size-[18px]" aria-hidden="true" />返回历史报告
      </Link>
      <Card aria-labelledby="report-conclusion-title">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
          <div className="w-full min-w-0 sm:w-auto sm:flex-1">
            <p className="text-lg font-bold leading-7 tracking-tight text-brand-700 sm:text-xl">规范性检测</p>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h1 className={`break-all text-slate-600 ${REPORT_DOCUMENT_TEXT}`}>{report.source_filename}</h1>
              <time dateTime={report.created_at} className="whitespace-nowrap text-xs text-slate-500">
                {formatChinaDateTime(report.created_at, { includeSeconds: true })}
              </time>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            {!documentBlocked && <IncrementalRerunDialog key={report.id} report={report} rules={rules} initiallyOpen={searchParams.get('rerun') === '1'} />}
            <ReportExportDialog report={report} rules={rules} metrics={metrics} repairs={repairSuggestions.repairSuggestionByFindingKey} />

          </div>
        </div>
        <div className="my-4 flex flex-wrap items-center justify-between gap-2">
          <h2 id="report-conclusion-title" className="font-bold text-slate-900">检测结论</h2>
          {summary.finding_count === (summary.execution_warning_count ?? 0) ? (
            <StatusBadge tone={hasInconclusiveRules || summary.error_rule_count ? 'neutral' : 'success'}>
              {summary.error_rule_count
                ? '部分规则执行失败'
                : hasInconclusiveRules
                  ? '部分规则无法判定'
                  : compilerPublicationSummary(report.result) || (isThirty
                    ? '规则检查通过'
                    : '基础检查通过')}
            </StatusBadge>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-7">
          {[
            ['论文总页数', metrics?.page_count?.toLocaleString('en-US') ?? metricsPlaceholder],
            ['论文总字数', metrics?.text_available && metrics.word_count != null ? metrics.word_count.toLocaleString('en-US') : metricsPlaceholder],
            ['错误总数', summary.finding_count],
            ['严重错误数', summary.error_finding_count],
            ['警告错误数', summary.warning_finding_count],
            ['提示错误数', summary.info_finding_count],
            ['规则未实现警告数', summary.execution_warning_count ?? 0],
          ].map(([label, value]) => (
            <div key={String(label)} className={`rounded-lg border p-3 ${label === '规则未实现警告数' ? 'border-violet-100 bg-violet-50/50' : 'border-slate-200 bg-slate-50'}`}>
              <p className={`text-xs ${label === '规则未实现警告数' ? 'text-violet-700' : 'text-slate-500'}`}>{label}</p>
              <p className={`mt-1 text-2xl font-black ${label === '规则未实现警告数' ? 'text-violet-700' : 'text-slate-900'}`}>{value}</p>
            </div>
          ))}
        </div>
        {unavailableReasons.length > 0 ? <p className="mt-3 text-sm text-slate-600">{unavailableReasons.join('；')}</p> : null}
      </Card>
      <DetectionScope report={report} rules={rules} />
      {!isSemanticReport ? <div className="flex items-center gap-2">
        <FileText className="size-5 text-brand-600" />
        <h2 className="text-lg font-black text-slate-900">检测报告详情预览</h2>
      </div> : null}
      <div className="mx-auto w-full max-w-7xl">
        <PaperLintWorkspace
        layout={isSemanticReport ? 'semantic' : 'default'}
        selectedRuleIds={report.selected_rule_ids}
        ruleRuns={report.result.rule_runs}
        numericReviewRun={numericReviewRun}
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
    </div>
  );
}

export default PaperLintReportPage;
