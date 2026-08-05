import { FormEvent, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createInnovationAssessment,
  type InnovationAssessmentDimensionInput,
  type InnovationAssessmentRequest,
  type InnovationAssessmentResponse,
  type InnovationDegreeType,
  type InnovationScoreDimensionKey,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';

const DIMENSIONS: Array<{ key: InnovationScoreDimensionKey; label: string }> = [
  { key: 'research_topic', label: '研究选题' },
  { key: 'research_method', label: '研究方法' },
  { key: 'research_content', label: '研究内容' },
  { key: 'research_conclusion', label: '研究结论' },
  { key: 'application_value', label: '应用价值' },
];

const EMPTY_DIMENSION: InnovationAssessmentDimensionInput = {
  level: 3,
  evidence: '',
  improvement_plan: '',
};

function buildEmptyDimensions(): InnovationAssessmentRequest['dimensions'] {
  return DIMENSIONS.reduce((accumulator, dimension) => {
    accumulator[dimension.key] = { ...EMPTY_DIMENSION };
    return accumulator;
  }, {} as InnovationAssessmentRequest['dimensions']);
}

function InnovationAssessmentPage() {
  const { status, user } = useAuthSession();
  const [thesisTitle, setThesisTitle] = useState('');
  const [degreeType, setDegreeType] = useState<InnovationDegreeType>('master');
  const [primaryDiscipline, setPrimaryDiscipline] = useState('');
  const [secondaryDiscipline, setSecondaryDiscipline] = useState('');
  const [researchDirection, setResearchDirection] = useState('');
  const [dimensions, setDimensions] = useState<InnovationAssessmentRequest['dimensions']>(() => buildEmptyDimensions());
  const [assessment, setAssessment] = useState<InnovationAssessmentResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const progressSteps = useMemo(() => [
    { name: '填写信息', complete: Boolean(thesisTitle && primaryDiscipline && secondaryDiscipline && researchDirection) },
    { name: '五维度自评', complete: DIMENSIONS.every((dimension) => dimensions[dimension.key].evidence.trim().length >= 20) },
    { name: '计算量表分', complete: Boolean(assessment) },
    { name: '保存快照', complete: Boolean(assessment?.id) },
  ], [assessment, dimensions, primaryDiscipline, researchDirection, secondaryDiscipline, thesisTitle]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setAssessment(null);
    setErrorMessage(null);
    setFieldErrors({});

    try {
      const result = await createInnovationAssessment({
        thesis_title: thesisTitle,
        degree_type: degreeType,
        primary_discipline: primaryDiscipline,
        secondary_discipline: secondaryDiscipline,
        research_direction: researchDirection,
        dimensions,
      });
      setAssessment(result);
    } catch (error) {
      const maybeErrors = (error as { response?: { data?: { errors?: Array<{ field: string; message: string }> } } })?.response?.data?.errors;
      if (Array.isArray(maybeErrors)) {
        setFieldErrors(Object.fromEntries(maybeErrors.map((item) => [item.field, item.message])));
      }
      setErrorMessage(error instanceof Error ? error.message : '创新性量表评估提交失败');
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') {
    return <main className="min-h-screen bg-white p-8 text-slate-700">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-white p-8">
        <h1 className="text-2xl font-black text-[#1F3B5D]">发起创新性量表评估</h1>
        <p className="mt-4 text-slate-600">请先登录后提交量表自评，后台会在保存前执行角色授权。</p>
        <Link className="mt-6 inline-flex rounded bg-[#3D8BF2] px-5 py-3 font-bold text-white" to="/auth">前往登录</Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white">
      <header className="flex h-16 items-center bg-[#1F3B5D] px-8">
        <h1 className="text-2xl font-black text-white">发起创新性量表评估</h1>
      </header>

      <form className="px-9 py-8" onSubmit={handleSubmit}>
        <section className="rounded-[24px] border-2 border-dashed border-[#B7CAE6] px-8 py-8 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border-2 border-[#B7CAE6] text-2xl font-black text-[#3D8BF2]">↑</div>
          <p className="mt-3 text-lg font-black text-[#333333]">填写论文题目与评估信息</p>
          <p className="mt-1 text-sm text-slate-500">无需上传样例文件；所有评估内容将以当前账号保存为输入快照。</p>
        </section>

        <section className="mt-8 grid gap-x-12 gap-y-6 lg:grid-cols-2">
          <label className="grid gap-2 text-base font-bold text-[#333333]">
            论文题目
            <input className="h-12 rounded border border-[#DADADA] px-4 outline-none focus:border-[#3D8BF2]" value={thesisTitle} onChange={(event) => setThesisTitle(event.target.value)} />
            {fieldErrors.thesis_title ? <span className="text-sm text-red-600">{fieldErrors.thesis_title}</span> : null}
          </label>
          <label className="grid gap-2 text-base font-bold text-[#333333]">
            学历层次
            <select className="h-12 rounded border border-[#DADADA] px-4 outline-none focus:border-[#3D8BF2]" value={degreeType} onChange={(event) => setDegreeType(event.target.value as InnovationDegreeType)}>
              <option value="master">硕士</option>
              <option value="doctoral">博士</option>
            </select>
          </label>
          <label className="grid gap-2 text-base font-bold text-[#333333]">
            一级学科
            <input className="h-12 rounded border border-[#DADADA] px-4 outline-none focus:border-[#3D8BF2]" value={primaryDiscipline} onChange={(event) => setPrimaryDiscipline(event.target.value)} />
            {fieldErrors.primary_discipline ? <span className="text-sm text-red-600">{fieldErrors.primary_discipline}</span> : null}
          </label>
          <label className="grid gap-2 text-base font-bold text-[#333333]">
            二级学科
            <input className="h-12 rounded border border-[#DADADA] px-4 outline-none focus:border-[#3D8BF2]" value={secondaryDiscipline} onChange={(event) => setSecondaryDiscipline(event.target.value)} />
            {fieldErrors.secondary_discipline ? <span className="text-sm text-red-600">{fieldErrors.secondary_discipline}</span> : null}
          </label>
          <label className="grid gap-2 text-base font-bold text-[#333333] lg:col-span-2">
            研究方向
            <input className="h-12 rounded border border-[#DADADA] px-4 outline-none focus:border-[#3D8BF2]" value={researchDirection} onChange={(event) => setResearchDirection(event.target.value)} />
            {fieldErrors.research_direction ? <span className="text-sm text-red-600">{fieldErrors.research_direction}</span> : null}
          </label>
        </section>

        <section className="mt-8 grid gap-5">
          {DIMENSIONS.map((dimension) => (
            <fieldset key={dimension.key} className="rounded-xl border border-slate-200 p-5">
              <legend className="px-2 text-lg font-black text-[#1F3B5D]">{dimension.label}</legend>
              <label className="mt-3 block text-sm font-bold text-slate-700">
                等级
                <select className="mt-2 h-11 w-full rounded border border-[#DADADA] px-3" value={dimensions[dimension.key].level} onChange={(event) => setDimensions((current) => ({ ...current, [dimension.key]: { ...current[dimension.key], level: Number(event.target.value) } }))}>
                  {[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level} 级</option>)}
                </select>
              </label>
              <label className="mt-3 block text-sm font-bold text-slate-700">
                证据（不少于 20 个字符）
                <textarea className="mt-2 min-h-24 w-full rounded border border-[#DADADA] p-3" value={dimensions[dimension.key].evidence} onChange={(event) => setDimensions((current) => ({ ...current, [dimension.key]: { ...current[dimension.key], evidence: event.target.value } }))} />
                {fieldErrors[`dimensions.${dimension.key}.evidence`] ? <span className="text-sm text-red-600">{fieldErrors[`dimensions.${dimension.key}.evidence`]}</span> : null}
              </label>
              <label className="mt-3 block text-sm font-bold text-slate-700">
                改进计划（不少于 20 个字符）
                <textarea className="mt-2 min-h-24 w-full rounded border border-[#DADADA] p-3" value={dimensions[dimension.key].improvement_plan} onChange={(event) => setDimensions((current) => ({ ...current, [dimension.key]: { ...current[dimension.key], improvement_plan: event.target.value } }))} />
                {fieldErrors[`dimensions.${dimension.key}.improvement_plan`] ? <span className="text-sm text-red-600">{fieldErrors[`dimensions.${dimension.key}.improvement_plan`]}</span> : null}
              </label>
            </fieldset>
          ))}
        </section>

        <p className="mt-6 rounded-lg bg-amber-50 p-4 font-bold text-amber-800">本结果为量表自评，不代替专家评审或文献查新</p>
        <button className="mt-6 h-14 w-full rounded-lg bg-[#3D8BF2] text-xl font-black text-white disabled:opacity-60" type="submit" disabled={submitting}>{submitting ? '保存评估中…' : 'AI 创新性分析'}</button>
        {errorMessage ? <p className="mt-4 text-sm font-bold text-red-600" role="alert">{errorMessage}</p> : null}
      </form>

      <section className="px-9 pb-8" aria-label="创新性分析处理进度">
        <h2 className="text-2xl font-black text-[#0b3768]">处理进度</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {progressSteps.map((step, index) => <span key={step.name} className={`rounded-lg border px-4 py-2 font-bold ${step.complete ? 'border-[#43c63a] bg-[#edf9ef] text-[#1f7a1f]' : 'border-slate-300 bg-white text-slate-500'}`}>{index + 1}. {step.name}</span>)}
        </div>
      </section>

      {assessment ? (
        <section className="border-t bg-[#fafafa] px-9 py-8" aria-labelledby="innovation-assessment-result-heading">
          <h2 id="innovation-assessment-result-heading" className="text-2xl font-black text-[#0b3768]">分析结果</h2>
          <div className="mt-5 rounded-lg border border-[#e0e0e0] bg-white p-8">
            <p className="text-3xl font-black text-[#3b86f4]">{assessment.total_score} 分 · {assessment.grade_label}</p>
            <p className="mt-3 font-bold text-slate-700">论文题目：{assessment.thesis_title}</p>
            <p className="mt-2 font-bold text-slate-700">完成时间：{assessment.created_at}</p>
            <p className="mt-2 font-bold text-amber-700">{assessment.disclaimer}</p>
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default InnovationAssessmentPage;
