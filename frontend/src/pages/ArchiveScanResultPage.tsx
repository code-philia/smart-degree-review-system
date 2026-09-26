import { ArrowLeft, CircleAlert, ExternalLink, FileSearch, MapPin } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  archivePdfUrl,
  fetchArchiveCatalog,
  fetchArchiveDocument,
  type ArchiveCatalog,
  type ArchiveDocument,
} from '../api/archiveScans';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { flattenPaperLintFindings } from '../components/paperLint/model';
import { ErrorState, LoadingState, PageHeader } from '../components/ui';

const outcomeLabel: Record<string, string> = {
  passed: '通过',
  issues_found: '发现问题',
  inconclusive: '无法判定',
  not_applicable: '不适用',
};
export default function ArchiveScanResultPage() {
  const { jobId, documentId } = useParams();
  const { status, user } = useAuthSession();
  const [document, setDocument] = useState<ArchiveDocument | null>(null);
  const [catalog, setCatalog] = useState<ArchiveCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const allowed = user?.role === 'SCHOOL_ADMIN' || user?.role === 'COLLEGE_ADMIN';
  useEffect(() => {
    if (!allowed || !jobId || !documentId) return;
    let cancelled = false;
    Promise.all([fetchArchiveDocument(jobId, documentId), fetchArchiveCatalog()])
      .then(([data, nextCatalog]) => {
        if (!cancelled) {
          setDocument(data.document);
          setCatalog(nextCatalog);
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : '检测结果加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [allowed, jobId, documentId]);
  const inconclusive = document?.result?.rule_runs.some((run) => run.outcome === 'inconclusive') || false;
  const findings = useMemo(() => (document?.result ? flattenPaperLintFindings(document.result) : []), [document]);
  if (status === 'loading') return <LoadingState label="正在验证权限…" />;
  if (!allowed) return <ErrorState title="无权查看归档论文" message="请使用学院管理员或学校管理员账号登录。" />;
  if (error) return <ErrorState title="检测结果暂不可用" message={error} />;
  if (!document || !catalog) return <LoadingState label="正在加载论文检测结果…" />;
  const back = `/thirty-rules-check/archive?job=${jobId}`;
  return (
    <div className="space-y-6">
      <PageHeader
        title={document.filename}
        description={document.relative_path}
        breadcrumbs={[
          { label: '工作台', to: '/' },
          { label: '30条规则检测', to: '/thirty-rules-check' },
          { label: '扫描479篇归档论文', to: back },
          { label: '论文结果' },
        ]}
        actions={
          <>
            <a
              href={archivePdfUrl(jobId!, documentId!)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-blue-700"
            >
              <ExternalLink className="size-4" />
              在浏览器中打开完整 PDF
            </a>
            <Link to={back} className="inline-flex items-center gap-2 text-sm font-bold text-blue-700 hover:underline">
              <ArrowLeft className="size-4" />
              返回任务结果
            </Link>
          </>
        }
      />
      {document.status === 'failed' ? (
        <div className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800">
          <CircleAlert className="size-5 shrink-0" />
          <div>
            <h2 className="font-bold">这篇论文检测失败</h2>
            <p className="mt-1 text-sm">{document.error_message || '请检查论文 PDF 文件。'}</p>
          </div>
        </div>
      ) : null}
      {document.status === 'pending' || document.status === 'running' ? (
        <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5 text-sm text-blue-800">
          这篇论文尚未完成扫描，请稍后从任务列表重新打开。
        </div>
      ) : null}
      {document.result ? (
        <>
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-blue-600">论文扫描报告</p>
                <h2 className="mt-1 text-xl font-black text-slate-900">检测结论</h2>
                <p className="mt-1 text-sm text-slate-500">结果由规则生成，建议对照原文核查。</p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-sm font-black ${findings.length ? 'bg-amber-50 text-amber-700' : inconclusive ? 'bg-slate-100 text-slate-700' : 'bg-emerald-50 text-emerald-700'}`}
              >
                {findings.length ? `${findings.length} 处问题` : inconclusive ? '部分规则无法判定' : '未发现问题'}
              </span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {document.result.rule_runs.map((run) => (
                <div key={run.rule_id} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm font-bold text-slate-900">
                    {catalog.rules.find((rule) => rule.rule_id === run.rule_id)?.title || run.rule_id}
                  </p>
                  <p
                    className={`mt-2 text-sm font-semibold ${run.outcome === 'issues_found' ? 'text-amber-700' : run.outcome === 'passed' ? 'text-emerald-700' : 'text-slate-600'}`}
                  >
                    {outcomeLabel[run.outcome] || '无法判定'} · {run.findings.length} 处
                  </p>
                  {run.message && <p className="mt-1 text-xs text-slate-500">{run.message}</p>}
                </div>
              ))}
            </div>
          </section>
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <MapPin className="size-4 text-blue-600" />
            点击右侧问题，左侧 PDF 将定位到相应页面和区域。
          </div>
          <PaperLintWorkspace
            file={{ name: document.filename, url: archivePdfUrl(jobId!, documentId!) }}
            findings={findings}
            rules={catalog.rules}
          />
        </>
      ) : (
        <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-6 text-slate-500">
          <FileSearch className="size-5" />
          暂无检测报告
        </div>
      )}
    </div>
  );
}
