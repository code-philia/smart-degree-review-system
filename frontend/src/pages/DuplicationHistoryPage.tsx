import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  downloadDuplicationReportJson,
  fetchDuplicationDetectionHistory,
  fetchDuplicationDetectionReport,
  type DuplicationDetectionResponse,
  type DuplicationHistoryRecord,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { formatChinaDateTime } from '../utils/dateTime';
import {
  Button,
  Card,
  DataTable,
  DataTableCell,
  DataTableHead,
  DataTableRow,
  EmptyState,
  ErrorState,
  LinkButton,
  LoadingState,
  ModuleTabs,
  PageHeader,
  StatusBadge,
} from '../components/ui';

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function getDocumentName(record: DuplicationHistoryRecord) {
  return record.source_filename || '粘贴文本检测';
}

function getDetectionReport(value: DuplicationHistoryRecord['report_json']): DuplicationDetectionResponse | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  const candidate = value as Partial<DuplicationDetectionResponse>;
  return Array.isArray(candidate.top_matches) && candidate.risk && typeof candidate.risk === 'object'
    ? (candidate as DuplicationDetectionResponse)
    : null;
}

function getDetectionTypeLabel(record: DuplicationHistoryRecord) {
  const report = getDetectionReport(record.report_json);
  return report?.detection_type_label || '校内库查重';
}

const RISK_FACTOR_LABELS: Record<string, string> = {
  paragraph_duplication_rate: '段落重复度',
  sentence_length_low_variation: '句式长度单一',
  template_connector_density: '模板连接词密度',
  vague_phrase_density: '模糊表达密度',
};

function DuplicationHistoryPage() {
  const { reportId } = useParams();
  const { status, user } = useAuthSession();
  const [history, setHistory] = useState<DuplicationHistoryRecord[]>([]);
  const [report, setReport] = useState<DuplicationHistoryRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const detectionReport = report ? getDetectionReport(report.report_json) : null;

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
          description={report ? `检测完成于 ${formatChinaDateTime(report.created_at)}` : '查看相似片段与写作风险提示。'}
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
          <div className="mx-auto max-w-6xl space-y-6">
            <Card
              title="检测摘要"
              description={`${getDetectionTypeLabel(report)} · ${getDocumentName(report)}`}
              actions={<StatusBadge tone="success">检测完成</StatusBadge>}
            >
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ...(detectionReport?.detection_type === 'aigc_writing_risk'
                    ? [['写作风险分', String(Math.round(report.writing_risk_score)), 'text-slate-900']]
                    : [
                        ['总相似率', formatPercent(report.total_similarity_rate), 'text-danger-600'],
                        ['比对样本数', String(report.sample_count), 'text-slate-900'],
                      ]),
                  ['有效字符数', String(detectionReport?.effective_character_count ?? '—'), 'text-slate-900'],
                ].map(([label, value, tone]) => (
                  <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-medium text-slate-500">{label}</p>
                    <p className={`mt-1 text-2xl font-black ${tone}`}>{value}</p>
                  </div>
                ))}
              </div>
              <dl className="mt-5 grid gap-x-8 gap-y-2 border-t border-slate-100 pt-4 text-sm sm:grid-cols-2">
                <div className="flex justify-between gap-4">
                  <dt className="text-slate-500">检测方式</dt>
                  <dd className="font-semibold text-slate-900">
                    {report.source_type === 'file' ? '文件上传' : '文本粘贴'}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-slate-500">报告生成时间</dt>
                  <dd className="font-semibold text-slate-900">{formatChinaDateTime(report.created_at)}</dd>
                </div>
              </dl>
            </Card>

            {detectionReport?.detection_type !== 'aigc_writing_risk' ? (
              <Card title="相似片段" description="以下内容用于辅助核对，建议结合论文语境和引用规范判断。">
                {!detectionReport ? (
                  <p className="rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600">
                    该历史报告未保留可展示的片段明细，可下载原始报告进行查看。
                  </p>
                ) : detectionReport.status === 'no_samples' || detectionReport.top_matches.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600">
                    当前试点样本库中没有达到检测阈值的相似片段。
                  </p>
                ) : (
                  <div className="space-y-4">
                    {detectionReport.top_matches.map((match) => (
                      <article key={match.sample_id} className="rounded-xl border border-slate-200 p-4 sm:p-5">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <h3 className="font-bold text-slate-900">{match.title}</h3>
                            <p className="mt-1 text-sm text-slate-500">
                              {match.subject || '未标注学科'} · {match.year || '年份未标注'}
                            </p>
                          </div>
                          <div className="flex gap-2 text-xs font-semibold">
                            <span className="rounded-full bg-danger-50 px-2.5 py-1 text-danger-600">
                              相似度 {formatPercent(match.jaccard_score)}
                            </span>
                            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">
                              命中 {match.matched_character_count} 字
                            </span>
                          </div>
                        </div>
                        <div className="mt-4 space-y-3">
                          {match.segments.map((segment, index) => (
                            <div
                              key={`${segment.source_start}-${segment.sample_start}-${index}`}
                              className="grid gap-3 rounded-lg bg-slate-50 p-3 lg:grid-cols-2"
                            >
                              <div>
                                <p className="text-xs font-bold text-slate-500">论文片段</p>
                                <p className="mt-1 text-sm leading-6 text-slate-800">{segment.source_excerpt}</p>
                              </div>
                              <div className="border-t border-slate-200 pt-3 lg:border-l lg:border-t-0 lg:pl-3 lg:pt-0">
                                <p className="text-xs font-bold text-slate-500">样本片段</p>
                                <p className="mt-1 text-sm leading-6 text-slate-800">{segment.sample_excerpt}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </Card>
            ) : null}

            <Card
              title={detectionReport?.detection_type === 'aigc_writing_risk' ? 'AIGC 写作风险提示' : '写作风险提示'}
              description="该分值仅基于文本特征进行启发式计算，不构成 AI 真伪或学术不端结论。"
            >
              {detectionReport ? (
                <>
                  <p className="text-sm leading-6 text-slate-700">{detectionReport.risk.explanation}</p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    {Object.entries(detectionReport.risk.factors).map(([key, value]) => (
                      <div
                        key={key}
                        className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3 text-sm"
                      >
                        <span className="text-slate-600">{RISK_FACTOR_LABELS[key] || key}</span>
                        <strong className="text-slate-900">{Math.round(value)}</strong>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-sm text-slate-600">该历史报告未保留风险因素明细。</p>
              )}
            </Card>
          </div>
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
          { label: '历史报告', to: '/duplication-history', active: true, count: history.length },
        ]}
      />
      {loading ? <LoadingState label="正在加载历史记录…" /> : null}
      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {!loading && !errorMessage && history.length === 0 ? (
        <EmptyState title="暂无相似度检测记录" description="完成一次论文相似度检测后，报告会出现在这里。" />
      ) : null}
      {history.length > 0 ? (
        <DataTable aria-label="相似度检测历史记录">
          <thead>
            <DataTableRow className="hover:bg-transparent">
              <DataTableHead>文档名称</DataTableHead>
              <DataTableHead className="text-center">检测类型</DataTableHead>
              <DataTableHead>检测结果</DataTableHead>
              <DataTableHead className="text-center">报告生成时间</DataTableHead>
              <DataTableHead className="text-center">操作</DataTableHead>
              <DataTableHead className="text-center">提交状态</DataTableHead>
            </DataTableRow>
          </thead>
          <tbody>
            {history.map((record, index) => (
              <DataTableRow key={record.id} className={index % 2 === 0 ? '' : 'bg-slate-50/60'}>
                <DataTableCell className="min-w-64 font-semibold text-slate-900">
                  {getDocumentName(record)}
                </DataTableCell>
                <DataTableCell className="text-center font-medium">{getDetectionTypeLabel(record)}</DataTableCell>
                <DataTableCell className="font-semibold text-danger-600">
                  {getDetectionReport(record.report_json)?.detection_type === 'aigc_writing_risk'
                    ? `写作风险分 ${Math.round(record.writing_risk_score)} · 启发式提示`
                    : `总相似率 ${formatPercent(record.total_similarity_rate)} · 样本 ${record.sample_count}`}
                </DataTableCell>
                <DataTableCell className="text-center tabular-nums">
                  {formatChinaDateTime(record.created_at)}
                </DataTableCell>
                <DataTableCell className="text-center">
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
                </DataTableCell>
                <DataTableCell className="text-center font-medium">未提交</DataTableCell>
              </DataTableRow>
            ))}
          </tbody>
        </DataTable>
      ) : null}
    </div>
  );
}

export default DuplicationHistoryPage;
