import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  downloadDuplicationReportJson,
  fetchDuplicationDetectionHistory,
  fetchDuplicationDetectionReport,
  type DuplicationHistoryRecord,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';
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

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function getDocumentName(record: DuplicationHistoryRecord) {
  return record.source_filename || '粘贴文本检测';
}

function DuplicationHistoryPage() {
  const { reportId } = useParams();
  const { status, user } = useAuthSession();
  const [history, setHistory] = useState<DuplicationHistoryRecord[]>([]);
  const [report, setReport] = useState<DuplicationHistoryRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const reportPayload = useMemo(() => (report ? JSON.stringify(report.report_json, null, 2) : ''), [report]);

  useEffect(() => {
    if (status !== 'authenticated' || !user) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);

    const request = reportId ? fetchDuplicationDetectionReport(reportId) : fetchDuplicationDetectionHistory();
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
          setErrorMessage(error instanceof Error ? error.message : '相似度检测历史加载失败');
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

  async function handleDownloadJson(recordId: string) {
    const blob = await downloadDuplicationReportJson(recordId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `duplication-report-${recordId}.json`;
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
          <h1 className="text-2xl font-black text-[#1F3A63]">历史检测记录</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后查看本人相似度检测历史和完整报告。</p>
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
          title="查重检测报告"
          breadcrumbs={[
            { label: '首页', to: '/' },
            { label: '历史检测记录', to: '/duplication-history' },
            { label: '查重检测报告' },
          ]}
          actions={
            <>
              <Button type="button" disabled={!report} onClick={() => report && handleDownloadJson(report.id)}>
                报告下载
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
          <Card>
            <dl className="grid gap-4 text-sm font-bold sm:grid-cols-4">
              <div>文档名：{getDocumentName(report)}</div>
              <div className="text-[#D93636]">总相似率：{formatPercent(report.total_similarity_rate)}</div>
              <div className="text-[#D93636]">写作风险分：{Math.round(report.writing_risk_score)}</div>
              <div>样本库数量：{report.sample_count}</div>
            </dl>
            <pre className="mt-6 max-h-[640px] overflow-auto rounded-2xl bg-slate-950 p-5 text-xs leading-6 text-slate-50">
              {reportPayload}
            </pre>
          </Card>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="论文相似度检测" description="查看本人以往检测记录和完整报告。" />
      <ModuleTabs
        ariaLabel="论文相似度检测功能导航"
        items={[
          { label: '发起检测', to: '/duplication-detect', active: false },
          { label: '历史记录', to: '/duplication-history', active: true, count: history.length },
        ]}
      />
      {loading ? <LoadingState label="正在加载历史记录…" /> : null}
      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {!loading && !errorMessage && history.length === 0 ? (
        <EmptyState title="暂无相似度检测记录" description="完成一次论文相似度检测后，报告会出现在这里。" />
      ) : null}
      {history.length > 0 ? (
        <div className="overflow-x-auto border border-[#E3EAF2] bg-white">
          <table className="min-w-full text-center text-[15px]">
            <thead className="bg-[#1F3A63] text-base font-bold text-white">
              <tr>
                <th className="px-6 py-5 text-left">文档名称</th>
                <th className="px-6 py-5">检测类型</th>
                <th className="px-6 py-5">检测结果</th>
                <th className="px-6 py-5">报告生成时间</th>
                <th className="px-6 py-5">操作</th>
                <th className="px-6 py-5">提交状态</th>
              </tr>
            </thead>
            <tbody>
              {history.map((record, index) => (
                <tr
                  key={record.id}
                  className={`border-b border-[#E3EAF2] ${index % 2 === 0 ? 'bg-white' : 'bg-[#F3F7FB]'}`}
                >
                  <td className="min-w-64 px-6 py-7 text-left font-black text-slate-900">
                    📄 {getDocumentName(record)}
                  </td>
                  <td className="px-6 py-7 font-bold">论文相似度检测</td>
                  <td className="px-6 py-7 font-black text-[#D93636]">
                    总相似率 {formatPercent(record.total_similarity_rate)} · 风险分{' '}
                    {Math.round(record.writing_risk_score)} · 样本 {record.sample_count}
                  </td>
                  <td className="px-6 py-7 text-slate-700">{record.created_at}</td>
                  <td className="px-6 py-7">
                    <div className="flex flex-nowrap justify-center gap-3">
                      <button
                        className="h-9 rounded-full bg-[#355B8E] px-4 text-sm font-bold text-white"
                        type="button"
                        onClick={() => handleDownloadJson(record.id)}
                      >
                        报告下载
                      </button>
                      <LinkButton size="sm" className="!rounded-full" to={`/duplication-history/${record.id}`}>
                        报告预览
                      </LinkButton>
                    </div>
                  </td>
                  <td className="px-6 py-7 font-bold text-slate-800">未提交</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

export default DuplicationHistoryPage;
