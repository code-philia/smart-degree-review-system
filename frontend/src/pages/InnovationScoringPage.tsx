import { FormEvent, useState } from 'react';
import { Calculator, CheckCircle2, Info, Sparkles } from 'lucide-react';
import {
  calculateInnovationScore,
  type InnovationDegreeType,
  type InnovationScoreDimensionKey,
  type InnovationScoreResponse,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Button, Card, ErrorState, LinkButton, LoadingState, PageHeader } from '../components/ui';

const DIMENSIONS: Array<{ key: InnovationScoreDimensionKey; label: string; hint: string }> = [
  { key: 'research_topic', label: '研究选题', hint: '问题价值与前沿性' },
  { key: 'research_method', label: '研究方法', hint: '方法设计与适配性' },
  { key: 'research_content', label: '研究内容', hint: '研究发现与原创性' },
  { key: 'research_conclusion', label: '研究结论', hint: '结论贡献与可信度' },
  { key: 'application_value', label: '应用价值', hint: '实践转化与推广价值' },
];

const DEFAULT_LEVELS: Record<InnovationScoreDimensionKey, number> = {
  research_topic: 3,
  research_method: 3,
  research_content: 3,
  research_conclusion: 3,
  application_value: 3,
};

function scoreTone(score: number) {
  if (score >= 90) return 'text-emerald-600';
  if (score >= 80) return 'text-brand-600';
  if (score >= 60) return 'text-amber-600';
  return 'text-rose-600';
}

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
      setReport(await calculateInnovationScore({ degree_type: degreeType, levels }));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '创新性评分失败');
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') return <LoadingState label="正在加载登录状态…" />;

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card className="p-8">
          <h1 className="text-2xl font-bold text-slate-900">创新性评分</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            请先登录后计算创新性分数，系统将按当前账号权限调用后台评分服务。
          </p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl pb-8">
      <PageHeader
        eyebrow="透明评分工具"
        title="创新性评分"
        description="选择学位类型与五项自评等级，系统按固定权重生成可追溯的参考分。"
        actions={
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-500">
            当前账号：{user.username}
          </span>
        }
      />

      <form onSubmit={handleSubmit}>
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
          <Card className="overflow-hidden p-0">
            <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <Calculator size={18} />
                </span>
                <div>
                  <h2 className="font-semibold text-slate-900">评分配置</h2>
                  <p className="mt-0.5 text-xs text-slate-500">每项按 1–5 级选择，等级越高代表自评表现越好。</p>
                </div>
              </div>
            </div>
            <div className="space-y-5 p-5 sm:p-6">
              <fieldset>
                <legend className="text-sm font-semibold text-slate-800">学位类型</legend>
                <div className="mt-2 grid max-w-sm grid-cols-2 rounded-lg bg-slate-100 p-1">
                  {(
                    [
                      ['master', '硕士', '20% / 20% / 25% / 20% / 15%'],
                      ['doctoral', '博士', '25% / 25% / 20% / 20% / 10%'],
                    ] as const
                  ).map(([value, label, weight]) => (
                    <label key={value} className="cursor-pointer">
                      <input
                        className="peer sr-only"
                        type="radio"
                        name="degreeType"
                        value={value}
                        checked={degreeType === value}
                        onChange={() => setDegreeType(value)}
                      />
                      <span className="block rounded-md px-3 py-2 text-center transition peer-checked:bg-white peer-checked:shadow-sm">
                        <span className="block text-sm font-semibold text-slate-700">{label}</span>
                        <span className="mt-0.5 block text-[10px] text-slate-400">{weight}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="grid gap-3 sm:grid-cols-2">
                {DIMENSIONS.map((dimension, index) => (
                  <label
                    key={dimension.key}
                    className={`group flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 transition hover:border-brand-200 ${index === DIMENSIONS.length - 1 ? 'sm:col-span-2' : ''}`}
                  >
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-slate-800">{dimension.label}</span>
                      <span className="mt-0.5 block truncate text-xs text-slate-500">{dimension.hint}</span>
                    </span>
                    <span className="relative shrink-0">
                      <select
                        aria-label={`${dimension.label}等级`}
                        className="h-9 min-w-20 appearance-none rounded-lg border border-slate-200 bg-slate-50 py-0 pl-3 pr-7 text-sm font-semibold text-slate-700 outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                        value={levels[dimension.key]}
                        onChange={(event) =>
                          setLevels((current) => ({ ...current, [dimension.key]: Number(event.target.value) }))
                        }
                      >
                        {[1, 2, 3, 4, 5].map((level) => (
                          <option key={level} value={level}>
                            {level} 级
                          </option>
                        ))}
                      </select>
                      <span
                        aria-hidden="true"
                        className="pointer-events-none absolute right-2 top-2.5 text-[10px] text-slate-400"
                      >
                        ⌄
                      </span>
                    </span>
                  </label>
                ))}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
                <p className="text-xs text-slate-500">本工具提供量表参考分，不代替专家评审或文献查新。</p>
                <Button size="lg" type="submit" disabled={submitting}>
                  <Sparkles size={16} />
                  {submitting ? '正在计算…' : '计算创新性分数'}
                </Button>
              </div>
              {errorMessage ? <ErrorState title="计算失败" message={errorMessage} /> : null}
            </div>
          </Card>

          <aside className="rounded-xl border border-brand-100 bg-brand-50/60 p-5">
            <div className="flex items-center gap-2 text-brand-700">
              <Info size={17} />
              <h2 className="text-sm font-semibold">评分说明</h2>
            </div>
            <ol className="mt-4 space-y-4 text-sm leading-6 text-slate-600">
              <li className="flex gap-3">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-brand-600">
                  1
                </span>
                <span>五项等级会转换为 20–100 分的原始分。</span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-brand-600">
                  2
                </span>
                <span>系统按所选学位类型的固定权重计算综合分。</span>
              </li>
              <li className="flex gap-3">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-brand-600">
                  3
                </span>
                <span>计算后可查看各维度的等级、权重与加权贡献。</span>
              </li>
            </ol>
          </aside>
        </div>
      </form>

      {report ? (
        <section
          className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
          aria-labelledby="innovation-score-report-heading"
        >
          <div className="grid gap-5 bg-slate-900 px-5 py-5 text-white sm:grid-cols-[auto_1fr] sm:px-6">
            <div className="flex h-24 w-24 flex-col items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15">
              <span className="text-3xl font-semibold tabular-nums">{report.total_score} 分</span>
              <span className="mt-0.5 text-xs text-slate-300">综合参考分</span>
            </div>
            <div className="flex flex-col justify-center">
              <div className="flex flex-wrap items-center gap-3">
                <h2 id="innovation-score-report-heading" className="text-lg font-semibold">
                  创新性评分报告
                </h2>
                <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-medium">{report.grade_label}</span>
              </div>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                {report.degree_type === 'master' ? '硕士' : '博士'}学位类型 · 已按当前五维度自评等级和固定权重完成计算。
              </p>
            </div>
          </div>
          <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-800">分项构成</h3>
                <span className="text-xs text-slate-500">原始分 × 权重</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[580px] text-left text-sm" aria-label="创新性评分明细">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      <th className="pb-3 font-medium">维度</th>
                      <th className="pb-3 font-medium">等级</th>
                      <th className="pb-3 font-medium">原始分</th>
                      <th className="pb-3 font-medium">权重</th>
                      <th className="pb-3 text-right font-medium">加权贡献</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.dimensions.map((dimension) => (
                      <tr key={dimension.key} className="border-b border-slate-100 last:border-0">
                        <td className="py-3 font-medium text-slate-800">{dimension.label}</td>
                        <td className="py-3 text-slate-600">{dimension.level}</td>
                        <td className="py-3 text-slate-600">{dimension.raw_score}</td>
                        <td className="py-3 text-slate-600">{dimension.weight * 100}%</td>
                        <td className="py-3 text-right font-semibold text-slate-800">{dimension.weighted_score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="rounded-lg bg-slate-50 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                <CheckCircle2 size={16} className={scoreTone(report.total_score)} />
                本次计算依据
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-600">{report.formula}</p>
              <p className="mt-3 border-t border-slate-200 pt-3 text-xs leading-5 text-slate-500">
                输入等级：
                {report.dimensions
                  .map((dimension) => `${dimension.label} ${report.input.levels[dimension.key]}级`)
                  .join(' · ')}
              </p>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default InnovationScoringPage;
