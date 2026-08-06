import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Card, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader } from '../components/ui';
import {
  downloadStudentReportResultJson,
  fetchStudentReportResultDetail,
  fetchStudentReportResults,
  type StudentReportResultDetail,
  type StudentReportResultListFilters,
  type StudentReportResultStatus,
  type StudentReportResultSummary,
} from '../api/reportStudentResults';

const SOURCE_TYPE_OPTIONS: Array<{ label: string; value: StudentReportResultListFilters['source_type'] | '' }> = [
  { label: '全部类型', value: '' },
  { label: '规范性检查', value: 'normative' },
  { label: '查重结果', value: 'duplication' },
  { label: '创新性量表', value: 'innovation' },
  { label: '辅助评阅', value: 'ai_review' },
];

const STATUS_OPTIONS: Array<{ label: string; value: StudentReportResultStatus | '' }> = [
  { label: '全部状态', value: '' },
  { label: '待反馈', value: 'submitted_pending_review' },
  { label: '批阅完成已反馈', value: 'review_completed_feedback' },
  { label: '学生已查阅', value: 'student_viewed_feedback' },
];

function formatTimestamp(value: string | null | undefined) {
  if (!value) return '—';
  return value.replace('T', ' ').replace('Z', '');
}

export default function StudentReportResultsPage() {
  const { submissionId } = useParams();
  const { status: sessionStatus, user } = useAuthSession();
  const [filters, setFilters] = useState<StudentReportResultListFilters>({});
  const [results, setResults] = useState<StudentReportResultSummary[]>([]);
  const [detail, setDetail] = useState<StudentReportResultDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null);

  const listCount = useMemo(() => results.length, [results]);

  useEffect(() => {
    if (sessionStatus !== 'authenticated' || !user) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    setDownloadMessage(null);

    const request = submissionId ? fetchStudentReportResultDetail(submissionId) : fetchStudentReportResults(filters);
    request
      .then((data) => {
        if (cancelled) return;
        if ('results' in data) {
          setResults(data.results);
          setDetail(null);
        } else {
          setDetail(data);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '批阅结果加载失败');
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
  }, [filters, sessionStatus, submissionId, user]);

  async function handleDownload() {
    if (!detail) return;
    setDownloadMessage(null);
    try {
      await downloadStudentReportResultJson(detail.submission_id);
      setDownloadMessage('JSON 文件已准备，可保存本轮摘要、批注和评价。');
    } catch (error) {
      setDownloadMessage(error instanceof Error ? error.message : 'JSON 下载失败');
    }
  }

  function updateFilter<K extends keyof StudentReportResultListFilters>(
    key: K,
    value: StudentReportResultListFilters[K] | '',
  ) {
    setFilters((current) => {
      const next = { ...current };
      if (value === '' || value === undefined) {
        delete next[key];
      } else {
        next[key] = value as StudentReportResultListFilters[K];
      }
      return next;
    });
  }

  if (sessionStatus === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-semibold text-slate-900">我的批阅结果</h1>
          <p className="mt-3 text-sm text-slate-500">请先登录学生账号后查看批阅结果。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  if (loading) {
    return <LoadingState label="正在加载批阅结果…" />;
  }

  if (errorMessage) {
    return <ErrorState message={errorMessage} />;
  }

  if (detail) {
    return (
      <div className="space-y-6">
        <Link className="text-sm text-blue-600" to="/student-report-results">
          返回结果列表
        </Link>
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
          <pre className="mt-6 whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
            {detail.report.original_text}
          </pre>
          {downloadMessage ? <p className="mt-4 text-sm text-emerald-700">{downloadMessage}</p> : null}
        </section>
        <section className="grid gap-4 lg:grid-cols-2">
          <article className="rounded-2xl border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">Finding 批注</h2>
            {detail.review.annotations.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">暂无逐条批注。</p>
            ) : null}
            {detail.review.annotations.length > 0 ? (
              <ul className="mt-3 space-y-3">
                {detail.review.annotations.map((annotation, index) => (
                  <li
                    key={`${annotation.finding_id}-${index}`}
                    className="rounded-lg border bg-slate-50 p-3 text-sm text-slate-700"
                  >
                    <p className="font-medium text-slate-900">{annotation.finding_id}</p>
                    <p className="mt-1">{annotation.comment}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </article>
          <article className="rounded-2xl border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">整体评价与整改建议</h2>
            <p className="mt-3 text-slate-700">{detail.review.overall_evaluation}</p>
            <p className="mt-3 text-sm text-slate-600">{detail.review.improvement_suggestions || '暂无整改建议。'}</p>
          </article>
        </section>
        <section className="rounded-2xl border bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">历史轮次</h2>
          <ul className="mt-4 divide-y" aria-label="历史轮次">
            {detail.history_rounds.map((round) => (
              <li key={round.submission_id} className="flex items-center justify-between py-3 text-sm">
                <div>
                  <p className="font-medium text-slate-900">{round.report_id}</p>
                  <p className="text-slate-500">
                    {formatTimestamp(round.submitted_at)} · {round.source_type}
                  </p>
                </div>
                <span className="text-slate-600">{round.status}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="我的批阅结果" description="按时间、报告类型和状态筛选本人所有提交轮次。" />
      <section className="grid gap-3 rounded-2xl border bg-white p-4 shadow-sm md:grid-cols-4">
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">开始时间</span>
          <input
            aria-label="开始时间"
            className="w-full rounded-md border px-3 py-2"
            type="date"
            value={filters.from || ''}
            onChange={(event) => updateFilter('from', event.target.value)}
          />
        </label>
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">结束时间</span>
          <input
            aria-label="结束时间"
            className="w-full rounded-md border px-3 py-2"
            type="date"
            value={filters.to || ''}
            onChange={(event) => updateFilter('to', event.target.value)}
          />
        </label>
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">报告类型</span>
          <select
            aria-label="报告类型"
            className="w-full rounded-md border px-3 py-2"
            value={filters.source_type || ''}
            onChange={(event) =>
              updateFilter('source_type', event.target.value as StudentReportResultListFilters['source_type'] | '')
            }
          >
            {SOURCE_TYPE_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-700">
          <span className="mb-1 block font-medium">状态</span>
          <select
            aria-label="状态"
            className="w-full rounded-md border px-3 py-2"
            value={filters.status || ''}
            onChange={(event) => updateFilter('status', event.target.value as StudentReportResultStatus | '')}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </section>
      <section className="rounded-2xl border bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-slate-900">批阅结果列表</h2>
          <p className="text-sm text-slate-500">共 {listCount} 条</p>
        </div>
        {results.length === 0 ? (
          <EmptyState title="暂无批阅结果" description="导师完成批阅并反馈后，结果会展示在这里。" />
        ) : null}
        <ul className="mt-4 divide-y" aria-label="批阅结果列表">
          {results.map((item) => (
            <li className="flex items-center justify-between gap-4 py-4" key={item.submission_id}>
              <div>
                <p className="font-medium text-slate-900">{item.report_id}</p>
                <p className="text-sm text-slate-500">
                  {item.source_type} · {item.status} · {formatTimestamp(item.feedback_at)}
                </p>
              </div>
              <Link className="text-blue-600" to={`/student-report-results/${item.submission_id}`}>
                查看详情
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
