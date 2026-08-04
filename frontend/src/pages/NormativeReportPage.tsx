import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  downloadNormativeReportJson,
  fetchNormativeDetectionHistory,
  fetchNormativeDetectionReport,
  type DetectionTaskResponse,
  type NormativeIssue,
} from '../api/normativeRules';

type ActiveIssue = {
  issue: NormativeIssue;
  index: number;
};

function NormativeReportPage() {
  const { reportId } = useParams();
  const { status, user } = useAuthSession();
  const [history, setHistory] = useState<DetectionTaskResponse[]>([]);
  const [report, setReport] = useState<DetectionTaskResponse | null>(null);
  const [activeIssue, setActiveIssue] = useState<ActiveIssue | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const lineRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const lines = useMemo(() => (report?.original_text || '').split('\n'), [report]);

  useEffect(() => {
    if (status !== 'authenticated' || !user) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);

    const request = reportId ? fetchNormativeDetectionReport(reportId) : fetchNormativeDetectionHistory();
    request
      .then((response) => {
        if (cancelled) {
          return;
        }
        if (Array.isArray(response)) {
          setHistory(response);
          setReport(null);
        } else {
          setReport(response);
          setHistory([]);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '检测报告加载失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reportId, status, user]);

  function handleIssueClick(issue: NormativeIssue, index: number) {
    setActiveIssue({ issue, index });
    lineRefs.current[issue.line]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  async function handleDownloadJson(taskId: string) {
    const blob = await downloadNormativeReportJson(taskId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `normative-report-${taskId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (status === 'loading') {
    return <main className="px-6 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">历史检测记录</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后查看本人检测历史和报告。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  if (reportId) {
    return (
      <main className="min-h-screen bg-[#F5FAFF] px-6 py-10">
        <section className="mx-auto max-w-7xl">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <Link className="text-sm font-semibold text-[#1F3760]" to="/normative-reports">返回历史检测记录</Link>
              <h1 className="mt-2 text-3xl font-black text-[#1F3760]">检测报告</h1>
            </div>
            <div className="flex gap-3">
              <button className="rounded-lg bg-[#1F3760] px-4 py-2 text-sm font-bold text-white" type="button" disabled={!report} onClick={() => report && handleDownloadJson(report.id)}>
                下载 UTF-8 JSON
              </button>
              <button className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-800" type="button" onClick={() => window.print()}>
                浏览器打印
              </button>
            </div>
          </div>

          {loading ? <p className="mt-6 text-sm font-semibold text-slate-500">正在加载报告…</p> : null}
          {errorMessage ? <p className="mt-6 text-sm font-semibold text-red-600">{errorMessage}</p> : null}

          {report ? (
            <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
              <section className="max-h-[720px] overflow-auto rounded-2xl border border-[#E1E7EF] bg-white font-mono text-sm leading-7 text-slate-800">
                {lines.map((line, index) => {
                  const lineNumber = index + 1;
                  const isActive = activeIssue?.issue.line === lineNumber;
                  return (
                    <div key={lineNumber} ref={(element) => { lineRefs.current[lineNumber] = element; }} className={`grid grid-cols-[64px_minmax(0,1fr)] border-b border-slate-100 ${isActive ? 'bg-yellow-100' : ''}`}>
                      <span className="select-none bg-slate-50 px-3 text-right text-slate-400">{lineNumber}</span>
                      <span className="whitespace-pre-wrap px-4">{line || ' '}</span>
                    </div>
                  );
                })}
              </section>

              <aside className="rounded-2xl border border-[#E1E7EF] bg-white p-5 shadow-sm">
                <h2 className="text-xl font-black text-[#1F3760]">问题列表</h2>
                <div className="mt-4 space-y-3">
                  {report.issues.map((issue, index) => (
                    <button key={`${issue.rule_id}-${index}`} aria-label={`${issue.severity} 第 ${issue.line} 行，第 ${issue.column} 列`} className={`w-full rounded-xl border p-4 text-left text-sm ${activeIssue?.index === index ? 'border-[#D62020] bg-red-50' : 'border-slate-200 bg-white'}`} type="button" onClick={() => handleIssueClick(issue, index)}>
                      <span className="font-black text-[#D62020]">{issue.severity}</span>
                      <span className="ml-2 text-slate-500">第 {issue.line} 行，第 {issue.column} 列</span>
                      <p className="mt-2 font-semibold text-slate-900">{issue.message}</p>
                      <p className="mt-1 text-slate-600">{issue.excerpt}</p>
                    </button>
                  ))}
                </div>
              </aside>
            </div>
          ) : null}
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F5FAFF] px-6 py-10">
      <section className="mx-auto max-w-7xl">
        <h1 className="text-3xl font-black text-[#1F3760]">历史检测记录</h1>
        {loading ? <p className="mt-6 text-sm font-semibold text-slate-500">正在加载历史记录…</p> : null}
        {errorMessage ? <p className="mt-6 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
        {!loading && !errorMessage && history.length === 0 ? <p className="mt-6 rounded-2xl border border-dashed border-blue-200 bg-white p-6 text-sm text-slate-600">暂无检测记录。</p> : null}
        {history.length > 0 ? (
          <div className="mt-6 overflow-hidden rounded-2xl border border-[#E1E7EF] bg-white shadow-sm">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-[#1F3760] text-white">
                <tr>
                  <th className="px-6 py-4">文档名称</th>
                  <th className="px-6 py-4">问题总数</th>
                  <th className="px-6 py-4">严重/一般/轻微</th>
                  <th className="px-6 py-4">检测时间</th>
                  <th className="px-6 py-4">操作</th>
                </tr>
              </thead>
              <tbody>
                {history.map((record, index) => (
                  <tr key={record.id} className={index % 2 === 0 ? 'bg-white' : 'bg-[#F5F9FC]'}>
                    <td className="px-6 py-6 font-bold text-slate-900">📄 {record.source_filename || '粘贴文本检测'}</td>
                    <td className="px-6 py-6 font-black text-[#D62020]">{record.issues.length}</td>
                    <td className="px-6 py-6 text-slate-700">{record.severity_counts.high || 0} / {record.severity_counts.medium || 0} / {record.severity_counts.low || 0}</td>
                    <td className="px-6 py-6 text-slate-700">{record.created_at}</td>
                    <td className="px-6 py-6">
                      <div className="flex flex-wrap gap-2">
                        <button className="rounded-lg bg-[#1F3760] px-3 py-2 font-bold text-white" type="button" onClick={() => handleDownloadJson(record.id)}>报告下载</button>
                        <Link className="rounded-lg bg-[#1F6F58] px-3 py-2 font-bold text-white" to={`/normative-reports/${record.id}`}>报告预览</Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}

export default NormativeReportPage;
