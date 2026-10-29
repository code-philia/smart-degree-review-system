import axios from 'axios';
import { FileCheck2, FileText, LoaderCircle, Play, Square, Upload, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  fetchReviewPilotPaperLintRules,
  fetchPaperLintJob,
  cancelPaperLintJob,
  fetchPaperLintReport,
  isPaperLintJobResponse,
  runReviewPilotPaperLint,
  type PaperLintCatalogResponse,
  type PaperLintRunResponse,
  type PaperLintRule,
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
import {
  Button,
  Card,
  ErrorState,
  LinkButton,
  LoadingState,
  ModuleTabs,
  PageHeader,
  StatusBadge,
} from '../components/ui';

const MAX_PDF_BYTES = 50 * 1024 * 1024;
type CheckMode = 'basic' | 'thirty';
type ResultFile = File | { name: string; url: string };
type StoredPaperLintJob = { jobId: string | null; requestId: string; filename: string; selectedRuleIds: string[] };

function activeJobStorageKey(userId: string) {
  return `paper-lint-active-job:${userId}`;
}

function newRequestId() {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `paper-lint-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function rulesForMode(rules: PaperLintRule[], mode: CheckMode) {
  const filtered = rules.filter((rule) => Boolean(rule.enabled_in_mvp) === (mode === 'thirty'));
  if (mode === 'thirty') {
    filtered.sort(
      (a, b) => Number(a.rule_id.slice('sjtu_rule_'.length)) - Number(b.rule_id.slice('sjtu_rule_'.length)),
    );
  }
  return filtered;
}

function errorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const message = error.response?.data?.message;
    if (typeof message === 'string' && message.trim()) return message;
    if (error.code === 'ECONNABORTED') return '规则审查运行超时，请减少规则后重试';
    if (!error.response) return '连接异常，正在确认任务状态';
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

function validatePdf(file: File) {
  if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
    throw new Error('仅支持上传 PDF 文件');
  }
  if (file.size > MAX_PDF_BYTES) throw new Error('PDF 文件大小不能超过 50 MB');
  if (file.size === 0) throw new Error('PDF 文件不能为空');
}

function fileSizeLabel(size: number) {
  return size >= 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(size / 1024)} KB`;
}

function partialPaperLintResponse(jobId: string, filename: string, runs: PaperLintRunResponse['result']['rule_runs']): PaperLintRunResponse {
  const findings = runs.flatMap((run) => run.findings || []);
  return { id: jobId, source_filename: filename, selected_rule_ids: runs.map((run) => run.rule_id), created_at: new Date().toISOString(), summary: { finding_count: findings.length, error_finding_count: runs.filter((run) => run.severity === 'error').reduce((n, run) => n + run.findings.length, 0), warning_finding_count: runs.filter((run) => run.severity === 'warning').reduce((n, run) => n + run.findings.length, 0), info_finding_count: runs.filter((run) => run.severity === 'info').reduce((n, run) => n + run.findings.length, 0), rule_count: runs.length, unsupported_rule_count: runs.filter((run) => run.execution_status === 'unsupported').length, error_rule_count: runs.filter((run) => run.execution_status === 'error').length, ruleset_label: '已完成规则' }, result: {
    type: 'paper_lint', paper_title: '上传论文', ruleset: { id: 'paper-lint-progress', name: '规则检测进行中', version_number: 1, version_label: '已完成规则' }, rule_runs: runs,
    summary: { rule_count: runs.length, completed_rule_count: runs.length, unsupported_rule_count: runs.filter((run) => run.execution_status === 'unsupported').length, error_rule_count: runs.filter((run) => run.execution_status === 'error').length, issue_rule_count: runs.filter((run) => run.outcome === 'issues_found').length, finding_count: findings.length, error_finding_count: runs.filter((run) => run.severity === 'error').reduce((n, run) => n + run.findings.length, 0), warning_finding_count: runs.filter((run) => run.severity === 'warning').reduce((n, run) => n + run.findings.length, 0), info_finding_count: runs.filter((run) => run.severity === 'info').reduce((n, run) => n + run.findings.length, 0), derived_rule_count: runs.filter((run) => run.evidence_mode === 'derived').length },
  }};
}

const outcomeLabels = {
  passed: '未发现可确认问题',
  issues_found: '发现问题',
  inconclusive: '无法判定',
  not_applicable: '不适用',
};

const outcomeTones = {
  passed: 'success',
  issues_found: 'warning',
  inconclusive: 'neutral',
  not_applicable: 'neutral',
} as const;

function NormativeCheckPage({ mode = 'basic' }: { mode?: CheckMode }) {
  const isThirty = mode === 'thirty';
  const title = isThirty ? 'PDF 规则检测' : '基础规则检测';
  const { status, user } = useAuthSession();
  const [catalog, setCatalog] = useState<PaperLintCatalogResponse | null>(null);
  const [selectedRuleIds, setSelectedRuleIds] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [resultFile, setResultFile] = useState<ResultFile | null>(null);
  const [response, setResponse] = useState<PaperLintRunResponse | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopped, setStopped] = useState(false);
  const runGenerationRef = useRef(0);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const requestIdRef = useRef<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<{ completed: number; total: number } | null>(null);
  const [externalConsent, setExternalConsent] = useState(false);
  useEffect(() => () => { runGenerationRef.current += 1; }, []);

  const loadCatalog = async () => {
    setCatalogLoading(true);
    setCatalogError(null);
    try {
      const nextCatalog = await fetchReviewPilotPaperLintRules();
      setCatalog(nextCatalog);
      const hasRestoredSelection = user && localStorage.getItem(activeJobStorageKey(user.id));
      if (!hasRestoredSelection) {
        setSelectedRuleIds(
          rulesForMode(nextCatalog.rules, mode)
            .filter((rule) => rule.default_enabled)
            .map((rule) => rule.rule_id),
        );
      }
    } catch (error) {
      setCatalog(null);
      setCatalogError(errorMessage(error, '规则目录加载失败'));
    } finally {
      setCatalogLoading(false);
    }
  };

  useEffect(() => {
    if (user) void loadCatalog();
  }, [user?.id, mode]);

  const visibleRules = useMemo(() => rulesForMode(catalog?.rules || [], mode), [catalog, mode]);
  const rulesById = useMemo(() => new Map((catalog?.rules || []).map((rule) => [rule.rule_id, rule])), [catalog]);
  const selectedExternalRule = useMemo(
    () => visibleRules.some((rule) => selectedRuleIds.includes(rule.rule_id) && rule.uses_external_model),
    [selectedRuleIds, visibleRules],
  );
  const findings = useMemo(() => (response ? flattenPaperLintFindings(response.result) : []), [response]);
  const repairSuggestions = usePaperLintRepairSuggestions(response?.id);
  const [findingFeedbackByKey, setFindingFeedbackByKey] = useState<Record<string, FindingFeedback | null>>({});
  const [suggestionFeedbackByFindingKey, setSuggestionFeedbackByFindingKey] = useState<Record<string, SuggestionFeedback | null>>({});

  useEffect(() => {
    if (!response?.id || !findings.length) return;
    let active = true;
    void Promise.all(
      findings.map(async (item) => [
        item.key,
        await fetchFindingFeedback(response.id, item.ruleRun.rule_id, item.finding.finding_id),
      ] as const),
    )
      .then((entries) => active && setFindingFeedbackByKey(Object.fromEntries(entries)))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [response?.id, findings]);

  useEffect(() => {
    if (!response?.id) return;
    let active = true;
    const entries = findings
      .map((item) => [item, repairSuggestions.repairSuggestionByFindingKey[item.key]] as const)
      .filter((entry): entry is readonly [typeof entry[0], NonNullable<typeof entry[1]>] => Boolean(entry[1]?.suggestion_id));
    if (!entries.length) return;
    void Promise.all(
      entries.map(async ([item, suggestion]) => [
        item.key,
        await fetchSuggestionFeedback(response.id, suggestion.suggestion_id!),
      ] as const),
    )
      .then((next) => active && setSuggestionFeedbackByFindingKey((current) => ({ ...current, ...Object.fromEntries(next) })))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [response?.id, findings, repairSuggestions.repairSuggestionByFindingKey]);

  const updateFindingFeedback = useCallback(async (item: (typeof findings)[number], value: 'positive' | 'negative') => {
    if (!response?.id) return;
    try {
      const feedback = await saveFindingFeedback(response.id, item.ruleRun.rule_id, item.finding.finding_id, { feedback_value: value });
      setFindingFeedbackByKey((current) => ({ ...current, [item.key]: feedback }));
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '反馈保存失败');
    }
  }, [response?.id]);
  const updateFindingReason = useCallback(async (item: (typeof findings)[number], reasonCode: string | null, reasonText: string | null) => {
    if (!response?.id) return;
    try {
      const feedback = await saveFindingFeedback(response.id, item.ruleRun.rule_id, item.finding.finding_id, {
        feedback_value: 'negative', reason_code: reasonCode, reason_text: reasonText,
      });
      setFindingFeedbackByKey((current) => ({ ...current, [item.key]: feedback }));
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '反馈保存失败');
    }
  }, [response?.id]);
  const cancelFindingFeedback = useCallback(async (item: (typeof findings)[number]) => {
    if (!response?.id) return;
    try {
      await deleteFindingFeedback(response.id, item.ruleRun.rule_id, item.finding.finding_id);
      setFindingFeedbackByKey((current) => ({ ...current, [item.key]: null }));
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '反馈取消失败');
    }
  }, [response?.id]);
  const updateSuggestionFeedback = useCallback(async (item: (typeof findings)[number], value: 'positive' | 'negative') => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!response?.id || !suggestion?.suggestion_id) return;
    try {
      const feedback = await saveSuggestionFeedback(response.id, suggestion.suggestion_id, { feedback_value: value });
      setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: feedback }));
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '反馈保存失败');
    }
  }, [response?.id, repairSuggestions.repairSuggestionByFindingKey]);
  const updateSuggestionReason = useCallback(async (item: (typeof findings)[number], reasonCode: string | null, reasonText: string | null) => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!response?.id || !suggestion?.suggestion_id) return;
    try {
      const feedback = await saveSuggestionFeedback(response.id, suggestion.suggestion_id, {
        feedback_value: 'negative', reason_code: reasonCode, reason_text: reasonText,
      });
      setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: feedback }));
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '反馈保存失败');
    }
  }, [response?.id, repairSuggestions.repairSuggestionByFindingKey]);
  const cancelSuggestionFeedback = useCallback(async (item: (typeof findings)[number]) => {
    const suggestion = repairSuggestions.repairSuggestionByFindingKey[item.key];
    if (!response?.id || !suggestion?.suggestion_id) return;
    try {
      await deleteSuggestionFeedback(response.id, suggestion.suggestion_id);
      setSuggestionFeedbackByFindingKey((current) => ({ ...current, [item.key]: null }));
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '反馈取消失败');
    }
  }, [response?.id, repairSuggestions.repairSuggestionByFindingKey]);

  function saveActiveJob(job: StoredPaperLintJob) {
    if (!user) return;
    localStorage.setItem(activeJobStorageKey(user.id), JSON.stringify(job));
    setActiveJobId(job.jobId);
  }

  function savePendingRequest(requestId: string, filename: string, selectedRuleIdsToSave: string[]) {
    if (!user) return;
    localStorage.setItem(activeJobStorageKey(user.id), JSON.stringify({
      jobId: null,
      requestId,
      filename,
      selectedRuleIds: selectedRuleIdsToSave,
    } satisfies StoredPaperLintJob));
  }

  function clearActiveJob() {
    if (user) localStorage.removeItem(activeJobStorageKey(user.id));
    setActiveJobId(null);
    requestIdRef.current = null;
  }

  async function showSavedReport(reportId: string, filename: string, sourceFile?: File, generation = runGenerationRef.current) {
    const nextReport = await fetchPaperLintReport(reportId);
    if (generation !== runGenerationRef.current) return;
    setResponse(nextReport);
    setRunError(null);
    setResultFile(sourceFile || {
      name: nextReport.source_filename || filename,
      url: `/api/normative/paper-lint/reports/${encodeURIComponent(reportId)}/pdf`,
    });
    clearActiveJob();
  }

  async function pollJob(jobId: string, filename: string, sourceFile?: File, generation = runGenerationRef.current) {
    const deadline = Date.now() + 25 * 60 * 1000;
    let disconnected = false;
    while (generation === runGenerationRef.current && Date.now() <= deadline) {
      try {
        const job = await fetchPaperLintJob(jobId);
        if (generation !== runGenerationRef.current) return;
        if (disconnected) {
          disconnected = false;
          setRunError(null);
        }
        if (job.progress) {
          setJobProgress({ completed: job.progress.completed_rule_ids?.length || 0, total: job.progress.total_rule_ids?.length || 0 });
          if (sourceFile && job.progress.rule_runs?.length) {
            setResponse((current) => current || partialPaperLintResponse(job.job_id, filename, job.progress?.rule_runs || []));
            setResultFile((current) => current || sourceFile);
          }
        }
        if (job.status === 'pending' || job.status === 'running') {
          await new Promise((resolve) => setTimeout(resolve, 300));
          continue;
        }
        if (job.status === 'cancelled') {
          clearActiveJob();
          setStopped(true);
          setResponse(null);
          setResultFile(null);
          setJobProgress(null);
          return;
        }
        if (job.status === 'failed') {
          clearActiveJob();
          throw new Error(job.error_message || '检测失败，请重试');
        }
        if (!job.report_id) {
          clearActiveJob();
          throw new Error('检测完成，但报告未保存，请重试');
        }
        await showSavedReport(job.report_id, filename, sourceFile, generation);
        return;
      } catch (error) {
        if (generation !== runGenerationRef.current) return;
        if (error instanceof Error && !/网络|连接|timeout|Network|ECONN/i.test(error.message)) throw error;
        disconnected = true;
        setRunError('连接中断，请重试获取检测状态');
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }
    if (generation !== runGenerationRef.current) return;
    throw new Error('检测任务等待超时，请稍后在历史报告中查看');
  }

  async function stopReview() {
    if (!activeJobId || stopping) return;
    let generation = runGenerationRef.current;
    const jobId = activeJobId;
    setStopping(true);
    setRunError(null);
    try {
      const job = await cancelPaperLintJob(jobId);
      if (generation !== runGenerationRef.current) return;
      if (job.status === 'failed') throw new Error(job.error_message || '检测失败，请重试');
      generation = ++runGenerationRef.current;
      if (job.status === 'completed' && job.report_id) {
        await showSavedReport(job.report_id, file?.name || '论文.pdf', file || undefined, generation);
      } else {
        clearActiveJob();
        setRunError(null);
        setStopped(true);
        setResponse(null);
        setResultFile(null);
        setJobProgress(null);
      }
      setRunning(false);
      setUploadPercent(null);
    } catch (error) {
      if (generation === runGenerationRef.current) setRunError(errorMessage(error, '停止检查失败，请重试'));
    } finally {
      setStopping(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    let stored: StoredPaperLintJob | null = null;
    try {
      stored = JSON.parse(localStorage.getItem(activeJobStorageKey(user.id)) || 'null') as StoredPaperLintJob | null;
    } catch {
      localStorage.removeItem(activeJobStorageKey(user.id));
    }
    if (!stored?.requestId || !stored.filename) return;
    requestIdRef.current = stored.requestId || null;
    if (!stored.jobId) {
      setSelectedRuleIds(stored.selectedRuleIds || []);
      setRunError('上次提交状态不明确，请重新选择同一文件后重试');
      return;
    }
    setActiveJobId(stored.jobId);
    setSelectedRuleIds(stored.selectedRuleIds || []);
    setRunning(true);
    const generation = ++runGenerationRef.current;
    void pollJob(stored.jobId, stored.filename, undefined, generation).catch((error) => {
      if (!cancelled && generation === runGenerationRef.current) setRunError(errorMessage(error, '检测任务恢复失败'));
    }).finally(() => {
      if (!cancelled && generation === runGenerationRef.current) setRunning(false);
    });
    return () => { cancelled = true; if (generation === runGenerationRef.current) runGenerationRef.current += 1; };
  }, [user?.id]);

  function chooseFile(nextFile: File | null) {
    setStopped(false);
    setRunError(null);
    setResponse(null);
    setResultFile(null);
    if (activeJobId) clearActiveJob();
    if (user && requestIdRef.current && !activeJobId) {
      try {
        const stored = JSON.parse(localStorage.getItem(activeJobStorageKey(user.id)) || 'null') as StoredPaperLintJob | null;
        if (!nextFile || (stored?.jobId === null && stored.filename !== nextFile.name)) clearActiveJob();
      } catch {
        clearActiveJob();
      }
    }
    if (!nextFile) {
      setFile(null);
      return;
    }
    try {
      validatePdf(nextFile);
      setFile(nextFile);
    } catch (error) {
      setFile(null);
      setRunError(errorMessage(error, 'PDF 文件无效'));
    }
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0] || null);
  }

  function toggleRule(ruleId: string) {
    setSelectedRuleIds((current) =>
      current.includes(ruleId) ? current.filter((id) => id !== ruleId) : [...current, ruleId],
    );
    setResponse(null);
    setResultFile(null);
  }

  function replaceSelectedRules(ruleIds: string[]) {
    setSelectedRuleIds(ruleIds);
    setResponse(null);
    setResultFile(null);
    setRunError(null);
  }

  async function runReview() {
    if (running || stopping) return;
    if (!file) {
      setRunError('请先选择 PDF 文件');
      return;
    }
    if (selectedRuleIds.length === 0) {
      setRunError('请至少选择一条审查规则');
      return;
    }
    if (selectedExternalRule && !externalConsent) {
      setRunError('运行 DeepSeek 语义规则前，请先确认论文相关文本允许发送至外部 API');
      return;
    }
    const generation = ++runGenerationRef.current;
    setRunning(true);
    setStopped(false);
    setJobProgress(null);
    setRunError(null);
    setResponse(null);
    setResultFile(null);
    const requestId = requestIdRef.current || newRequestId();
    requestIdRef.current = requestId;
    savePendingRequest(requestId, file.name, selectedRuleIds);
    try {
      setUploadPercent(0);
      const submitted = await runReviewPilotPaperLint(file, selectedRuleIds, externalConsent, requestId, setUploadPercent);
      setUploadPercent(null);
      let nextResponse: PaperLintRunResponse;
      if (isPaperLintJobResponse(submitted)) {
        saveActiveJob({ jobId: submitted.job_id, requestId, filename: file.name, selectedRuleIds });
        if (generation !== runGenerationRef.current) return;
        await pollJob(submitted.job_id, file.name, file, generation);
        return;
      } else {
        nextResponse = submitted;
      }
      if (generation !== runGenerationRef.current) return;
      setResponse(nextResponse);
      setResultFile(file);
      clearActiveJob();
    } catch (error) {
      if (generation === runGenerationRef.current) setRunError(errorMessage(error, '规则审查运行失败'));
    } finally {
      if (generation === runGenerationRef.current) {
        setUploadPercent(null);
        setRunning(false);
      }
    }
  }

  if (status === 'loading') return <LoadingState label="正在加载登录状态…" />;

  if (!user) {
    return (
      <Card>
        <h1 className="text-2xl font-black text-slate-900">{title}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后上传论文并运行规则审查。</p>
        <LinkButton className="mt-5" to="/auth">
          前往登录
        </LinkButton>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {isThirty ? (
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-950 via-blue-950 to-cyan-900 p-6 text-white shadow-xl sm:p-9">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-14 -top-24 size-72 rounded-full border border-white/10 bg-cyan-300/10 blur-2xl"
          />
          <div className="relative grid gap-7 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <span className="inline-flex rounded-full border border-cyan-200/30 bg-cyan-300/10 px-3 py-1 text-xs font-semibold tracking-wide text-cyan-100">
                论文规范专项检测
              </span>
              <h1 className="mt-5 text-3xl font-black tracking-tight sm:text-4xl">PDF 规则检测</h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-blue-100/85 sm:text-base">
                聚焦公式引用、文献引用与目录页码等可定位问题。上传论文后，自主选择已开放规则，逐项查看检测结果和 PDF
                原文位置。
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:min-w-72">
              <div className="rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-sm">
                <p className="text-3xl font-black">
                  {visibleRules.length}
                  <span className="ml-1 text-base font-medium">/ {visibleRules.length}</span>
                </p>
                <p className="mt-2 text-xs text-blue-100">可选规则</p>
              </div>
              <div className="rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-sm">
                <p className="text-3xl font-black">PDF</p>
                <p className="mt-2 text-xs text-blue-100">原文定位报告</p>
              </div>
            </div>
          </div>
        </section>
      ) : (
        <PageHeader title={title} description="上传 PDF 论文并选择检查项，生成可定位问题的检查报告。" />
      )}
      <ModuleTabs
        ariaLabel={`${title}功能导航`}
        items={[
          { label: '发起检测', to: isThirty ? '/thirty-rules-check' : '/normative-check', active: true },
          { label: '历史报告', to: isThirty ? '/thirty-rules-check/reports' : '/normative-reports', active: false },
        ]}
      />

      <section
        aria-label={isThirty ? '发起 PDF 规则检测' : '发起基础规则检测'}
        className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
      >
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-5">
          <div>
            <h2 className="text-lg font-bold text-slate-900">发起检查</h2>
            <p className="mt-1 text-sm text-slate-500">完成后自动保存至历史报告，可继续查看问题定位与修改建议。</p>
          </div>
          <span className="rounded-full bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700">
            PDF 论文检查
          </span>
        </div>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,.85fr)_minmax(440px,1.15fr)]">
          <Card title="1. 上传论文" description="仅支持 PDF，最大 50 MB。">
            <label
              className={`flex min-h-64 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition ${
                dragging
                  ? 'border-brand-500 bg-brand-50'
                  : 'border-slate-300 bg-slate-50 hover:border-brand-500 hover:bg-brand-50/50'
              }`}
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
            >
              <input
                className="sr-only"
                type="file"
                accept=".pdf,application/pdf"
                aria-label="上传待审查 PDF"
                disabled={running}
                onChange={(event) => chooseFile(event.target.files?.[0] || null)}
              />
              {file ? (
                <>
                  <FileText className="size-10 text-brand-500" />
                  <span className="mt-3 max-w-full truncate text-sm font-bold text-slate-900">{file.name}</span>
                  <span className="mt-1 text-xs text-slate-500">{fileSizeLabel(file.size)}</span>
                  <Button
                    className="mt-4"
                    size="sm"
                    variant="ghost"
                    onClick={(event) => {
                      event.preventDefault();
                      chooseFile(null);
                    }}
                  >
                    <X className="size-4" />
                    移除文件
                  </Button>
                </>
              ) : (
                <>
                  <span className="flex size-14 items-center justify-center rounded-full bg-brand-100 text-brand-600">
                    <Upload className="size-7" />
                  </span>
                  <span className="mt-4 text-sm font-bold text-slate-900">拖拽 PDF 到此处，或点击选择文件</span>
                  <span className="mt-2 text-xs text-slate-500">最大 50 MB；扫描版可能无法完成部分文字与版式规则</span>
                </>
              )}
            </label>
          </Card>

          <Card
            title="2. 选择审查规则"
            description={
              isThirty
                ? '请选择本次需要执行的规则。规则不可用时会显示原因并禁止提交。'
                : '基础检查默认启用；需要额外文本分析的检查项可按需选择。'
            }
            actions={
              catalog ? (
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      replaceSelectedRules(visibleRules.filter((rule) => rule.available).map((rule) => rule.rule_id))
                    }
                  >
                    全选可用
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => replaceSelectedRules([])}>
                    清空
                  </Button>
                </div>
              ) : undefined
            }
          >
            {catalogLoading ? <LoadingState label="正在读取检查项…" /> : null}
            {catalogError ? <ErrorState message={catalogError} onRetry={() => void loadCatalog()} /> : null}
            {catalog ? (
              <div className={`grid gap-3 md:grid-cols-2 ${isThirty ? '' : 'max-h-80 overflow-y-auto pr-1'}`}>
                {visibleRules.map((rule: PaperLintRule) => {
                  const checked = selectedRuleIds.includes(rule.rule_id);
                  return (
                    <label
                      key={rule.rule_id}
                      className={`flex gap-3 rounded-lg border p-3 transition ${
                        rule.available ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
                      } ${checked ? 'border-brand-500 bg-brand-50 shadow-sm' : 'border-slate-200 hover:border-slate-300'} ${isThirty ? 'min-h-28 rounded-xl bg-gradient-to-br from-white to-slate-50/70 p-4' : ''}`}
                    >
                      <input
                        className="mt-0.5 size-4 accent-brand-500"
                        type="checkbox"
                        checked={checked}
                        disabled={running || !rule.available}
                        onChange={() => toggleRule(rule.rule_id)}
                      />
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-900">
                          {rule.title}
                          {!rule.available ? (
                            <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] text-slate-600">
                              尚未配置
                            </span>
                          ) : null}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-slate-500">{rule.description}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            ) : null}
            {catalog && visibleRules.length === 0 ? (
              <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                当前页面暂无可用规则。
              </p>
            ) : null}
            {selectedExternalRule ? (
              <label className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <input
                  className="mt-0.5 size-4 accent-brand-500"
                  type="checkbox"
                  checked={externalConsent}
                  onChange={(event) => setExternalConsent(event.target.checked)}
                  disabled={running}
                />
                <span>
                  我确认本次论文相关文本允许发送至外部 API（校内 DeepSeek）进行语义检测。
                </span>
              </label>
            ) : null}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
              <p className="text-sm text-slate-600">
                已选择 <strong className="text-slate-900">{selectedRuleIds.length}</strong> 条规则
              </p>
              <div className="flex items-center gap-2">
              {running || stopping ? (
                <Button variant="danger" disabled={!activeJobId || stopping}
                  title={!activeJobId ? '上传完成后可停止检查' : undefined} onClick={() => void stopReview()}>
                  {stopping ? <LoaderCircle className="size-4 animate-spin" /> : <Square className="size-4" />}
                  {stopping ? '正在停止…' : '停止检查'}
                </Button>
              ) : null}
              <Button
                disabled={
                  !file ||
                  !catalog ||
                  selectedRuleIds.length === 0 ||
                  running ||
                  stopping ||
                  (selectedExternalRule && !externalConsent)
                }
                onClick={() => void runReview()}
              >
                {running ? <LoaderCircle className="size-4 animate-spin" /> : <Play className="size-4" />}
                {running ? uploadPercent !== null && uploadPercent < 100 ? '正在上传…' : '正在检查…' : '开始检查'}
              </Button>
              </div>
            </div>
          </Card>
        </div>
        <p className="mt-5 text-xs leading-5 text-slate-500">扫描版 PDF 可能无法完成部分文字与版式规则检查。</p>
      </section>

      {runError ? <ErrorState title="审查未完成" message={runError} onRetry={() => {
        if (stopping) return;
        if (!activeJobId) { void runReview(); return; }
        const generation = ++runGenerationRef.current;
        setRunning(true);
        setRunError(null);
        void pollJob(activeJobId, file?.name || '论文.pdf', file || undefined, generation)
          .catch((error) => { if (generation === runGenerationRef.current) setRunError(errorMessage(error, '检测任务恢复失败')); })
          .finally(() => { if (generation === runGenerationRef.current) setRunning(false); });
      }} /> : null}

      {stopped ? <Card><p className="text-sm text-slate-600" role="status">已停止检查，可以重新开始。</p></Card> : null}

      {running ? (
        <Card>
          <div className="flex items-center gap-4 py-5">
            <span className="flex size-11 items-center justify-center rounded-full bg-brand-100 text-brand-600">
              <LoaderCircle className="size-5 animate-spin" />
            </span>
            <div>
              <p className="font-bold text-slate-900">{uploadPercent !== null && uploadPercent < 100 ? `正在上传 PDF（${uploadPercent}%）` : jobProgress && jobProgress.total ? `正在检查规则（已完成 ${jobProgress.completed}/${jobProgress.total}）` : '正在进行本地检查'}</p>
              <p className="mt-1 text-sm text-slate-500">{uploadPercent !== null && uploadPercent < 100 ? '正在传输论文文件，上传完成后立即开始检测。' : selectedRuleIds.includes('typo_detection_check') ? '已完成的规则会先展示；正文错别字检测按段落处理，耗时可能较长，可随时停止。' : '已完成的规则会先展示，可随时停止检查。'}</p>
            </div>
          </div>
        </Card>
      ) : null}

      {response && resultFile ? (
        <>
          <Card
            title="审查结果"
            description={`${response.result.paper_title} · ${new Date(response.created_at).toLocaleString('zh-CN')}`}
            actions={
              <StatusBadge
                tone={
                  response.result.summary.finding_count
                    ? 'warning'
                    : response.result.summary.unsupported_rule_count + response.result.summary.error_rule_count
                      ? 'neutral'
                      : 'success'
                }
              >
                {compilerPublicationSummary(response.result) || (response.result.summary.finding_count
                  ? `发现 ${response.result.summary.finding_count} 项问题`
                  : response.result.summary.unsupported_rule_count + response.result.summary.error_rule_count
                    ? '部分规则无法判定'
                    : '未发现问题')}
              </StatusBadge>
            }
          >
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {[
                ['执行规则', response.result.summary.rule_count],
                ['完成规则', response.result.summary.completed_rule_count],
                ['发现问题的规则', response.result.summary.issue_rule_count],
                ['问题总数', response.result.summary.finding_count],
                [
                  '不适用/失败',
                  response.result.summary.unsupported_rule_count + response.result.summary.error_rule_count,
                ],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">{label}</p>
                  <p className="mt-1 text-2xl font-black text-slate-900">{value}</p>
                </div>
              ))}
            </div>
            <details className="mt-4 rounded-lg border border-slate-200">
              <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-slate-800">
                查看各规则执行状态
              </summary>
              <div className="grid gap-2 border-t border-slate-200 p-3 md:grid-cols-2">
                {response.result.rule_runs.map((run) => (
                  <div
                    key={run.rule_run_id}
                    className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <span className="block truncate text-sm text-slate-700">
                        {rulesById.get(run.rule_id)?.title || run.rule_id}
                      </span>
                      {run.message ? <p className="mt-1 text-xs text-slate-500">{run.message}</p> : null}
                    </div>
                    <StatusBadge tone={outcomeTones[run.outcome]}>{compilerPublicationLabel(run) || outcomeLabels[run.outcome]}</StatusBadge>
                  </div>
                ))}
              </div>
            </details>
          </Card>

          <div className="flex items-center gap-2">
            <FileCheck2 className="size-5 text-brand-600" />
            <h2 className="text-lg font-black text-slate-900">PDF 定位与问题联动</h2>
          </div>
          <PaperLintWorkspace
            file={resultFile}
            openPdfUrl={`/api/normative/paper-lint/reports/${encodeURIComponent(response.id)}/pdf`}
            findings={findings}
            rules={visibleRules}
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
        </>
      ) : null}
    </div>
  );
}

export default NormativeCheckPage;
