import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { fetchPaperLintReports, type PaperLintReportListItem } from '../api/paperLint';
import {
  downloadNormativeReportJson,
  fetchNormativeDetectionHistory,
  fetchNormativeDetectionReport,
  type DetectionTaskResponse,
  type NormativeIssue,
} from '../api/normativeRules';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LinkButton,
  LoadingState,
  ModuleTabs,
  PageHeader,
} from '../components/ui';

type ActiveIssue = {
  issue: NormativeIssue;
  index: number;
};

function NormativeReportPage() {
  const { reportId } = useParams();
  const { status, user } = useAuthSession();
  const [history, setHistory] = useState<DetectionTaskResponse[]>([]);
  const [report, setReport] = useState<DetectionTaskResponse | null>(null);
  const [pdfReports, setPdfReports] = useState<PaperLintReportListItem[]>([]);
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

    const request = reportId
      ? fetchNormativeDetectionReport(reportId)
      : Promise.all([fetchNormativeDetectionHistory(), fetchPaperLintReports().catch(() => [])]);
    request
      .then((response) => {
        if (cancelled) {
          return;
        }
        if (Array.isArray(response) && Array.isArray(response[0])) {
          const [legacyHistory, savedPdfReports] = response as [DetectionTaskResponse[], PaperLintReportListItem[]];
          setHistory(legacyHistory);
          setPdfReports(savedPdfReports);
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
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">历史检测记录</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后查看本人检测历史和报告。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  if (reportId) {
    return (
      <div>
        <PageHeader
          title="检测报告"
          breadcrumbs={[
            { label: '首页', to: '/' },
            { label: '历史检测记录', to: '/normative-reports' },
            { label: '检测报告' },
          ]}
          actions={
            <>
              <Button type="button" disabled={!report} onClick={() => report && handleDownloadJson(report.id)}>
                下载 UTF-8 JSON
              </Button>
              <Button type="button" variant="secondary" onClick={() => window.print()}>
                浏览器打印
              </Button>
            </>
          }
        />

        {loading ? <LoadingState label="正在加载报告…" /> : null}
        {errorMessage ? <ErrorState message={errorMessage} /> : null}

        {report ? (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
            <section className="max-h-[720px] overflow-auto rounded-2xl border border-[#E1E7EF] bg-white font-mono text-sm leading-7 text-slate-800">
              {lines.map((line, index) => {
                const lineNumber = index + 1;
                const isActive = activeIssue?.issue.line === lineNumber;
                return (
                  <div
                    key={lineNumber}
                    ref={(element) => {
                      lineRefs.current[lineNumber] = element;
                    }}
                    className={`grid grid-cols-[64px_minmax(0,1fr)] border-b border-slate-100 ${isActive ? 'bg-yellow-100' : ''}`}
                  >
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
                  <button
                    key={`${issue.rule_id}-${index}`}
                    aria-label={`${issue.severity} 第 ${issue.line} 行，第 ${issue.column} 列`}
                    className={`w-full rounded-xl border p-4 text-left text-sm ${activeIssue?.index === index ? 'border-[#D62020] bg-red-50' : 'border-slate-200 bg-white'}`}
                    type="button"
                    onClick={() => handleIssueClick(issue, index)}
                  >
                    <span className="font-black text-[#D62020]">{issue.severity}</span>
                    <span className="ml-2 text-slate-500">
                      第 {issue.line} 行，第 {issue.column} 列
                    </span>
                    <p className="mt-2 font-semibold text-slate-900">{issue.message}</p>
                    <p className="mt-1 text-slate-600">{issue.excerpt}</p>
                  </button>
                ))}
              </div>
            </aside>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="规范性检测" description="查看本人已保存的规范检测记录和报告。" />
      <ModuleTabs
        ariaLabel="规范性检测功能导航"
        items={[
          { label: '发起审查', to: '/normative-check', active: false },
          { label: '历史报告', to: '/normative-reports', active: true, count: history.length + pdfReports.length },
        ]}
      />
      {loading ? <LoadingState label="正在加载历史记录…" /> : null}
      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {!loading && !errorMessage && history.length === 0 && pdfReports.length === 0 ? (
        <EmptyState title="暂无检测记录" description="完成一次规范性检测后，报告会出现在这里。" />
      ) : null}
      {pdfReports.length > 0 ? (
        <section className="mb-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="font-bold text-slate-900">PDF 论文检查报告</h2>
              <p className="mt-1 text-sm text-slate-500">可继续查看原文定位、问题说明和修改建议。</p>
            </div>
            <span className="rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700">
              {pdfReports.length} 份
            </span>
          </div>
          <div className="divide-y divide-slate-100">
            {pdfReports.map((record) => (
              <div
                key={record.id}
                className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 hover:bg-brand-50/40"
              >
                <div className="min-w-0">
                  <p className="truncate font-semibold text-slate-900">{record.source_filename}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {new Date(record.created_at).toLocaleString('zh-CN')} ·{' '}
                    {record.summary.ruleset_label || '当前规则版本'}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-sm">
                  <span
                    className={
                      record.summary.error_finding_count
                        ? 'font-bold text-danger-600'
                        : 'font-semibold text-success-600'
                    }
                  >
                    {record.summary.finding_count ? `${record.summary.finding_count} 项待处理` : '未发现问题'}
                  </span>
                  <LinkButton size="sm" to={`/normative-reports/pdf/${record.id}`}>
                    继续处理
                  </LinkButton>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {history.length > 0 ? (
        <section>
          <div className="mb-3">
            <h2 className="font-bold text-slate-900">文本规范检测记录</h2>
            <p className="mt-1 text-sm text-slate-500">历史文本检测报告保留原有的行号定位方式。</p>
          </div>
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
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
                    <td className="px-6 py-6 font-bold text-slate-900">
                      📄 {record.source_filename || '粘贴文本检测'}
                    </td>
                    <td className="px-6 py-6 font-black text-[#D62020]">{record.issues.length}</td>
                    <td className="px-6 py-6 text-slate-700">
                      {record.severity_counts.high || 0} / {record.severity_counts.medium || 0} /{' '}
                      {record.severity_counts.low || 0}
                    </td>
                    <td className="px-6 py-6 text-slate-700">{record.created_at}</td>
                    <td className="px-6 py-6">
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="rounded-lg bg-[#1F3760] px-3 py-2 font-bold text-white"
                          type="button"
                          onClick={() => handleDownloadJson(record.id)}
                        >
                          报告下载
                        </button>
                        <LinkButton size="sm" to={`/normative-reports/${record.id}`}>
                          报告预览
                        </LinkButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default NormativeReportPage;
