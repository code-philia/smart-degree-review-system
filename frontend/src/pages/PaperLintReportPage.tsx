import { FileText } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  fetchPaperLintReport,
  fetchPaperLintDocumentMetrics,
  fetchReviewPilotPaperLintRules,
  type PaperLintDocumentMetrics,
  type PaperLintRule,
  type PaperLintRunResponse,
} from '../api/paperLint';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
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
import { Card, ErrorState, LoadingState, StatusBadge } from '../components/ui';
import { formatChinaDateTime } from '../utils/dateTime';

function PaperLintReportPage({ mode = 'basic' }: { mode?: 'basic' | 'thirty' }) {
  const isThirty = mode === 'thirty';
  const historyPath = isThirty ? '/thirty-rules-check/reports' : '/normative-reports';
  const { reportId } = useParams();
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
        if (!cancelled) setReport(nextReport);
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
  const inconclusiveRuns = report.result.rule_runs.filter((run) =>
    run.outcome === 'inconclusive' && compilerPublicationLabel(run) !== '未触发告警');
  const hasInconclusiveRules = summary.unsupported_rule_count > 0 || inconclusiveRuns.length > 0;
  const unavailableReasons = [...new Set(report.result.rule_runs
    .filter((run) => run.execution_status === 'unsupported' || run.execution_status === 'error' || inconclusiveRuns.includes(run))
    .map((run) => run.message).filter(Boolean))];
  const metricsPlaceholder = metricsLoading ? '统计中…' : '未统计';
  const pdfUrl = `/api/normative/paper-lint/reports/${encodeURIComponent(reportId!)}/pdf`;
  const isSemanticReport = report.selected_rule_ids.includes('abstract_numeric_consistency_check');
  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-5">
      <Card aria-labelledby="report-conclusion-title">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-brand-700">规范性检测</p>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h1 className="break-all text-lg font-bold text-slate-900 sm:text-xl">{report.source_filename}</h1>
              <time dateTime={report.created_at} className="whitespace-nowrap text-xs text-slate-500">
                {formatChinaDateTime(report.created_at, { includeSeconds: true })}
              </time>
            </div>
          </div>
          <Link className="text-sm font-semibold text-brand-700 hover:underline" to={historyPath}>返回历史报告</Link>
        </div>
        <div className="my-4 flex flex-wrap items-center justify-between gap-2">
          <h2 id="report-conclusion-title" className="font-bold text-slate-900">检测结论</h2>
          <StatusBadge
            tone={
              summary.error_finding_count
                ? 'danger'
                : summary.warning_finding_count
                  ? 'warning'
                  : hasInconclusiveRules || summary.error_rule_count
                    ? 'neutral'
                    : 'success'
            }
          >
            {summary.finding_count
              ? `待处理 ${summary.finding_count} 项`
                : summary.error_rule_count
                  ? '部分规则执行失败'
                  : hasInconclusiveRules
                    ? '部分规则无法判定'
                : compilerPublicationSummary(report.result) || (isThirty
                  ? '规则检查通过'
                  : '基础检查通过')}
          </StatusBadge>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {[
            ['论文总页数', metrics?.page_count?.toLocaleString('en-US') ?? metricsPlaceholder],
            ['论文总字数', metrics?.text_available && metrics.word_count != null ? metrics.word_count.toLocaleString('en-US') : metricsPlaceholder],
            ['错误总数', summary.finding_count],
            ['严重错误数', summary.error_finding_count],
            ['警告错误数', summary.warning_finding_count],
            ['提示错误数', summary.info_finding_count],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs text-slate-500">{label}</p>
              <p className="mt-1 text-2xl font-black text-slate-900">{value}</p>
            </div>
          ))}
        </div>
        {unavailableReasons.length > 0 ? <p className="mt-3 text-sm text-slate-600">{unavailableReasons.join('；')}</p> : null}
      </Card>
      {!isSemanticReport ? <div className="flex items-center gap-2">
        <FileText className="size-5 text-brand-600" />
        <h2 className="text-lg font-black text-slate-900">逐项处理问题</h2>
      </div> : null}
      <div className="mx-auto w-full max-w-7xl">
        <PaperLintWorkspace
        layout={isSemanticReport ? 'semantic' : 'default'}
        numericReviewRun={isSemanticReport ? report.result.rule_runs.find((run) => run.rule_id === 'abstract_numeric_consistency_check') : undefined}
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
