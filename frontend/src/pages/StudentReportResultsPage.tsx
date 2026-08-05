import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  downloadStudentReportResultJson,
  fetchStudentReportResultDetail,
  fetchStudentReportResults,
  type StudentReportResultDetail,
  type StudentReportResultListFilters,
  type StudentReportResultSummary,
} from '../api/reportStudentResults';

export default function StudentReportResultsPage() {
  const { submissionId } = useParams();
  const [filters, setFilters] = useState<StudentReportResultListFilters>({});
  const [results, setResults] = useState<StudentReportResultSummary[]>([]);
  const [detail, setDetail] = useState<StudentReportResultDetail | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');

  useEffect(() => {
    setStatus('loading');
    const request = submissionId ? fetchStudentReportResultDetail(submissionId) : fetchStudentReportResults(filters);
    request
      .then((data) => {
        if ('results' in data) {
          setResults(data.results);
          setDetail(null);
        } else {
          setDetail(data);
        }
        setStatus('idle');
      })
      .catch(() => setStatus('error'));
  }, [filters, submissionId]);

  async function handleDownload() {
    if (!detail) return;
    await downloadStudentReportResultJson(detail.submission_id);
  }

  if (status === 'loading') {
    return <main className="p-8 text-slate-600">正在加载批阅结果...</main>;
  }

  if (status === 'error') {
    return <main className="p-8 text-red-600">无法加载批阅结果，请确认登录学生账号后重试。</main>;
  }

  if (detail) {
    return (
      <main className="space-y-6 p-8">
        <Link className="text-sm text-blue-600" to="/student-report-results">返回结果列表</Link>
        <section className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold text-slate-900">{detail.report.title}</h1>
              <p className="mt-2 text-sm text-slate-500">状态：{detail.status}</p>
            </div>
            <button className="rounded-lg bg-blue-600 px-4 py-2 text-white" type="button" onClick={handleDownload}>
              下载 JSON
            </button>
          </div>
          <pre className="mt-6 whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">{detail.report.original_text}</pre>
        </section>
        <section className="grid gap-4 lg:grid-cols-2">
          <article className="rounded-2xl border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">Finding 批注</h2>
            {detail.review.annotations.length === 0 ? <p className="mt-3 text-sm text-slate-500">暂无逐条批注。</p> : null}
          </article>
          <article className="rounded-2xl border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">整体评价与整改建议</h2>
            <p className="mt-3 text-slate-700">{detail.review.overall_evaluation}</p>
            <p className="mt-3 text-sm text-slate-600">{detail.review.improvement_suggestions || '暂无整改建议。'}</p>
          </article>
        </section>
      </main>
    );
  }

  return (
    <main className="space-y-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">我的批阅结果</h1>
        <p className="mt-2 text-sm text-slate-500">按时间、报告类型和状态筛选本人所有提交轮次。</p>
      </header>
      <section className="rounded-2xl border bg-white p-6 shadow-sm">
        {results.length === 0 ? <p className="text-sm text-slate-500">暂无批阅结果。</p> : null}
        <ul className="divide-y">
          {results.map((item) => (
            <li className="flex items-center justify-between py-4" key={item.submission_id}>
              <div>
                <p className="font-medium text-slate-900">{item.report_id}</p>
                <p className="text-sm text-slate-500">{item.source_type} · {item.status}</p>
              </div>
              <Link className="text-blue-600" to={`/student-report-results/${item.submission_id}`}>查看详情</Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
