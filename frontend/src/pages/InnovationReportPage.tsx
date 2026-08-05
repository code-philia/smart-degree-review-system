import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  downloadInnovationReportJson,
  fetchInnovationReport,
  type InnovationAssessmentResponse,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';

type InnovationReportSection = 'basic' | 'radar' | 'heatmap' | 'dimensions' | 'summary';

const REPORT_TABS: Array<{ key: InnovationReportSection; label: string; heading: string }> = [
  { key: 'basic', label: '基本信息', heading: '第一部分 · 基本信息' },
  { key: 'radar', label: '核心指标雷达图', heading: '第二部分 · 核心指标雷达图' },
  { key: 'heatmap', label: '子指标热力图', heading: '第三部分 · 子指标热力图' },
  { key: 'dimensions', label: '分项评价', heading: '第四部分 · 分项评价' },
  { key: 'summary', label: '综合评价与建议', heading: '第五部分 · 综合评价与建议' },
];

function InnovationReportPage() {
  const { reportId } = useParams();
  const { status, user } = useAuthSession();
  const [activeSection, setActiveSection] = useState<InnovationReportSection>('basic');
  const [report, setReport] = useState<InnovationAssessmentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const activeTab = useMemo(
    () => REPORT_TABS.find((tab) => tab.key === activeSection) || REPORT_TABS[0],
    [activeSection],
  );

  useEffect(() => {
    if (status !== 'authenticated' || !user || !reportId) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
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
    if (!reportId) {
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
    return <main className="min-h-screen bg-[#F7F9FB] p-8 text-slate-700">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#F7F9FB] p-8">
        <h1 className="text-2xl font-black text-[#1F3F63]">学位论文创新性分析报告</h1>
        <p className="mt-4 text-slate-600">请先登录后查看已完成的创新性量表报告。</p>
        <Link className="mt-6 inline-flex rounded bg-[#2F86F6] px-5 py-3 font-bold text-white" to="/auth">前往登录</Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F7F9FB] font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif] text-[#1F2D3D]">
      <header className="flex h-16 items-center justify-center bg-[#1F3F63] px-6">
        <h1 className="text-center text-[30px] font-black tracking-wide text-white">学位论文创新性分析报告</h1>
      </header>

      <nav className="grid grid-cols-5" aria-label="创新性报告章节">
        {REPORT_TABS.map((tab) => (
          <button
            key={tab.key}
            className={`h-10 border-r border-white text-base font-bold transition ${activeSection === tab.key ? 'bg-[#2F86F6] text-white' : 'bg-[#EEF3F8] text-[#8A8F98] hover:text-[#1F3F63]'}`}
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
          <button className="rounded border border-[#2F86F6] px-4 py-2 text-sm font-bold text-[#2F86F6] disabled:opacity-50" type="button" disabled={!report} onClick={handleDownloadJson}>下载 JSON</button>
          <button className="rounded bg-[#2F86F6] px-4 py-2 text-sm font-bold text-white" type="button" onClick={() => window.print()}>浏览器打印</button>
        </div>
      </section>

      <section className="px-6 py-5">
        {loading ? <div className="rounded-xl border border-[#E5E8EC] bg-white p-6 text-slate-500">正在加载报告数据…</div> : null}
        {errorMessage ? <div className="rounded-xl border border-red-200 bg-red-50 p-6 font-bold text-red-700" role="alert">{errorMessage}</div> : null}
        {!loading && !errorMessage && !report ? <div className="rounded-xl border border-[#E5E8EC] bg-white p-6 text-slate-500">暂无可展示的创新性量表报告。</div> : null}
        {report ? <div className="rounded-xl border border-dashed border-[#B7CAE6] bg-white p-6 text-slate-600">报告内容区域由后续实现绑定基本信息、SVG 雷达图、CSS 热力矩阵、证据、改进计划、权重公式、综合分和声明。</div> : null}
      </section>
    </main>
  );
}

export default InnovationReportPage;
