import {
  Archive,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FileSearch,
  FolderOpen,
  Layers3,
  LoaderCircle,
  Play,
  Search,
  Trash2,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  fetchArchiveCatalog,
  fetchArchiveDocuments,
  fetchArchiveJob,
  fetchArchiveJobs,
  deleteArchiveJob,
  startArchiveJob,
  type ArchiveCatalog,
  type ArchiveDocumentPage,
  type ArchiveJob,
} from '../api/archiveScans';
import { Button, EmptyState, ErrorState, LoadingState, ModuleTabs, PageHeader } from '../components/ui';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '../components/shadcn/alert-dialog';

const adminRoles = new Set(['COLLEGE_ADMIN', 'SCHOOL_ADMIN']);
function message(error: unknown) {
  return error instanceof Error ? error.message : '请求失败，请稍后重试';
}
function jobLabel(job: ArchiveJob) {
  return `${job.selected_rule_ids.map((id) => id.replace('sjtu_rule_', '')).join('、')} 号规则`;
}

export default function ArchiveScanPage() {
  const { status, user } = useAuthSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [catalog, setCatalog] = useState<ArchiveCatalog | null>(null);
  const [jobs, setJobs] = useState<ArchiveJob[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [activeJob, setActiveJob] = useState<ArchiveJob | null>(null);
  const [documents, setDocuments] = useState<ArchiveDocumentPage | null>(null);
  const [ruleFilter, setRuleFilter] = useState('');
  const [outcomeFilter, setOutcomeFilter] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const canAccess = !!user && adminRoles.has(user.role);
  const currentJobId = searchParams.get('job');
  const refreshJobs = useCallback(async () => {
    const { jobs: next } = await fetchArchiveJobs();
    setJobs(next);
    return next;
  }, []);
  useEffect(() => {
    if (!canAccess) return;
    let cancelled = false;
    Promise.all([fetchArchiveCatalog(), refreshJobs()])
      .then(([nextCatalog, nextJobs]) => {
        if (cancelled) return;
        setCatalog(nextCatalog);
        if (!currentJobId && nextJobs[0]) setSearchParams({ job: nextJobs[0].id }, { replace: true });
      })
      .catch((cause) => {
        if (!cancelled) setError(message(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canAccess]);
  useEffect(() => {
    if (!canAccess || !currentJobId) {
      setActiveJob(null);
      setDocuments(null);
      return;
    }
    let cancelled = false;
    const refresh = async () => {
      try {
        const [{ job }, rows] = await Promise.all([
          fetchArchiveJob(currentJobId),
          fetchArchiveDocuments(currentJobId, {
            rule_id: ruleFilter || undefined,
            outcome: outcomeFilter || undefined,
            q: query || undefined,
            page,
          }),
        ]);
        if (!cancelled) {
          setActiveJob(job);
          setDocuments(rows);
        }
      } catch (cause) {
        if (!cancelled) setError(message(cause));
      }
    };
    void refresh();
    const timer =
      activeJob?.status === 'running'
        ? window.setInterval(() => {
            void refresh();
          }, 3000)
        : undefined;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [canAccess, currentJobId, ruleFilter, outcomeFilter, query, page, refreshJobs, activeJob?.status]);
  const running = jobs.some((job) => job.status === 'running');
  useEffect(() => {
    if (!canAccess || !running) return;
    const timer = window.setInterval(() => {
      void refreshJobs();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [canAccess, running, refreshJobs]);
  const selectedRules = useMemo(
    () => catalog?.rules.filter((rule) => selected.includes(rule.rule_id)) || [],
    [catalog, selected],
  );
  async function launch(ids: string[]) {
    setBusy(true);
    setError(null);
    try {
      const { job } = await startArchiveJob(ids);
      setSelected([]);
      setRuleFilter('');
      setOutcomeFilter('');
      setQuery('');
      setPage(1);
      await refreshJobs();
      setSearchParams({ job: job.id });
      setActiveJob(job);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  }
  async function removeJob(id: string) {
    setDeletingId(id);
    setError(null);
    try {
      await deleteArchiveJob(id);
      const remaining = await refreshJobs();
      if (currentJobId === id) {
        setRuleFilter('');
        setOutcomeFilter('');
        setQuery('');
        setPage(1);
        setActiveJob(null);
        setDocuments(null);
        setSearchParams(remaining[0] ? { job: remaining[0].id } : {}, { replace: true });
      }
    } catch (cause) {
      setError(message(cause));
    } finally {
      setDeletingId(null);
    }
  }
  if (status === 'loading') return <LoadingState label="正在验证访问权限…" />;
  if (!canAccess) return <ErrorState title="无权访问归档批量扫描" message="请使用学院管理员或学校管理员账号登录。" />;
  return (
    <div className="space-y-6">
      <PageHeader title="30条规则检测" description="单篇检测与归档论文批量扫描" />
      <ModuleTabs
        ariaLabel="30条规则检测功能导航"
        items={[
          { label: '发起检测', to: '/thirty-rules-check', active: false },
          { label: '历史报告', to: '/thirty-rules-check/reports', active: false },
          { label: '扫描479篇归档论文', to: '/thirty-rules-check/archive', active: true },
        ]}
      />
      <section className="relative overflow-hidden rounded-[28px] bg-gradient-to-br from-slate-950 via-blue-950 to-cyan-900 p-6 text-white shadow-xl sm:p-9">
        <div className="absolute -right-20 -top-32 size-80 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs font-bold text-cyan-100">
              <Archive className="size-3.5" /> 归档论文专项扫描
            </span>
            <h1 className="mt-5 text-3xl font-black tracking-tight sm:text-4xl">
              {catalog?.paper_count ?? '479'} 篇归档论文
            </h1>
            <p className="mt-3 max-w-2xl leading-7 text-blue-100">
              选择一条或多条已开放规则，扫描全部归档论文。任务逐篇保存结果，可查看问题所在的 PDF 页面与原文位置。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-white/15 bg-white/10 px-5 py-4 backdrop-blur-sm">
              <p className="text-3xl font-black">4</p>
              <p className="mt-1 text-xs text-blue-100">已开放规则</p>
            </div>
            <div className="rounded-2xl border border-white/15 bg-white/10 px-5 py-4 backdrop-blur-sm">
              <p className="text-3xl font-black">{jobs.length}</p>
              <p className="mt-1 text-xs text-blue-100">已保存任务</p>
            </div>
          </div>
        </div>
      </section>
      {error && <ErrorState message={error} />}
      {loading ? (
        <LoadingState label="正在加载归档扫描信息…" />
      ) : (
        <>
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-black text-slate-900">选择扫描规则</h2>
                <p className="mt-1 text-sm text-slate-500">每张卡片可单独运行，也可以勾选后一次运行多条规则。</p>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">
                已选择 {selected.length} 条
              </span>
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-2">
              {catalog?.rules.map((rule) => (
                <article
                  key={rule.rule_id}
                  className={`rounded-2xl border p-5 transition ${selected.includes(rule.rule_id) ? 'border-blue-400 bg-blue-50/60 ring-2 ring-blue-100' : 'border-slate-200 bg-slate-50/40 hover:border-blue-200'}`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      className="mt-1 size-4 accent-blue-600"
                      type="checkbox"
                      aria-label={`选择规则 ${rule.rule_id.replace('sjtu_rule_', '')}`}
                      checked={selected.includes(rule.rule_id)}
                      onChange={() =>
                        setSelected((current) =>
                          current.includes(rule.rule_id)
                            ? current.filter((id) => id !== rule.rule_id)
                            : [...current, rule.rule_id],
                        )
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-black text-slate-900">{rule.title}</p>
                      <p className="mt-2 text-sm leading-6 text-slate-500">{rule.description}</p>
                    </div>
                  </div>
                  <div className="mt-5 flex justify-end">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={running || busy}
                      aria-label={`仅运行规则 ${rule.rule_id.replace('sjtu_rule_', '')}`}
                      onClick={() => void launch([rule.rule_id])}
                    >
                      <Play className="mr-1 size-3.5" />
                      单独运行
                    </Button>
                  </div>
                </article>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3">
              <p className="text-sm text-slate-600">
                {selectedRules.length
                  ? `本次将以 ${selectedRules.map((rule) => rule.title).join('、')} 扫描全部论文`
                  : '勾选规则后开始批量扫描'}
              </p>
              <Button disabled={!selected.length || busy || running} onClick={() => void launch(selected)}>
                {busy ? <LoaderCircle className="mr-2 size-4 animate-spin" /> : <Play className="mr-2 size-4" />}
                扫描全部归档论文
              </Button>
            </div>
            {running && <p className="mt-3 text-xs text-amber-700">已有扫描任务正在运行，完成后可发起下一次。</p>}
          </section>
          <section className="grid gap-5 xl:grid-cols-[minmax(260px,.34fr)_minmax(0,1fr)]">
            <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="flex items-center gap-2 text-lg font-black text-slate-900">
                <Clock3 className="size-5 text-blue-600" /> 已保存任务
              </h2>
              <p className="mt-1 text-xs text-slate-500">全部扫描记录</p>
              <div className="mt-4 max-h-[520px] space-y-2 overflow-y-auto">
                {jobs.length ? (
                  jobs.map((job) => (
                    <div
                      key={job.id}
                      className={`flex items-center rounded-xl border transition ${currentJobId === job.id ? 'border-blue-300 bg-blue-50' : 'border-slate-200 hover:bg-slate-50'}`}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setRuleFilter('');
                          setOutcomeFilter('');
                          setQuery('');
                          setPage(1);
                          setActiveJob(null);
                          setDocuments(null);
                          setSearchParams({ job: job.id });
                        }}
                        className="min-w-0 flex-1 p-3 text-left"
                      >
                        <span className="flex items-center justify-between gap-2 text-sm font-bold text-slate-900">
                          <span>{jobLabel(job)}</span>
                          {job.status === 'running' ? (
                            <LoaderCircle className="size-4 animate-spin text-blue-600" />
                          ) : (
                            <CheckCircle2 className="size-4 text-emerald-600" />
                          )}
                        </span>
                        <span className="mt-1 block text-xs text-slate-500">
                          {new Date(job.created_at).toLocaleString('zh-CN')} · {job.completed_count + job.failed_count}/
                          {job.total_count} 篇
                        </span>
                      </button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <button
                            type="button"
                            aria-label={`删除任务 ${job.id}`}
                            title={job.status === 'running' ? '扫描中不可删除' : '删除任务'}
                            disabled={job.status === 'running' || deletingId !== null}
                            className="mr-2 inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {deletingId === job.id ? (
                              <LoaderCircle className="size-4 animate-spin" />
                            ) : (
                              <Trash2 className="size-4" />
                            )}
                          </button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>删除这次扫描任务？</AlertDialogTitle>
                            <AlertDialogDescription>
                              删除后无法恢复。该任务的 {job.total_count} 篇检测结果会一起删除，归档 PDF 文件会保留。
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>取消</AlertDialogCancel>
                            <AlertDialogAction
                              className="bg-red-600 text-white hover:bg-red-700"
                              onClick={() => void removeJob(job.id)}
                            >
                              确认删除
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  ))
                ) : (
                  <EmptyState title="尚无扫描任务" description="选择规则后开始第一次扫描。" />
                )}
              </div>
            </aside>
            <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              {activeJob ? (
                <>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="text-xl font-black text-slate-900">任务结果</h2>
                      <p className="mt-1 text-sm text-slate-500">
                        {jobLabel(activeJob)} · 创建于 {new Date(activeJob.created_at).toLocaleString('zh-CN')}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-bold ${activeJob.status === 'running' ? 'bg-blue-50 text-blue-700' : activeJob.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}
                    >
                      {activeJob.status === 'running'
                        ? '扫描中'
                        : activeJob.status === 'failed'
                          ? '任务中断'
                          : '已完成'}
                    </span>
                  </div>
                  <div className="mt-5 grid gap-3 sm:grid-cols-5">
                    {[
                      ['总论文', activeJob.total_count, FolderOpen],
                      ['已完成', activeJob.completed_count, CheckCircle2],
                      ['失败', activeJob.failed_count, CircleAlert],
                      ['无法判定', activeJob.inconclusive_count, CircleAlert],
                      ['发现问题', activeJob.finding_count, FileSearch],
                    ].map(([label, value, Icon]) => {
                      const Glyph = Icon as typeof FolderOpen;
                      return (
                        <div key={label as string} className="rounded-xl bg-slate-50 p-4">
                          <Glyph className="size-5 text-blue-600" />
                          <p className="mt-2 text-2xl font-black text-slate-900">{value as number}</p>
                          <p className="text-xs text-slate-500">{label as string}</p>
                        </div>
                      );
                    })}
                  </div>
                  <div
                    className="mt-5 h-2 overflow-hidden rounded-full bg-slate-100"
                    role="progressbar"
                    aria-valuenow={activeJob.completed_count + activeJob.failed_count}
                    aria-valuemax={activeJob.total_count}
                  >
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
                      style={{
                        width: `${Math.round((100 * (activeJob.completed_count + activeJob.failed_count)) / Math.max(1, activeJob.total_count))}%`,
                      }}
                    />
                  </div>
                  <div className="mt-5 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
                    <label className="relative">
                      <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-slate-400" />
                      <input
                        className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm"
                        placeholder="搜索论文名称"
                        aria-label="搜索论文名称"
                        value={query}
                        onChange={(event) => {
                          setQuery(event.target.value);
                          setPage(1);
                        }}
                      />
                    </label>
                    <select
                      aria-label="按规则筛选"
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                      value={ruleFilter}
                      onChange={(event) => {
                        setRuleFilter(event.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">全部规则</option>
                      {catalog?.rules
                        .filter((rule) => activeJob.selected_rule_ids.includes(rule.rule_id))
                        .map((rule) => (
                          <option value={rule.rule_id} key={rule.rule_id}>
                            {rule.title}
                          </option>
                        ))}
                    </select>
                    <select
                      aria-label="按结果筛选"
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
                      value={outcomeFilter}
                      onChange={(event) => {
                        setOutcomeFilter(event.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">全部结果</option>
                      <option value="issues_found">发现问题</option>
                      <option value="passed">通过</option>
                      <option value="inconclusive">无法判定</option>
                      <option value="failed">检测失败</option>
                    </select>
                  </div>
                  <div className="mt-4 divide-y divide-slate-100">
                    {documents?.items.map((doc) => (
                      <Link
                        key={doc.id}
                        to={`/thirty-rules-check/archive/jobs/${activeJob.id}/documents/${doc.id}`}
                        className="flex items-center gap-3 py-3 transition hover:bg-slate-50"
                      >
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                          <FileSearch className="size-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-slate-900">{doc.filename}</span>
                          <span className="block truncate text-xs text-slate-500">{doc.relative_path}</span>
                        </span>
                        <span
                          className={`shrink-0 text-xs font-bold ${doc.finding_count ? 'text-amber-700' : doc.status === 'failed' ? 'text-red-600' : 'text-slate-500'}`}
                        >
                          {doc.status === 'failed'
                            ? '检测失败'
                            : doc.status === 'pending'
                              ? '等待中'
                              : doc.status === 'running'
                                ? '检测中'
                                : doc.finding_count
                                  ? `${doc.finding_count} 处问题`
                                  : Object.values(doc.rule_outcomes).includes('inconclusive')
                                    ? '无法判定'
                                    : Object.values(doc.rule_outcomes).includes('issues_found')
                                      ? '发现问题'
                                      : Object.values(doc.rule_outcomes).every((outcome) => outcome === 'passed')
                                        ? '通过'
                                        : '未检测'}
                        </span>
                        <ArrowRight className="size-4 shrink-0 text-slate-400" />
                      </Link>
                    ))}
                  </div>
                  {documents && !documents.items.length && (
                    <p className="py-8 text-center text-sm text-slate-500">当前筛选下没有论文</p>
                  )}
                  {documents && documents.total > documents.page_size && (
                    <div className="mt-4 flex items-center justify-center gap-4 text-sm">
                      <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                        上一页
                      </Button>
                      <span>
                        {page} / {Math.ceil(documents.total / documents.page_size)}
                      </span>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={page >= Math.ceil(documents.total / documents.page_size)}
                        onClick={() => setPage(page + 1)}
                      >
                        下一页
                      </Button>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex min-h-64 flex-col items-center justify-center text-center text-slate-500">
                  <Layers3 className="size-10 text-blue-300" />
                  <h2 className="mt-3 text-lg font-bold text-slate-900">选择任务查看结果</h2>
                  <p className="mt-1 text-sm">每次扫描都会保留进度和逐篇结果。</p>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
