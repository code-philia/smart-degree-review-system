import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  downloadInnovationReportJson,
  fetchInnovationReport,
  type InnovationAssessmentResponse,
  type InnovationScoreDimensionReport,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';

type InnovationReportSection = 'basic' | 'radar' | 'heatmap' | 'dimensions' | 'summary';

type SectionConfig = {
  key: InnovationReportSection;
  label: string;
  heading: string;
};

const REPORT_TABS: SectionConfig[] = [
  { key: 'basic', label: '基本信息', heading: '第一部分 · 基本信息' },
  { key: 'radar', label: '核心指标雷达图', heading: '第二部分 · 核心指标雷达图' },
  { key: 'heatmap', label: '子指标热力图', heading: '第三部分 · 子指标热力图' },
  { key: 'dimensions', label: '分项评价', heading: '第四部分 · 分项评价' },
  { key: 'summary', label: '综合评价与建议', heading: '第五部分 · 综合评价与建议' },
];

const DIMENSION_LABELS: Record<string, string> = {
  research_topic: '研究选题',
  research_method: '研究方法',
  research_content: '研究内容',
  research_conclusion: '研究结论',
  application_value: '应用价值',
};

function formatPercent(weight: number) {
  return `${Math.round(weight * 100)}%`;
}

function formatTimestamp(value: string) {
  return value ? value.replace('T', ' ').replace('Z', '') : '—';
}

function formatScore(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function gradeTone(gradeLabel: InnovationAssessmentResponse['grade_label']) {
  switch (gradeLabel) {
    case '优秀':
      return 'bg-[#27B46A] text-white';
    case '良好':
      return 'bg-[#2F86F6] text-white';
    case '一般':
      return 'bg-amber-500 text-white';
    default:
      return 'bg-orange-500 text-white';
  }
}

function buildRadarPoints(dimensions: InnovationScoreDimensionReport[]) {
  const size = 320;
  const center = size / 2;
  const radius = 120;
  const angleOffset = -Math.PI / 2;

  return dimensions.map((dimension, index) => {
    const angle = angleOffset + (Math.PI * 2 * index) / dimensions.length;
    const distance = radius * (dimension.level / 5);
    return {
      ...dimension,
      x: center + Math.cos(angle) * distance,
      y: center + Math.sin(angle) * distance,
      axisX: center + Math.cos(angle) * radius,
      axisY: center + Math.sin(angle) * radius,
    };
  });
}

function InnovationReportPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const { status, user } = useAuthSession();
  const [activeSection, setActiveSection] = useState<InnovationReportSection>('basic');
  const [report, setReport] = useState<InnovationAssessmentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeTab = useMemo(
    () => REPORT_TABS.find((tab) => tab.key === activeSection) || REPORT_TABS[0],
    [activeSection],
  );

  const radarPoints = useMemo(() => (report ? buildRadarPoints(report.dimensions) : []), [report]);

  useEffect(() => {
    if (status !== 'authenticated' || !user || !reportId) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    setReport(null);

    fetchInnovationReport(reportId)
      .then((nextReport) => {
        if (!cancelled) {
          setReport(nextReport);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '创新性量表报告加载失败');
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

  async function handleDownloadJson() {
    if (!reportId || !report) {
      return;
    }

    const blob = await downloadInnovationReportJson(reportId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `innovation-report-${reportId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (status === 'loading') {
    return (
      <main className="min-h-screen bg-[#F7F9FB] p-8 text-slate-700">
        <div className="mx-auto max-w-6xl rounded-xl border border-[#E5E8EC] bg-white p-6">正在加载登录状态…</div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#F7F9FB] p-8 font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif] text-[#1F2D3D]">
        <h1 className="text-center text-[30px] font-black text-[#1F3F63]">学位论文创新性分析报告</h1>
        <p className="mt-4 text-center text-[15px] text-slate-600">请先登录后查看已完成的创新性量表报告。</p>
        <div className="mt-6 flex justify-center">
          <Link className="inline-flex rounded bg-[#2F86F6] px-5 py-3 font-bold text-white" to="/auth">
            前往登录
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F7F9FB] font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif] text-[#1F2D3D]">
      <header className="flex h-16 items-center justify-center bg-[#1F3F63] px-6">
        <h1 className="text-center text-[30px] font-black tracking-wide text-white">学位论文创新性分析报告</h1>
      </header>

      <nav className="grid h-10 grid-cols-5 divide-x divide-white" aria-label="创新性报告章节">
        {REPORT_TABS.map((tab) => (
          <button
            key={tab.key}
            className={`h-10 px-2 text-[16px] font-bold transition ${activeSection === tab.key ? 'bg-[#2F86F6] text-white' : 'bg-[#EEF3F8] text-[#8A8F98] hover:text-[#1F3F63]'}`}
            type="button"
            onClick={() => setActiveSection(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <section className="flex min-h-[52px] items-center justify-between bg-[#EEF3F8] px-5">
        <h2 className="text-lg font-black text-[#1F3F63]">{activeTab.heading}</h2>
        <div className="flex gap-3 print:hidden">
          <button
            className="rounded border border-[#2F86F6] px-4 py-2 text-sm font-bold text-[#2F86F6] disabled:cursor-not-allowed disabled:opacity-50"
            type="button"
            disabled={!report}
            onClick={handleDownloadJson}
          >
            下载 UTF-8 JSON
          </button>
          <button
            className="rounded bg-[#2F86F6] px-4 py-2 text-sm font-bold text-white"
            type="button"
            onClick={() => window.print()}
          >
            浏览器打印
          </button>
        </div>
      </section>

      <section className="px-6 py-5">
        {loading ? (
          <div className="space-y-4">
            <div className="h-48 animate-pulse rounded-xl border border-[#E5E8EC] bg-white" />
            <div className="h-24 animate-pulse rounded-xl border border-[#E5E8EC] bg-white" />
          </div>
        ) : null}

        {errorMessage ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 font-bold text-red-700" role="alert">
            {errorMessage}
          </div>
        ) : null}

        {!loading && !errorMessage && !report ? (
          <div className="rounded-xl border border-[#E5E8EC] bg-white p-6 text-slate-500">暂无可展示的创新性量表报告。</div>
        ) : null}

        {report ? (
          <div className="space-y-5">
            <section className="rounded-xl border border-[#E5E8EC] bg-white p-6" data-testid="innovation-report-basic-info">
              <div className="grid gap-0 divide-y divide-[#E5E8EC] text-[15px]">
                <div className="grid gap-4 py-4 lg:grid-cols-[1.4fr_0.9fr]">
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">论文题目</div>
                    <div className="truncate font-bold text-[#1F2D3D]" title={report.thesis_title}>{report.thesis_title}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">报告编号</div>
                    <div className="truncate font-bold text-[#1F2D3D]" title={report.id}>{report.id}</div>
                  </div>
                </div>

                <div className="grid gap-4 py-4 lg:grid-cols-[1.4fr_0.9fr]">
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">一级学科</div>
                    <div className="truncate font-bold text-[#1F2D3D]" title={report.primary_discipline}>{report.primary_discipline}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">学位类型</div>
                    <div className="truncate font-bold text-[#1F2D3D]">{report.degree_type === 'doctoral' ? '博士' : '硕士'}</div>
                  </div>
                </div>

                <div className="grid gap-4 py-4 lg:grid-cols-[1.4fr_0.9fr]">
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">二级学科</div>
                    <div className="truncate font-bold text-[#1F2D3D]" title={report.secondary_discipline}>{report.secondary_discipline}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">学生编号</div>
                    <div className="truncate font-bold text-[#1F2D3D]" title={report.user_id}>{report.user_id}</div>
                  </div>
                </div>

                <div className="grid gap-4 py-4 lg:grid-cols-[1.4fr_0.9fr]">
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">研究方向</div>
                    <div className="truncate font-bold text-[#1F2D3D]" title={report.research_direction}>{report.research_direction}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="text-[#8A8F98]">报告生成时间</div>
                    <div className="truncate font-bold text-[#1F2D3D]" title={report.created_at}>{formatTimestamp(report.created_at)}</div>
                  </div>
                </div>
              </div>
            </section>

            <section className="rounded-[6px] border-2 border-[#2F86F6] bg-[#EAF4FF] px-5 py-4">
              <div className="grid gap-4 lg:grid-cols-[1fr_auto_1fr] lg:items-stretch">
                <div className="flex min-h-[90px] flex-col items-center justify-center text-center">
                  <div className="text-sm font-bold text-[#1F3F63]">综合创新性等级</div>
                  <div
                    className={`mt-3 inline-flex min-w-28 justify-center rounded-[8px] px-6 py-3 text-[22px] font-black ${gradeTone(report.grade_label)}`}
                    data-testid="innovation-report-grade"
                  >
                    {report.grade_label}
                  </div>
                </div>
                <div className="hidden w-px bg-[#B7CAE6] lg:block" />
                <div className="flex min-h-[90px] flex-col items-center justify-center text-center">
                  <div className="text-sm font-bold text-[#1F3F63]">综合创新得分</div>
                  <div className="mt-2 flex items-end gap-1 text-[#2F86F6]">
                    <span className="text-[44px] font-black leading-none" data-testid="innovation-report-total-score">
                      {formatScore(report.total_score)}
                    </span>
                    <span className="pb-1 text-[16px] font-bold">/100 分</span>
                  </div>
                </div>
              </div>
            </section>

            {activeSection === 'radar' ? (
              <section className="rounded-xl border border-[#E5E8EC] bg-white p-6">
                <div className="mb-4 text-[18px] font-black text-[#1F3F63]">五维创新性雷达图</div>
                <svg
                  aria-label="五维创新性雷达图"
                  role="img"
                  viewBox="0 0 320 320"
                  className="mx-auto block max-w-full"
                >
                  <defs>
                    <linearGradient id="innovation-radar-fill" x1="0%" x2="0%" y1="0%" y2="100%">
                      <stop offset="0%" stopColor="#2F86F6" stopOpacity="0.35" />
                      <stop offset="100%" stopColor="#2F86F6" stopOpacity="0.12" />
                    </linearGradient>
                  </defs>
                  {[24, 48, 72, 96, 120].map((radius) => (
                    <circle key={radius} cx="160" cy="160" r={radius} fill="none" stroke="#DDE6F0" strokeWidth="1" />
                  ))}
                  {radarPoints.map((dimension) => (
                    <line key={`${dimension.key}-axis`} x1="160" y1="160" x2={dimension.axisX} y2={dimension.axisY} stroke="#DDE6F0" strokeWidth="1" />
                  ))}
                  <polygon
                    points={radarPoints.map((dimension) => `${dimension.x},${dimension.y}`).join(' ')}
                    fill="url(#innovation-radar-fill)"
                    stroke="#2F86F6"
                    strokeWidth="3"
                  />
                  {radarPoints.map((dimension) => (
                    <g key={dimension.key} data-testid={`innovation-report-radar-dimension-${dimension.key}`} data-level={dimension.level} data-weighted-score={dimension.weighted_score}>
                      <circle cx={dimension.x} cy={dimension.y} r="5" fill="#2F86F6" />
                      <text x={dimension.axisX} y={dimension.axisY} fill="#1F2D3D" fontSize="13" fontWeight="700" textAnchor="middle" dominantBaseline="middle">
                        {dimension.label}
                      </text>
                    </g>
                  ))}
                </svg>
              </section>
            ) : null}

            {activeSection === 'heatmap' ? (
              <section className="rounded-xl border border-[#E5E8EC] bg-white p-6">
                <div className="mb-4 text-[18px] font-black text-[#1F3F63]">五维评级热力矩阵</div>
                <div className="overflow-hidden rounded-lg border border-[#E5E8EC]">
                  <table className="min-w-full text-left text-[15px]" aria-label="五维评级热力矩阵">
                    <thead className="bg-[#EEF3F8] text-[#1F3F63]">
                      <tr>
                        <th className="px-4 py-3">维度</th>
                        <th className="px-4 py-3">等级</th>
                        <th className="px-4 py-3">原始分</th>
                        <th className="px-4 py-3">权重</th>
                        <th className="px-4 py-3">加权分</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.dimensions.map((dimension, index) => {
                        const tone =
                          dimension.level >= 5
                            ? 'bg-[#DFF6E9] text-[#1E7B43]'
                            : dimension.level >= 4
                              ? 'bg-[#EAF4FF] text-[#1F3F63]'
                              : dimension.level >= 3
                                ? 'bg-[#FFF4DF] text-[#9A6110]'
                                : 'bg-[#FDE8E8] text-[#C12B2B]';
                        return (
                          <tr
                            key={dimension.key}
                            className={index % 2 === 0 ? 'bg-white' : 'bg-[#FAFBFC]'}
                            data-testid={`innovation-report-heatmap-dimension-${dimension.key}`}
                            data-weighted-score={dimension.weighted_score}
                          >
                            <td className="px-4 py-3 font-bold text-[#1F2D3D]">{dimension.label}</td>
                            <td className="px-4 py-3">
                              <span className={`inline-flex rounded px-2 py-1 text-sm font-bold ${tone}`}>{dimension.level}</span>
                            </td>
                            <td className="px-4 py-3">{dimension.raw_score}</td>
                            <td className="px-4 py-3">{formatPercent(dimension.weight)}</td>
                            <td className="px-4 py-3 font-bold text-[#2F86F6]">{formatScore(dimension.weighted_score)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            ) : null}

            {activeSection === 'dimensions' ? (
              <section className="space-y-4 rounded-xl border border-[#E5E8EC] bg-white p-6">
                <div className="text-[18px] font-black text-[#1F3F63]">分项评价</div>
                {report.dimensions.map((dimension) => {
                  const input = report.input_snapshot.dimensions[dimension.key];
                  return (
                    <article key={dimension.key} className="rounded-lg border border-[#E5E8EC] bg-[#FAFBFC] p-4" data-testid={`innovation-report-dimension-text-${dimension.key}`}>
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <h3 className="text-[16px] font-black text-[#1F2D3D]">{dimension.label}</h3>
                        <div className="text-sm font-bold text-[#1F3F63]">
                          等级 {dimension.level} · 权重 {formatPercent(dimension.weight)} · 加权分 {formatScore(dimension.weighted_score)}
                        </div>
                      </div>
                      <div className="mt-3 grid gap-3 text-[15px] leading-7 text-[#374151] lg:grid-cols-2">
                        <div>
                          <span className="font-bold text-[#8A8F98]">证据：</span>
                          <span className="break-words">{input?.evidence || '—'}</span>
                        </div>
                        <div>
                          <span className="font-bold text-[#8A8F98]">改进计划：</span>
                          <span className="break-words">{input?.improvement_plan || '—'}</span>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </section>
            ) : null}

            {activeSection === 'summary' ? (
              <section className="space-y-4 rounded-xl border border-[#E5E8EC] bg-white p-6">
                <div className="text-[18px] font-black text-[#1F3F63]">综合评价与建议</div>
                <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
                  <div className="rounded-xl border border-[#E5E8EC] bg-[#FAFBFC] p-4">
                    <div className="text-sm font-bold text-[#8A8F98]">权重公式</div>
                    <div className="mt-2 text-[15px] leading-7 text-[#1F2D3D]" data-testid="innovation-report-formula">
                      {report.formula}
                    </div>
                  </div>
                  <div className="rounded-xl border border-[#E5E8EC] bg-[#FAFBFC] p-4">
                    <div className="text-sm font-bold text-[#8A8F98]">综合结果</div>
                    <div className="mt-3 flex flex-wrap items-center gap-4">
                      <span className={`inline-flex rounded-[8px] px-5 py-2 text-[20px] font-black ${gradeTone(report.grade_label)}`} data-testid="innovation-report-summary-grade">
                        {report.grade_label}
                      </span>
                      <span className="text-[#2F86F6]">
                        <span className="text-[36px] font-black leading-none" data-testid="innovation-report-summary-score">
                          {formatScore(report.total_score)}
                        </span>
                        <span className="ml-1 text-[16px] font-bold">/100 分</span>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-[#E5E8EC] bg-[#FAFBFC] p-4">
                  <div className="text-sm font-bold text-[#8A8F98]">综合建议</div>
                  <ul className="mt-3 space-y-3 text-[15px] leading-7 text-[#374151]">
                    {report.dimensions.map((dimension) => (
                      <li key={`${dimension.key}-summary`}>
                        <span className="font-bold text-[#1F2D3D]">{dimension.label}：</span>
                        <span>{report.input_snapshot.dimensions[dimension.key]?.improvement_plan || '—'}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="rounded-xl border border-[#E5E8EC] bg-[#FAFBFC] p-4 text-[14px] leading-7 text-[#6B7280]" data-testid="innovation-report-disclaimer">
                  {report.disclaimer}
                </div>
              </section>
            ) : null}

            {activeSection === 'basic' ? (
              <section className="rounded-xl border border-[#E5E8EC] bg-white p-6">
                <div className="text-[18px] font-black text-[#1F3F63]">报告说明</div>
                <p className="mt-3 text-[15px] leading-7 text-[#374151]">本页内容全部来自运行时获取的创新性评估报告，支持图表、矩阵、证据与建议的同步查看。</p>
              </section>
            ) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}

export default InnovationReportPage;
