import { useState } from 'react';
import {
  createReportSubmissions,
  type ReportSubmissionRequestItem,
  type CreateReportSubmissionResponse,
} from '../api/reportSubmissions';

export default function StudentReportSubmissionPage() {
  const [selectedReports, setSelectedReports] = useState<ReportSubmissionRequestItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<CreateReportSubmissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmitSelectedReports() {
    setSubmitting(true);
    setError(null);
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
        {['未提交', '待批阅', '已反馈', '学生已查看'].map((status, index) => (
          <span key={status} className="flex items-center gap-3">
            <span className="rounded-full bg-slate-400 px-5 py-2 text-sm font-bold text-white">{status}</span>
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
        <div className="border-b border-slate-200 px-5 py-4 text-sm text-slate-500">
          后续实现将从规范检测、相似度、创新性和 AI 评阅历史加载已完成且属于本人的报告，勾选后批量提交。
        </div>
        <div className="p-5">
          {error ? <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
          {result ? (
            <div className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">
              已创建批次 {result.batch_id}，待批阅记录 {result.submissions.length} 条。
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 px-4 py-12 text-center text-slate-500">
              暂无已加载的可提交报告。
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
