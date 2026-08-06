import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  fetchSupervisorReviewDetail,
  submitSupervisorReview,
  type SupervisorReviewAnnotation,
  type SupervisorReviewDetailResponse,
} from '../api/reportSupervisorReview';
import { EmptyState, ErrorState, LoadingState } from '../components/ui';

const severityLabels: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '轻微',
};

function formatDateTime(value: string) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export default function SupervisorReviewPage() {
  const { submissionId = '' } = useParams();
  const [detail, setDetail] = useState<SupervisorReviewDetailResponse | null>(null);
  const [annotations, setAnnotations] = useState<SupervisorReviewAnnotation[]>([]);
  const [selectedFindingId, setSelectedFindingId] = useState('');
  const [comment, setComment] = useState('');
  const [overallEvaluation, setOverallEvaluation] = useState('');
  const [improvementSuggestions, setImprovementSuggestions] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchSupervisorReviewDetail(submissionId)
      .then((response) => {
        if (!active) return;
        setDetail(response);
        setAnnotations(response.review.annotations);
        setOverallEvaluation(response.review.overall_evaluation || '');
        setImprovementSuggestions(response.review.improvement_suggestions || '');
        setSelectedFindingId(response.report.findings[0]?.finding_id || '');
      })
      .catch(() => {
        if (active) setError('报告批阅内容加载失败或无权访问该提交记录');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [submissionId]);

  const locked = Boolean(detail?.review.locked);
  const groupedFindings = useMemo(() => {
    const groups = new Map<string, SupervisorReviewDetailResponse['report']['findings']>();
    for (const finding of detail?.report.findings || []) {
      const key = finding.category || '未分类问题';
      groups.set(key, [...(groups.get(key) || []), finding]);
    }
    return Array.from(groups.entries());
  }, [detail]);

  function addAnnotation() {
    if (locked || !selectedFindingId || !comment.trim()) return;
    setAnnotations((current) => [...current, { finding_id: selectedFindingId, comment: comment.trim() }]);
    setComment('');
  }

  async function handleSubmit() {
    if (!overallEvaluation.trim()) {
      setError('提交评阅必须填写整体评价');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await submitSupervisorReview(submissionId, {
        annotations,
        overall_evaluation: overallEvaluation,
        improvement_suggestions: improvementSuggestions,
      });
      setDetail(response);
      setAnnotations(response.review.annotations);
    } catch {
      setError('提交评阅失败，请确认导师身份、待办归属和整体评价后重试');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="text-slate-900">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <Link className="text-xs font-semibold text-brand-600 hover:underline" to="/supervisor-review-queue">待批阅任务</Link>
          <h1 className="mt-1 text-lg font-bold text-[#173a5e]">原报告批注与整体反馈</h1>
        </div>
        <Link className="rounded border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100" to="/supervisor-review-queue">
          返回待办中心
        </Link>
      </div>

      {error ? <ErrorState message={error} /> : null}
      {loading ? (
        <LoadingState label="正在加载原报告…" />
      ) : detail ? (
        <section className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          <article className="overflow-hidden rounded border border-slate-200 bg-white">
            <div className="border-b border-slate-200 bg-[#e9f7ff] px-4 py-3 text-sm font-semibold text-[#173a5e]">
              学生 {detail.student_id} · 报告 {detail.report_id} · {formatDateTime(detail.report.created_at)}
            </div>
            <div className="max-h-[70vh] overflow-auto p-4 text-sm">
              {groupedFindings.length === 0 ? (
                <EmptyState title="暂无可批注问题项" />
              ) : groupedFindings.map(([category, findings]) => (
                <div key={category} className="mb-4 overflow-hidden rounded border border-slate-200">
                  <div className="bg-[#e9f7ff] px-3 py-2 font-bold text-[#1f436a]">{category}（{findings.length}）</div>
                  {findings.map((finding) => (
                    <button
                      key={finding.finding_id}
                      className="block w-full border-t border-slate-200 px-3 py-3 text-left hover:bg-[#fffbea]"
                      onClick={() => setSelectedFindingId(finding.finding_id)}
                      type="button"
                    >
                      <span className="mr-2 font-mono text-xs text-slate-500">{finding.finding_id}</span>
                      <span className="font-semibold">{finding.message}</span>
                      <span className="float-right rounded-full bg-orange-100 px-2 py-1 text-xs font-bold text-orange-700">
                        {severityLabels[finding.severity] || finding.severity}
                      </span>
                      <p className="mt-1 text-xs text-slate-500">{finding.suggestion}</p>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </article>

          <aside className="rounded border border-slate-200 bg-white p-4 text-sm">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-bold text-[#173a5e]">批注列表与反馈</h2>
              {locked ? <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-bold text-green-700">已锁定</span> : null}
            </div>
            <div className="mb-4 rounded border border-dashed border-blue-200 bg-[#fffbea] p-3">
              {annotations.length === 0 ? <p className="text-slate-500">尚未添加问题批注。</p> : annotations.map((annotation, index) => (
                <div key={`${annotation.finding_id}-${index}`} className="border-b border-yellow-100 py-2 last:border-b-0">
                  <p className="font-mono text-xs text-slate-500">{annotation.finding_id}</p>
                  <p>{annotation.comment}</p>
                </div>
              ))}
            </div>
            <label className="mb-2 block font-semibold text-slate-700">
              finding_id
              <input className="mt-1 w-full rounded border border-slate-300 px-3 py-2" disabled={locked} value={selectedFindingId} onChange={(event) => setSelectedFindingId(event.target.value)} />
            </label>
            <label className="mb-3 block font-semibold text-slate-700">
              批注内容
              <textarea className="mt-1 min-h-20 w-full rounded border border-slate-300 px-3 py-2" disabled={locked} value={comment} onChange={(event) => setComment(event.target.value)} />
            </label>
            <button className="mb-4 rounded border border-blue-500 px-3 py-2 font-bold text-blue-600 disabled:opacity-50" disabled={locked || !comment.trim()} onClick={addAnnotation} type="button">添加批注</button>
            <label className="mb-3 block font-semibold text-green-700">
              整体评价（必填）
              <textarea className="mt-1 min-h-24 w-full rounded border border-slate-300 px-3 py-2 text-slate-900" disabled={locked} value={overallEvaluation} onChange={(event) => setOverallEvaluation(event.target.value)} />
            </label>
            <label className="mb-4 block font-semibold text-orange-600">
              整改建议
              <textarea className="mt-1 min-h-24 w-full rounded border border-slate-300 px-3 py-2 text-slate-900" disabled={locked} value={improvementSuggestions} onChange={(event) => setImprovementSuggestions(event.target.value)} />
            </label>
            <div className="flex items-center justify-between">
              <span className="text-xs text-green-600">内容将以提交结果为准并锁定本轮批阅。</span>
              <button className="rounded bg-[#2f80ed] px-5 py-2 font-bold text-white disabled:opacity-50" disabled={locked || submitting} onClick={handleSubmit} type="button">
                {submitting ? '提交中...' : '提交评阅'}
              </button>
            </div>
          </aside>
        </section>
      ) : null}
    </div>
  );
}
