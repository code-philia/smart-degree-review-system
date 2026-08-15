import axios from 'axios';
import { FileCheck2, FileText, LoaderCircle, Play, Upload, X } from 'lucide-react';
import { useEffect, useMemo, useState, type DragEvent } from 'react';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  fetchReviewPilotPaperLintRules,
  runReviewPilotPaperLint,
  type PaperLintCatalogResponse,
  type PaperLintRunResponse,
  type PaperLintRule,
} from '../api/paperLint';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { flattenPaperLintFindings } from '../components/paperLint/model';
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

function errorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error)) {
    const message = error.response?.data?.message;
    if (typeof message === 'string' && message.trim()) return message;
    if (error.code === 'ECONNABORTED') return '规则审查运行超时，请减少规则后重试';
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

const outcomeLabels = {
  passed: '通过',
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

function NormativeCheckPage() {
  const { status, user } = useAuthSession();
  const [catalog, setCatalog] = useState<PaperLintCatalogResponse | null>(null);
  const [selectedRuleIds, setSelectedRuleIds] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [resultFile, setResultFile] = useState<File | null>(null);
  const [response, setResponse] = useState<PaperLintRunResponse | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [semanticConsent, setSemanticConsent] = useState(false);

  const loadCatalog = async () => {
    setCatalogLoading(true);
    setCatalogError(null);
    try {
      const nextCatalog = await fetchReviewPilotPaperLintRules();
      setCatalog(nextCatalog);
      setSelectedRuleIds(nextCatalog.rules.filter((rule) => rule.default_enabled).map((rule) => rule.rule_id));
      setSemanticConsent(false);
    } catch (error) {
      setCatalog(null);
      setCatalogError(errorMessage(error, '规则目录加载失败'));
    } finally {
      setCatalogLoading(false);
    }
  };

  useEffect(() => {
    if (user) void loadCatalog();
  }, [user?.id]);

  const rulesById = useMemo(() => new Map((catalog?.rules || []).map((rule) => [rule.rule_id, rule])), [catalog]);
  const selectedSemanticRules = useMemo(
    () =>
      (catalog?.rules || []).filter(
        (rule) => rule.execution_mode === 'semantic' && selectedRuleIds.includes(rule.rule_id),
      ),
    [catalog, selectedRuleIds],
  );
  const findings = useMemo(() => (response ? flattenPaperLintFindings(response.result) : []), [response]);

  function chooseFile(nextFile: File | null) {
    setRunError(null);
    setResponse(null);
    setResultFile(null);
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
    setSemanticConsent(false);
  }

  function replaceSelectedRules(ruleIds: string[]) {
    setSelectedRuleIds(ruleIds);
    setResponse(null);
    setResultFile(null);
    setRunError(null);
    setSemanticConsent(false);
  }

  async function runReview() {
    if (!file) {
      setRunError('请先选择 PDF 文件');
      return;
    }
    if (selectedRuleIds.length === 0) {
      setRunError('请至少选择一条审查规则');
      return;
    }
    if (selectedSemanticRules.length > 0 && !semanticConsent) {
      setRunError('请先确认论文相关文本允许发送至 DeepSeek 官方 API');
      return;
    }
    setRunning(true);
    setRunError(null);
    setResponse(null);
    setResultFile(null);
    try {
      const nextResponse = await runReviewPilotPaperLint(file, selectedRuleIds, semanticConsent);
      setResponse(nextResponse);
      setResultFile(file);
    } catch (error) {
      setRunError(errorMessage(error, '规则审查运行失败'));
    } finally {
      setRunning(false);
    }
  }

  if (status === 'loading') return <LoadingState label="正在加载登录状态…" />;

  if (!user) {
    return (
      <Card>
        <h1 className="text-2xl font-black text-slate-900">规范性检测</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后上传论文并运行规则审查。</p>
        <LinkButton className="mt-5" to="/auth">
          前往登录
        </LinkButton>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="规范性检测"
        description="上传 PDF 论文并选择检查项，生成可定位问题的检查报告。"
        breadcrumbs={[{ label: '检测与生成', to: '/' }, { label: '规范性检测' }]}
      />
      <ModuleTabs
        ariaLabel="规范性检测功能导航"
        items={[
          { label: '发起检测', to: '/normative-check', active: true },
          { label: '历史报告', to: '/normative-reports', active: false },
        ]}
      />

      <section
        aria-label="发起规范性检测"
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
            description="基础检查默认启用；需要额外文本分析的检查项可按需选择。"
            actions={
              catalog ? (
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      replaceSelectedRules(catalog.rules.filter((rule) => rule.available).map((rule) => rule.rule_id))
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
              <div className="grid max-h-80 gap-2 overflow-y-auto pr-1 md:grid-cols-2">
                {catalog.rules.map((rule: PaperLintRule) => {
                  const checked = selectedRuleIds.includes(rule.rule_id);
                  return (
                    <label
                      key={rule.rule_id}
                      className={`flex gap-3 rounded-lg border p-3 transition ${
                        rule.available ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
                      } ${checked ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:border-slate-300'}`}
                    >
                      <input
                        className="mt-0.5 size-4 accent-brand-500"
                        type="checkbox"
                        checked={checked}
                        disabled={!rule.available}
                        onChange={() => toggleRule(rule.rule_id)}
                      />
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-2 text-sm font-bold text-slate-900">
                          {rule.title}
                          {rule.execution_mode === 'semantic' ? (
                            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] text-violet-700">
                              扩展分析
                            </span>
                          ) : null}
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
            {selectedSemanticRules.length > 0 ? (
              <div
                className="mt-4 rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs leading-5 text-violet-900"
                role="note"
              >
                <p>
                  已选择 {selectedSemanticRules.length} 条扩展分析检查项。系统会将相关摘要、论点和候选论据文本发送到
                  DeepSeek 官方 API；请勿上传不允许外发的论文，结果必须由人工复核。
                </p>
                <label className="mt-2 flex cursor-pointer items-start gap-2 font-semibold">
                  <input
                    className="mt-0.5 size-4 accent-violet-600"
                    type="checkbox"
                    checked={semanticConsent}
                    onChange={(event) => setSemanticConsent(event.target.checked)}
                  />
                  <span>我确认该论文相关文本允许发送至 DeepSeek 官方 API</span>
                </label>
              </div>
            ) : null}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
              <p className="text-sm text-slate-600">
                已选择 <strong className="text-slate-900">{selectedRuleIds.length}</strong> 条规则
              </p>
              <Button
                disabled={
                  !file ||
                  !catalog ||
                  selectedRuleIds.length === 0 ||
                  running ||
                  (selectedSemanticRules.length > 0 && !semanticConsent)
                }
                onClick={() => void runReview()}
              >
                {running ? <LoaderCircle className="size-4 animate-spin" /> : <Play className="size-4" />}
                {running ? '正在检查…' : '开始检查'}
              </Button>
            </div>
          </Card>
        </div>
        <p className="mt-5 text-xs leading-5 text-slate-500">扫描版 PDF 可能无法完成部分文字与版式规则检查。</p>
      </section>

      {runError ? <ErrorState title="审查未完成" message={runError} /> : null}

      {running ? (
        <Card>
          <div className="flex items-center gap-4 py-5">
            <span className="flex size-11 items-center justify-center rounded-full bg-brand-100 text-brand-600">
              <LoaderCircle className="size-5 animate-spin" />
            </span>
            <div>
              <p className="font-bold text-slate-900">正在解析论文并逐项检查</p>
              <p className="mt-1 text-sm text-slate-500">扩展分析检查项可能需要更长时间；完成后将直接展示真实结果。</p>
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
              <StatusBadge tone={response.result.summary.finding_count ? 'warning' : 'success'}>
                {response.result.summary.finding_count
                  ? `发现 ${response.result.summary.finding_count} 项问题`
                  : '未发现问题'}
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
                    <span className="truncate text-sm text-slate-700">
                      {rulesById.get(run.rule_id)?.title || run.rule_id}
                    </span>
                    <StatusBadge tone={outcomeTones[run.outcome]}>{outcomeLabels[run.outcome]}</StatusBadge>
                  </div>
                ))}
              </div>
            </details>
          </Card>

          <div className="flex items-center gap-2">
            <FileCheck2 className="size-5 text-brand-600" />
            <h2 className="text-lg font-black text-slate-900">PDF 定位与问题联动</h2>
          </div>
          <PaperLintWorkspace file={resultFile} findings={findings} rules={catalog?.rules || []} />
        </>
      ) : null}
    </div>
  );
}

export default NormativeCheckPage;
