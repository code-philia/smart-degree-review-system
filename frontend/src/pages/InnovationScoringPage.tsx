import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  calculateInnovationScore,
  type InnovationDegreeType,
  type InnovationScoreDimensionKey,
  type InnovationScoreResponse,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';

const DIMENSIONS: Array<{ key: InnovationScoreDimensionKey; label: string }> = [
  { key: 'research_topic', label: '研究选题' },
  { key: 'research_method', label: '研究方法' },
  { key: 'research_content', label: '研究内容' },
  { key: 'research_conclusion', label: '研究结论' },
  { key: 'application_value', label: '应用价值' },
];

const DEFAULT_LEVELS: Record<InnovationScoreDimensionKey, number> = {
  research_topic: 3,
  research_method: 3,
  research_content: 3,
  research_conclusion: 3,
  application_value: 3,
};

function InnovationScoringPage() {
  const { status, user } = useAuthSession();
  const [degreeType, setDegreeType] = useState<InnovationDegreeType>('master');
  const [levels, setLevels] = useState(DEFAULT_LEVELS);
  const [report, setReport] = useState<InnovationScoreResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setErrorMessage(null);
    setReport(null);

    try {
      const result = await calculateInnovationScore({ degree_type: degreeType, levels });
      setReport(result);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '创新性评分失败');
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') {
    return <main className="px-6 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">创新性固定透明评分</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后按五个维度计算创新性综合分。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#FEFDFB] px-6 py-10">
      <section className="mx-auto max-w-5xl rounded-[28px] border border-[#B8B8B8] bg-white p-8">
        <h1 className="text-3xl font-black text-[#111111]">创新性固定透明评分</h1>
        <p className="mt-3 text-sm font-semibold text-slate-600">选择博士或硕士权重，并为五个维度选择 1-5 级。</p>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <label className="block text-sm font-black text-slate-800">
            学位类型
            <select
              className="mt-2 h-12 w-full rounded-xl border border-slate-300 px-4 text-sm font-semibold outline-none focus:border-blue-500"
              value={degreeType}
              onChange={(event) => setDegreeType(event.target.value as InnovationDegreeType)}
            >
              <option value="master">硕士</option>
              <option value="doctoral">博士</option>
            </select>
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            {DIMENSIONS.map((dimension) => (
              <label key={dimension.key} className="block rounded-2xl border border-slate-200 p-4 text-sm font-black text-slate-800">
                {dimension.label}
                <select
                  className="mt-2 h-12 w-full rounded-xl border border-slate-300 px-4 text-sm font-semibold outline-none focus:border-blue-500"
                  value={levels[dimension.key]}
                  onChange={(event) => setLevels((current) => ({ ...current, [dimension.key]: Number(event.target.value) }))}
                >
                  {[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level} 级</option>)}
                </select>
              </label>
            ))}
          </div>

          <button
            className="h-14 rounded-full bg-[#2448E8] px-10 text-lg font-black text-white shadow-[0_5px_0_#1736C8] disabled:cursor-not-allowed disabled:opacity-50"
            type="submit"
            disabled={submitting}
          >
            {submitting ? '计算中…' : '计算创新性分数'}
          </button>
          {errorMessage ? <p className="text-sm font-semibold text-red-600">{errorMessage}</p> : null}
        </form>

        {report ? (
          <section className="mt-8 rounded-2xl border border-blue-100 bg-blue-50 p-5">
            <h2 className="text-2xl font-black text-blue-900">{report.total_score} 分 · {report.grade_label}</h2>
            <p className="mt-3 text-sm font-bold text-blue-900">公式：{report.formula}</p>
            <ul className="mt-4 space-y-2 text-sm font-semibold text-slate-700">
              {report.dimensions.map((dimension) => (
                <li key={dimension.key}>{dimension.label}：{dimension.level} 级 × 20 = {dimension.raw_score}，权重 {Math.round(dimension.weight * 100)}%，加权 {dimension.weighted_score}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </section>
    </main>
  );
}

export default InnovationScoringPage;
