import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  fetchStudentQualityPortrait,
  type StudentQualityPortraitMetric,
  type StudentQualityPortraitResponse,
} from '../api/normativeRules';

function formatScore(score: number | null) {
  return score === null ? '缺失' : score.toFixed(1);
}

function formatSourceTime(value: string | null) {
  return value || '暂无完成记录';
}

function buildOverallScoreLabel(portrait: StudentQualityPortraitResponse | null) {
  if (!portrait) {
    return '请输入学生 ID 后查询本人与组织范围内的最新质量画像';
  }
  return portrait.completeness.complete && portrait.overall_score !== null
    ? `${portrait.overall_score.toFixed(1)} 分`
    : '数据不完整';
}

function getMetricByKey(metrics: StudentQualityPortraitMetric[], key: StudentQualityPortraitMetric['key']) {
  return metrics.find((metric) => metric.key === key) || null;
}

function StudentQualityPortraitPage() {
  const { studentId: routeStudentId } = useParams<{ studentId?: string }>();
  const [studentId, setStudentId] = useState(routeStudentId || '');
  const [portrait, setPortrait] = useState<StudentQualityPortraitResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    setStudentId(routeStudentId || '');
  }, [routeStudentId]);

  const overallScoreLabel = useMemo(() => buildOverallScoreLabel(portrait), [portrait]);

  async function handleQuery() {
    const normalizedStudentId = studentId.trim();
    if (!normalizedStudentId) {
      setErrorMessage('请输入学生画像 ID');
      setPortrait(null);
      return;
    }

    setLoading(true);
    setErrorMessage('');
    try {
      const nextPortrait = await fetchStudentQualityPortrait(normalizedStudentId);
      setPortrait(nextPortrait);
    } catch (error) {
      setPortrait(null);
      setErrorMessage(error instanceof Error ? error.message : '单学生质量画像加载失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f5f8fb] font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif] text-[#1f2d3d]">
      <header role="banner" className="flex h-[58px] items-center justify-center bg-[#1f3f63] px-6 text-[22px] font-bold text-white">
        单学生本地质量画像
      </header>

      <section className="mx-7 mt-4 border border-[#d9e1ea] bg-[#eef5fb] px-4 py-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid gap-2 text-[14px] font-semibold text-[#1f3f63]">
            学生画像 ID
            <input
              aria-label="学生画像 ID"
              className="h-10 min-w-[260px] rounded border border-[#d9e1ea] bg-white px-3 text-[14px] font-normal outline-none focus:border-[#2f80ed]"
              placeholder="请输入学生本人或授权范围内学生 ID"
              value={studentId}
              onChange={(event) => setStudentId(event.target.value)}
            />
          </label>
          <button
            className="h-10 rounded bg-[#2f80ed] px-8 text-[14px] font-bold text-white"
            type="button"
            onClick={() => void handleQuery()}
          >
            查询
          </button>
          <a className="h-10 rounded border border-[#d9e1ea] bg-white px-5 pt-2 text-[14px] font-bold text-[#1f3f63]" href="/quality-dashboard">
            返回群体仪表盘
          </a>
        </div>
      </section>

      {loading ? <p className="py-14 text-center text-[#536476]">质量画像加载中...</p> : null}
      {!loading && errorMessage ? <p className="py-14 text-center text-red-600">{errorMessage}</p> : null}
      {!loading && !errorMessage && !portrait ? (
        <p className="py-14 text-center text-[#536476]">请输入学生 ID 后查看该学生最新完成记录画像</p>
      ) : null}

      {portrait ? (
        <section className="mx-7 my-5 overflow-hidden border border-[#d9e1ea] bg-white shadow-sm">
          <h2 className="bg-[#1f3f63] px-5 py-3 text-[18px] font-bold text-white">单学生论文全景质量画像</h2>
          <div className="grid gap-5 p-5 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-4">
              <div className="grid gap-3 rounded border border-[#d9e1ea] bg-[#eaf4ff] p-4 md:grid-cols-3">
                <p><span className="text-[#536476]">学号：</span><strong>{portrait.student.student_number}</strong></p>
                <p><span className="text-[#536476]">姓名：</span><strong>{portrait.student.student_name}</strong></p>
                <p><span className="text-[#536476]">学院：</span><strong>{portrait.student.college_name}</strong></p>
                <p><span className="text-[#536476]">导师：</span><strong>{portrait.student.supervisor_name || '暂无'}</strong></p>
                <p className="md:col-span-2"><span className="text-[#536476]">论文题目：</span><strong>{portrait.student.thesis_title || '暂无最新论文题目'}</strong></p>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {portrait.metrics.map((metric) => (
                  <article key={metric.key} className="rounded border border-[#d9e1ea] bg-white p-4 text-center">
                    <p className="text-[14px] text-[#536476]">{metric.label}</p>
                    <div className="mt-2 flex items-end justify-center gap-1 text-[#1f3f63]">
                      <strong className="text-[28px] font-bold">{formatScore(metric.score)}</strong>
                      {metric.score !== null ? <span className="pb-1 text-[13px] text-[#536476]">分</span> : null}
                    </div>
                    <p className="mt-2 text-[12px] text-[#536476]">{formatSourceTime(metric.source_created_at)}</p>
                    {metric.detail_url ? (
                      <a className="mt-2 inline-flex text-[13px] font-semibold text-[#2f80ed]" href={metric.detail_url}>
                        查看详情
                      </a>
                    ) : null}
                  </article>
                ))}
              </div>

              <article className="rounded border border-[#d9e1ea] bg-[#f8fafc] p-4">
                <p className="text-[14px] text-[#536476]">综合分</p>
                <div className="mt-2 flex items-end gap-1">
                  <strong className={`text-[30px] font-bold ${portrait.completeness.complete ? 'text-[#19a85b]' : 'text-[#f39a2e]'}`}>
                    {overallScoreLabel}
                  </strong>
                </div>
                {!portrait.completeness.complete ? (
                  <p className="mt-2 text-[14px] text-[#f39a2e]">
                    缺失项：{portrait.completeness.missing_metric_labels.join('、') || '无'}
                  </p>
                ) : null}
              </article>
            </div>

            <div className="space-y-4">
              <article className="rounded border border-[#d9e1ea] bg-white p-5">
                <h3 className="mb-4 text-[18px] font-bold text-[#1f3f63]">四指标雷达图</h3>
                <div className="grid min-h-[260px] place-items-center rounded border border-dashed border-[#c8d3df] bg-[#f8fbff] px-4 text-center text-[#536476]">
                  <div>
                    <p className="font-semibold">雷达图占位区</p>
                    <p className="mt-2 text-[13px]">运行时将根据四项指标数据绘制质量雷达图。</p>
                  </div>
                </div>
              </article>

              <article className="rounded border border-[#d9e1ea] bg-white p-5">
                <h3 className="text-[18px] font-bold text-[#1f3f63]">指标完整性</h3>
                <ul className="mt-3 grid gap-2 text-[14px] text-[#536476]">
                  <li>规范性：{getMetricByKey(portrait.metrics, 'normative')?.source_label || '暂无'}</li>
                  <li>原创性：{getMetricByKey(portrait.metrics, 'originality')?.source_label || '暂无'}</li>
                  <li>创新性：{getMetricByKey(portrait.metrics, 'innovation')?.source_label || '暂无'}</li>
                  <li>评阅基础：{getMetricByKey(portrait.metrics, 'review_base')?.source_label || '暂无'}</li>
                </ul>
              </article>
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default StudentQualityPortraitPage;
