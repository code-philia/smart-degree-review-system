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
  const [levels, setLevels] = useState<Record<InnovationScoreDimensionKey, number>>(DEFAULT_LEVELS);
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
    return (
      <main className="min-h-screen bg-[#FEFDFB] px-6 py-12">
        <section className="mx-auto max-w-4xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">创新性评分</h1>
          <p className="mt-3 text-sm font-semibold text-slate-500">正在加载登录状态…</p>
        </section>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#FEFDFB] px-6 py-12">
        <section className="mx-auto max-w-4xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">创新性评分</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后计算创新性分数，系统将按当前账号权限调用后台评分服务。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#FEFDFB] px-6 py-10">
      <section className="mx-auto max-w-5xl rounded-[28px] border border-[#B8B8B8] bg-white p-8 shadow-sm">
        <h1 className="text-3xl font-black text-[#111111]">创新性评分</h1>
        <p className="mt-3 text-sm font-semibold text-slate-600">当前登录用户：{user.username}（{user.role}）</p>
        <p className="mt-2 text-sm font-semibold text-slate-600">选择博士或硕士权重，并为五个维度选择 1-5 级。</p>

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
                {dimension.label}等级
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
          {errorMessage ? <p className="text-sm font-semibold text-red-600" role="alert">{errorMessage}</p> : null}
        </form>

        {report ? (
          <section className="mt-8 rounded-2xl border border-blue-100 bg-blue-50 p-5" aria-labelledby="innovation-score-report-heading">
            <div className="flex flex-wrap items-end gap-4">
              <h2 id="innovation-score-report-heading" className="text-2xl font-black text-blue-950">创新性评分报告</h2>
              <p className="text-3xl font-black text-blue-700">{report.total_score} 分</p>
              <p className="rounded-full bg-white px-4 py-2 text-base font-black text-blue-900">{report.grade_label}</p>
            </div>
            <p className="mt-4 text-sm font-bold text-blue-900">公式：{report.formula}</p>
            <p className="mt-2 text-sm font-semibold text-slate-700">
              本次输入：{report.degree_type === 'master' ? '硕士' : '博士'}；
              {report.dimensions.map((dimension) => `${dimension.label}${report.input.levels[dimension.key]}级`).join('，')}
            </p>
            <div className="mt-5 overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm" aria-label="创新性评分明细">
                <thead>
                  <tr className="border-b border-blue-200 text-slate-600">
                    <th className="py-3 pr-4 font-black">维度</th>
                    <th className="py-3 pr-4 font-black">输入等级</th>
                    <th className="py-3 pr-4 font-black">原始分</th>
                    <th className="py-3 pr-4 font-black">权重</th>
                    <th className="py-3 pr-4 font-black">加权贡献</th>
                  </tr>
                </thead>
                <tbody>
                  {report.dimensions.map((dimension) => (
                    <tr key={dimension.key} className="border-b border-blue-100 last:border-0">
                      <td className="py-3 pr-4 font-black text-slate-900">{dimension.label}</td>
                      <td className="py-3 pr-4 font-semibold text-slate-700">{dimension.level}</td>
                      <td className="py-3 pr-4 font-semibold text-slate-700">{dimension.raw_score}</td>
                      <td className="py-3 pr-4 font-semibold text-slate-700">{dimension.weight * 100}%</td>
                      <td className="py-3 pr-4 font-semibold text-slate-700">{dimension.weighted_score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}
      </section>
    </main>
  );
}

export default InnovationScoringPage;
