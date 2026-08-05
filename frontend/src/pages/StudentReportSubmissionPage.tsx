import { useEffect, useMemo, useState } from 'react';
import {
  createReportSubmissions,
  type ReportSubmissionRequestItem,
  type CreateReportSubmissionResponse,
  type ReportSubmissionSourceType,
} from '../api/reportSubmissions';
import {
  fetchAiReviewHistory,
  fetchDuplicationDetectionHistory,
  fetchInnovationHistory,
  fetchNormativeDetectionHistory,
  type AiReviewHistoryRecord,
  type DetectionTaskResponse,
  type DuplicationHistoryRecord,
  type InnovationHistoryRecord,
} from '../api/normativeRules';

type RuntimeReportRow = ReportSubmissionRequestItem & {
  key: string;
  title: string;
  typeLabel: string;
  createdAt: string;
  summary: string;
};

const sourceLabels: Record<ReportSubmissionSourceType, string> = {
  normative: '规范检测',
  duplication: '相似度检测',
  innovation: '创新性评价',
  ai_review: 'AI 评阅',
};

function formatDateTime(value: string) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function makeRow(sourceType: ReportSubmissionSourceType, report: {
  id: string;
  created_at: string;
  source_filename?: string | null;
  thesis_title?: string;
  status?: string;
  severity_counts?: Record<string, number>;
  total_similarity_rate?: number;
  total_score?: number;
  grade_label?: string;
  result_label?: string;
}): RuntimeReportRow | null {
  if (sourceType === 'normative' && report.status !== 'completed') {
    return null;
  }

  const typeLabel = sourceLabels[sourceType];
  const issueCount = Object.values(report.severity_counts || {}).reduce((total, count) => total + Number(count || 0), 0);
  const summaries: Record<ReportSubmissionSourceType, string> = {
    normative: `规范问题 ${issueCount} 项`,
    duplication: typeof report.total_similarity_rate === 'number' ? `相似度 ${(report.total_similarity_rate * 100).toFixed(1)}%` : '相似度报告已完成',
    innovation: typeof report.total_score === 'number' ? `创新评分 ${report.total_score}${report.grade_label ? ` · ${report.grade_label}` : ''}` : '创新性报告已完成',
    ai_review: typeof report.total_score === 'number' ? `AI 评分 ${report.total_score}${report.result_label ? ` · ${report.result_label}` : ''}` : 'AI 评阅报告已完成',
  };

  return {
    key: `${sourceType}:${report.id}`,
    source_type: sourceType,
    report_id: report.id,
    typeLabel,
    title: report.source_filename || report.thesis_title || `${typeLabel} ${report.id}`,
    createdAt: report.created_at,
    summary: summaries[sourceType],
  };
}

async function loadCompletedRuntimeReports(): Promise<RuntimeReportRow[]> {
  const [normative, duplication, innovation, aiReview] = await Promise.all([
    fetchNormativeDetectionHistory(),
    fetchDuplicationDetectionHistory(),
    fetchInnovationHistory(),
    fetchAiReviewHistory(),
  ]);

  return [
    ...normative.map((report: DetectionTaskResponse) => makeRow('normative', report)),
    ...duplication.map((report: DuplicationHistoryRecord) => makeRow('duplication', report)),
    ...innovation.map((report: InnovationHistoryRecord) => makeRow('innovation', report)),
    ...aiReview.map((report: AiReviewHistoryRecord) => makeRow('ai_review', report)),
  ]
    .filter((row): row is RuntimeReportRow => Boolean(row))
    .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime());
}

export default function StudentReportSubmissionPage() {
  const [reports, setReports] = useState<RuntimeReportRow[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<CreateReportSubmissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    loadCompletedRuntimeReports()
      .then((rows) => {
        if (!active) return;
        setReports(rows);
        setSelectedKeys((keys) => keys.filter((key) => rows.some((row) => row.key === key)));
      })
      .catch(() => {
        if (!active) return;
        setLoadError('可提交报告加载失败，请稍后重试');
        setReports([]);
        setSelectedKeys([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedReports = useMemo<ReportSubmissionRequestItem[]>(() => reports
    .filter((report) => selectedKeys.includes(report.key))
    .map(({ source_type, report_id }) => ({ source_type, report_id })), [reports, selectedKeys]);

  function toggleReport(row: RuntimeReportRow) {
    setResult(null);
    setError(null);
    setSelectedKeys((keys) => (keys.includes(row.key) ? keys.filter((key) => key !== row.key) : [...keys, row.key]));
  }

  async function handleSubmitSelectedReports() {
    if (selectedReports.length === 0) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const response = await createReportSubmissions({ reports: selectedReports });
      setResult(response);
    } catch {
      setError('报告提交失败，请确认所选报告已完成且属于本人');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f5f7fa] text-slate-900">
      <header className="flex h-[72px] items-center justify-between bg-[#1f3f67] px-8 text-white">
        <h1 className="text-2xl font-bold">学生报告提交与批阅结果台账</h1>
        <div className="rounded-xl bg-[#173a62] p-1 text-sm font-bold">
          <span className="rounded-lg bg-[#3489f5] px-4 py-2">学生端</span>
        </div>
      </header>

      <section className="flex items-center gap-3 border-b border-slate-200 bg-slate-100 px-8 py-4">
        <span className="font-semibold text-slate-700">报告状态流转：</span>
        {[
          ['未提交', 'bg-slate-400'],
          ['待批阅', 'bg-[#ff8f2a]'],
          ['已反馈', 'bg-[#43c83a]'],
          ['学生已查看', 'bg-[#3489f5]'],
        ].map(([status, color], index) => (
          <span key={status} className="flex items-center gap-3">
            <span className={`rounded-full ${color} px-5 py-2 text-sm font-bold text-white`}>{status}</span>
            {index < 3 ? <span className="text-slate-400">&gt;</span> : null}
          </span>
        ))}
        <span className="ml-auto text-sm text-slate-500">仅展示运行时加载的本人已完成报告，不使用示例数据。</span>
      </section>

      <section className="m-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between bg-[#1f3f67] px-5 py-4 text-white">
          <h2 className="text-xl font-bold">可提交报告</h2>
          <button
            type="button"
            disabled={submitting || selectedReports.length === 0}
            onClick={handleSubmitSelectedReports}
            className="rounded-lg bg-[#3489f5] px-5 py-2 font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {submitting ? '提交中...' : '推送报告'}
          </button>
        </div>
        <div className="flex gap-3 border-b border-slate-200 px-5 py-4 text-sm text-slate-500">
          <span className="rounded border border-slate-200 px-3 py-2">类型：全部</span>
          <span className="rounded border border-slate-200 px-3 py-2">状态：已完成</span>
          <span className="rounded border border-slate-200 px-3 py-2">时间：全部</span>
          <span className="ml-auto py-2">勾选报告后批量推送导师批阅待办。</span>
        </div>
        <div className="p-5">
          {error ? <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
          {loadError ? <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{loadError}</div> : null}
          {result ? (
            <div className="mb-4 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">
              已创建批次 {result.batch_id}，待批阅记录 {result.submissions.length} 条。
            </div>
          ) : null}

          {loading ? (
            <div className="rounded-lg border border-dashed border-slate-300 px-4 py-12 text-center text-slate-500">正在加载可提交报告...</div>
          ) : reports.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 px-4 py-12 text-center text-slate-500">
              暂无已加载的可提交报告。
            </div>
          ) : (
            <table className="w-full border-collapse overflow-hidden rounded-lg text-sm">
              <thead className="bg-[#1f3f67] text-white">
                <tr>
                  <th className="border border-[#173a62] px-4 py-3">选择</th>
                  <th className="border border-[#173a62] px-4 py-3">检测类型</th>
                  <th className="border border-[#173a62] px-4 py-3">报告编号</th>
                  <th className="border border-[#173a62] px-4 py-3">报告名称</th>
                  <th className="border border-[#173a62] px-4 py-3">结果摘要</th>
                  <th className="border border-[#173a62] px-4 py-3">完成时间</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((row) => (
                  <tr key={row.key} className="text-center even:bg-slate-50">
                    <td className="border border-slate-200 px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={`${row.typeLabel} ${row.report_id}`}
                        checked={selectedKeys.includes(row.key)}
                        onChange={() => toggleReport(row)}
                        className="h-4 w-4 accent-[#3489f5]"
                      />
                    </td>
                    <td className="border border-slate-200 px-4 py-3 font-semibold text-[#1f3f67]">{row.typeLabel}</td>
                    <td className="border border-slate-200 px-4 py-3 font-mono text-xs">{row.report_id}</td>
                    <td className="border border-slate-200 px-4 py-3">{row.title}</td>
                    <td className="border border-slate-200 px-4 py-3">{row.summary}</td>
                    <td className="border border-slate-200 px-4 py-3">{formatDateTime(row.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </main>
  );
}
