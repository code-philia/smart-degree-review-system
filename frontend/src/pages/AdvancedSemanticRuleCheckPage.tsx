import { BarChart3, BookOpen, BookOpenCheck, ExternalLink, FileSearch, FileText, Tag, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { fetchPaperLintBuiltInCase, fetchPaperLintBuiltInCasePdf, type PaperLintBuiltInCase } from '../api/paperLint';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { flattenPaperLintFindings } from '../components/paperLint/model';
import { Card, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader } from '../components/ui';

type ExampleKey = 'claim-evidence-inconsistency' | 'novelty-detection' | 'baseline-recommendation';
const examples: Array<{ key: ExampleKey; label: string; description: string }> = [
  { key: 'claim-evidence-inconsistency', label: '论点论据不一致', description: '跨页核对同一指标的陈述与实验结果。' },
  { key: 'novelty-detection', label: '论文新颖性检测', description: '通过方法结构比对识别已有工作重合。' },
  { key: 'baseline-recommendation', label: '相关对比工作推荐', description: '按问题与方法相似度组织对比工作。' },
];

type DslParameter = { name: string; type: string; description: string };
type Dsl = { title: string; inputs: DslParameter[]; output: DslParameter; steps: string[] };

const targetDsl: Dsl = {
  title: 'Identifying Latent State-Transition Processes for Individualized Reinforcement Learning',
  inputs: [
    { name: 'latent individual-specific factors', type: 'tensor<float, 1>', description: '影响个体状态转移过程、且无法被直接观测的个体特征。' },
    { name: 'current state', type: 'tensor<float, 1>', description: '交互个体当前可观测的 MDP 状态。' },
    { name: 'current reward', type: 'float', description: '学习个体化策略时获得的奖励信号。' },
    { name: 'observed state-action trajectories', type: 'list<tensor<float, 1>>', description: '用于识别潜在因子与状态转移过程的历史轨迹。' },
  ],
  output: { name: 'current action', type: 'tensor<float, 1>', description: '考虑潜在状态转移因子后，由个体化策略选择的动作。' },
  steps: [
    '在 MDP 中加入影响状态转移的个体潜在因子。',
    '从状态—动作轨迹中推断潜在因子与状态转移过程。',
    '通过 VQ-VAE 风格的生成模型恢复紧凑的潜在表示。',
    '将潜在表示与强化学习算法结合，学习个体化策略。',
  ],
};

const similarDsl: Dsl = {
  title: 'Factored Adaptation for Non-Stationary Reinforcement Learning',
  inputs: [
    { name: 'latent change factors', type: 'tensor<float, 1>', description: '影响非平稳 MDP 转移动态与奖励函数的不可观测变化因子。' },
    { name: 'current state', type: 'tensor<float, 1>', description: '非平稳动态下当前可观测的 MDP 状态。' },
    { name: 'current reward', type: 'float', description: '受潜在变化因子支配的奖励信号。' },
    { name: 'observed state-action trajectories', type: 'list<tensor<float, 1>>', description: '用于识别分解式 MDP 结构与潜在变化因子的历史轨迹。' },
  ],
  output: { name: 'current action', type: 'tensor<float, 1>', description: '策略适应潜在变化因子后选择的动作。' },
  steps: [
    '构建由潜在变化因子影响转移与奖励的分解式非平稳 MDP。',
    '从观测轨迹中推断潜在因子并恢复因果转移结构。',
    '使用带稀疏掩码的 FN-VAE 恢复紧凑的分解潜在表示。',
    '以潜在表示进行策略优化，使策略适应转移动态。',
  ],
};
type Work = { name: string; link: string; method: number; problem: number; sameProblem: boolean; description: string };
const works: Work[] = [
  { name: 'GPT4MTS: Prompt-based Large Language Model for Multimodal Time-series Forecasting', link: 'https://doi.org/10.1609/aaai.v38i21.30383', method: 83, problem: 95, sameProblem: true, description: '正式实验中复现的多模态预测基线，采用 LLM 同时利用数值与文本信息。' },
  { name: 'Language in the Flow of Time: Time-Series-Paired Texts Weaved into a Unified Temporal Narrative', link: 'https://arxiv.org/abs/2502.08942', method: 81, problem: 94, sameProblem: true, description: '正式实验中的多模态基线，将与时序配对的文本作为辅助变量。' },
  { name: 'Time-VLM: Exploring Multimodal Vision-Language Models for Augmented Time Series Forecasting', link: 'https://arxiv.org/abs/2502.04395', method: 72, problem: 90, sameProblem: true, description: '采用视觉语言模型连接时序、视觉与文本模态。' },
  { name: 'CALF: Aligning LLMs for Time Series Forecasting via Cross-modal Fine-Tuning', link: 'https://arxiv.org/abs/2403.07300', method: 68, problem: 88, sameProblem: true, description: '通过跨模态微调缓解文本与时序数据的分布差异。' },
  { name: 'Time-LLM: Time Series Forecasting by Reprogramming Large Language Models', link: 'https://arxiv.org/abs/2310.01728', method: 55, problem: 82, sameProblem: false, description: '相关工作中的 LLM 时序预测方法，未被作为正式实验基线复现。' },
  { name: 'CC-Time: Cross-Model and Cross-Modality Time Series Forecasting', link: 'https://arxiv.org/abs/2508.12235', method: 62, problem: 84, sameProblem: false, description: '相关工作中的跨模态预测路线，提供补充比较视角。' },
];

function ExampleNav({ active }: { active: ExampleKey }) { return <nav aria-label="高级语义规则检测示例" className="grid gap-3 md:grid-cols-3">{examples.map((item, index) => <NavLink key={item.key} to={`/advanced-semantic-rule-check/${item.key}`} className={({ isActive }) => `rounded-xl border p-4 transition ${isActive || active === item.key ? 'border-violet-500 bg-violet-50 shadow-sm' : 'border-slate-200 bg-white hover:border-violet-300'}`}><span className="text-xs font-bold text-violet-700">语义规则 {index + 1}</span><span className="mt-1 block font-bold text-slate-900">{item.label}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{item.description}</span></NavLink>)}</nav>; }

function ClaimEvidenceExample() {
  const { status, user } = useAuthSession(); const [reviewCase, setReviewCase] = useState<PaperLintBuiltInCase | null>(null); const [pdfFile, setPdfFile] = useState<File | null>(null); const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!user) return; let alive = true; void Promise.all([fetchPaperLintBuiltInCase('yandex-accuracy-claim-evidence'), fetchPaperLintBuiltInCasePdf('yandex-accuracy-claim-evidence')]).then(([nextCase, pdf]) => { if (alive) { setReviewCase(nextCase); setPdfFile(new File([pdf], nextCase.pdf_filename, { type: 'application/pdf' })); } }).catch((loadError) => alive && setError(loadError instanceof Error ? loadError.message : '案例详情加载失败')); return () => { alive = false; }; }, [user]);
  const findings = useMemo(() => (reviewCase ? flattenPaperLintFindings(reviewCase.result) : []), [reviewCase]);
  if (status === 'loading') return <LoadingState label="正在恢复登录状态…" />;
  if (!user) return <EmptyState title="请先登录后查看案例" description="登录后可在同一页面查看原始 PDF、审查结论和跨页证据定位。" action={<LinkButton to="/auth">前往登录</LinkButton>} />;
  if (error) return <ErrorState message={error} />;
  if (!reviewCase || !pdfFile) return <LoadingState label="正在加载案例 PDF 与审查结果…" />;
  return <div className="space-y-5"><div className="grid gap-3 md:grid-cols-3"><Card><div className="flex items-center gap-3"><FileSearch className="size-5 text-brand-600" /><div><p className="text-xs font-semibold text-slate-500">审查规则</p><p className="mt-1 font-bold text-slate-900">{reviewCase.rule.title}</p></div></div></Card><Card><p className="text-xs font-semibold text-slate-500">论点定位</p><p className="mt-1 font-bold text-slate-900">第 {reviewCase.claim_page} 页</p></Card><Card><p className="text-xs font-semibold text-slate-500">论据定位</p><p className="mt-1 font-bold text-slate-900">第 {reviewCase.evidence_page} 页</p></Card></div><PaperLintWorkspace file={pdfFile} findings={findings} rules={[reviewCase.rule]} /></div>;
}

function DslPanel({ dsl, label, tone }: { dsl: Dsl; label: string; tone: 'target' | 'reference' }) {
  const palette = tone === 'target'
    ? { border: 'border-slate-200', label: 'text-slate-600', badge: 'bg-slate-100 text-slate-700', index: 'bg-slate-800 text-white', step: 'border-slate-200 bg-white' }
    : { border: 'border-sky-200', label: 'text-sky-700', badge: 'bg-sky-50 text-sky-700', index: 'bg-sky-600 text-white', step: 'border-sky-100 bg-sky-50/30' };
  return <section className={`overflow-hidden rounded-xl border bg-white shadow-sm ${palette.border}`}>
    <div className="border-b border-inherit px-5 py-5"><div className="flex items-start gap-3"><div className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${palette.badge}`}><FileText className="size-4" /></div><div><p className={`text-xs font-bold tracking-wide ${palette.label}`}>{label}</p><h2 className="mt-1 text-base font-bold leading-6 text-slate-900">{dsl.title}</h2></div></div></div>
    <div className="space-y-6 bg-slate-50/50 p-5"><section><p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">输入</p><div className="space-y-2">{dsl.inputs.map((item, index) => <article key={item.name} className="rounded-lg border border-slate-200 bg-white px-3.5 py-3"><div className="flex items-center gap-2"><span className={`flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${palette.index}`}>{index + 1}</span><code className="truncate text-[13px] font-semibold text-slate-800">{item.name}</code></div><div className="ml-7 mt-2 flex flex-wrap items-center gap-x-2 gap-y-1"><span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${palette.badge}`}>{item.type}</span><p className="text-xs leading-5 text-slate-500">{item.description}</p></div></article>)}</div></section>
      <section><p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">输出</p><article className="rounded-lg border border-slate-200 bg-white px-3.5 py-3"><code className="text-[13px] font-semibold text-slate-800">{dsl.output.name}</code><div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1"><span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${palette.badge}`}>{dsl.output.type}</span><p className="text-xs leading-5 text-slate-500">{dsl.output.description}</p></div></article></section>
      <section><p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-500">方法路径</p><ol className="space-y-3">{dsl.steps.map((step, index) => <li key={step} className="relative flex gap-3"><span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${palette.index}`}>{index + 1}</span><p className={`min-h-6 flex-1 rounded-lg border px-3 py-2 text-sm leading-5 text-slate-700 ${palette.step}`}>{step}</p></li>)}</ol></section></div>
  </section>;
}

function NoveltyExample() {
  return <div className="space-y-6">
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div className="grid lg:grid-cols-[minmax(0,1fr)_250px]"><div className="p-6 sm:p-7"><p className="text-xs font-bold tracking-[0.16em] text-slate-500">检测结论</p><div className="mt-3 flex flex-wrap items-center gap-3"><h2 className="text-3xl font-bold tracking-tight text-slate-900">不新颖</h2><span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-bold text-amber-700 ring-1 ring-inset ring-amber-200">存在核心结构重合</span></div><p className="mt-4 max-w-2xl text-sm leading-6 text-slate-600">待评估论文与已发表工作均以潜在因子刻画 MDP 状态转移，并据此调整强化学习策略；二者在问题建模、潜在表示恢复与策略适应路径上形成连续对应。</p></div><div className="border-t border-slate-200 bg-slate-50 px-6 py-5 lg:border-l lg:border-t-0"><dl className="grid grid-cols-2 gap-4"><div><dt className="text-xs font-medium text-slate-500">检索轮次</dt><dd className="mt-1 text-2xl font-bold text-slate-900">3</dd></div><div><dt className="text-xs font-medium text-slate-500">命中工作</dt><dd className="mt-1 text-2xl font-bold text-slate-900">1</dd></div></dl><div className="mt-4 border-t border-slate-200 pt-3"><div className="flex items-end justify-between"><p className="text-xs font-medium text-slate-500">新颖度</p><p className="text-lg font-bold text-amber-700">0.20</p></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200"><span className="block h-full rounded-full bg-amber-500" style={{ width: '20%' }} /></div><div className="mt-1 flex justify-between text-[10px] text-slate-400"><span>0 很不新颖</span><span>1 很新颖</span></div></div></div></div></section>
    <section><div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold tracking-[0.14em] text-slate-500">结构化对照</p><h2 className="mt-1 text-xl font-bold text-slate-900">方法与问题表述</h2></div><p className="text-sm text-slate-500">从输入、输出和方法路径逐项比对</p></div><div className="grid items-start gap-5 xl:grid-cols-2"><DslPanel dsl={targetDsl} label="待评估论文" tone="target" /><DslPanel dsl={similarDsl} label="相似工作 · 1 / 1" tone="reference" /></div></section>
    <section className="rounded-xl border border-slate-200 bg-slate-50 p-5"><p className="text-xs font-bold tracking-[0.14em] text-slate-500">重合依据</p><div className="mt-4 grid gap-3 md:grid-cols-3"><div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm font-bold text-slate-800">潜在因子建模</p><p className="mt-1 text-xs leading-5 text-slate-500">均从轨迹中推断不可直接观测的潜在因子。</p></div><div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm font-bold text-slate-800">状态转移恢复</p><p className="mt-1 text-xs leading-5 text-slate-500">均以潜在表示解释并恢复 MDP 转移结构。</p></div><div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-sm font-bold text-slate-800">策略适应</p><p className="mt-1 text-xs leading-5 text-slate-500">均将恢复的表示用于强化学习策略优化与动作选择。</p></div></div></section>
  </div>;
}

function SimilarityBar({ label, value }: { label: string; value: number }) { const [bar, text] = (value >= 80 ? 'bg-red-500 text-red-600' : value >= 50 ? 'bg-amber-500 text-amber-600' : 'bg-emerald-500 text-emerald-600').split(' '); return <div className="flex items-center gap-2"><span className="w-16 shrink-0 text-xs text-slate-500">{label}</span><span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100"><span className={`block h-full rounded-full ${bar}`} style={{ width: `${value}%` }} /></span><span className={`w-9 text-right text-xs font-bold ${text}`}>{value}%</span></div>; }
function WorkCard({ work }: { work: Work }) {
  const recommendation = work.sameProblem
    ? work.method >= 80
      ? '两篇文章解决同一个问题，且方法高度相似，建议作为优先对比工作。'
      : '两篇文章解决同一个问题，可作为实验基线进行直接对照。'
    : '研究问题相近，可作为扩展比较与相关工作引用。';
  return <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex items-start justify-between gap-3"><div><div className="mb-2 flex flex-wrap gap-2"><span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${work.sameProblem ? 'bg-sky-50 text-sky-700' : 'bg-slate-100 text-slate-600'}`}>{work.sameProblem ? '同一问题' : '问题相近'}</span><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">方法相似度 {work.method}%</span></div><h3 className="text-sm font-semibold leading-5 text-slate-900">{work.name}</h3></div><a href={work.link} target="_blank" rel="noreferrer" className="shrink-0 text-slate-400 hover:text-sky-600" aria-label={`打开 ${work.name}`}><ExternalLink className="size-4" /></a></div><p className="mt-3 text-xs leading-5 text-slate-500">{work.description}</p><p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs font-medium leading-5 text-slate-700">{recommendation}</p><div className="mt-4 space-y-2 border-t border-slate-100 pt-3"><SimilarityBar label="问题相似度" value={work.problem} /><SimilarityBar label="方法相似度" value={work.method} /></div></article>;
}

function BaselineExample() {
  const priority = works.filter((work) => work.sameProblem && work.method > 80); const reproduced = works.filter((work) => work.sameProblem && work.method <= 80); const related = works.filter((work) => !work.sameProblem && work.problem > 75); const average = Math.round(works.reduce((sum, work) => sum + work.method, 0) / works.length);
  return <div className="space-y-7"><section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"><p className="text-xs font-bold tracking-[0.14em] text-slate-500">待比较论文</p><h2 className="mt-2 max-w-4xl text-xl font-bold leading-7 text-slate-900">Unlocking the Value of Text: Event-Driven Reasoning and Multi-Level Alignment for Time Series Forecasting</h2><div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-slate-500"><span className="inline-flex items-center gap-1"><Users className="size-3.5" /> Siyuan Wang, Peng Chen, Yihang Wang +4</span><span>·</span><span className="inline-flex items-center gap-1"><BookOpen className="size-3.5" /> ICLR 2026</span><span>·</span><span className="inline-flex items-center gap-1"><Tag className="size-3.5" /> Time series</span><span className="rounded bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">Accept (Poster)</span></div><p className="mt-4 max-w-4xl text-sm leading-6 text-slate-600">面向包含外生文本的真实世界时序预测，VoT 以事件驱动推理和多层对齐结合文本信息与数值时序；实验覆盖 10 个领域，验证了文本利用的有效性。</p><a href="https://openreview.net/forum?id=0TAFiyHgEl" target="_blank" rel="noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-slate-500 hover:text-sky-600"><ExternalLink className="size-3.5" /> 查看 OpenReview</a></section><section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]"><div className="rounded-xl border border-sky-200 bg-sky-50/50 p-6"><p className="text-xs font-bold tracking-[0.14em] text-sky-700">推荐依据</p><h2 className="mt-2 text-xl font-bold text-slate-900">优先比较同一问题下的方法路线</h2><p className="mt-3 text-sm leading-6 text-slate-700">已筛出 {priority.length} 篇优先对比工作：它们解决的是同一个时序预测问题，并且方法路径非常接近。建议在实验与相关工作中优先纳入，清楚说明与本文的差异。</p></div><div className="grid grid-cols-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="border-r border-slate-100 px-2 text-center"><FileSearch className="mx-auto mb-2 size-4 text-slate-400" /><p className="text-xl font-bold text-slate-900">{works.length}</p><p className="mt-1 text-[11px] text-slate-500">相关论文</p></div><div className="border-r border-slate-100 px-2 text-center"><BarChart3 className="mx-auto mb-2 size-4 text-slate-400" /><p className="text-xl font-bold text-slate-900">{average}%</p><p className="mt-1 text-[11px] text-slate-500">平均方法相似度</p></div><div className="px-2 text-center"><BookOpenCheck className="mx-auto mb-2 size-4 text-sky-600" /><p className="text-xl font-bold text-slate-900">{priority.length}</p><p className="mt-1 text-[11px] text-slate-500">优先对比</p></div></div></section><section><div className="mb-4 flex items-end justify-between gap-3"><div><p className="text-xs font-bold tracking-[0.14em] text-slate-500">推荐结果</p><h2 className="mt-1 text-xl font-bold text-slate-900">优先对比工作</h2></div><p className="text-sm text-slate-500">同一问题且方法相似度超过 80%</p></div><div className="grid gap-4 lg:grid-cols-2">{priority.map((work) => <WorkCard key={work.name} work={work} />)}</div></section><div className="grid items-start gap-7 lg:grid-cols-2"><section><div className="mb-4"><p className="text-xs font-bold tracking-[0.14em] text-slate-500">实验设计</p><h2 className="mt-1 text-xl font-bold text-slate-900">可复现实验基线</h2></div><div className="space-y-3">{reproduced.map((work) => <WorkCard key={work.name} work={work} />)}</div></section><section><div className="mb-4"><p className="text-xs font-bold tracking-[0.14em] text-slate-500">文献综述</p><h2 className="mt-1 text-xl font-bold text-slate-900">扩展比较工作</h2></div><div className="space-y-3">{related.map((work) => <WorkCard key={work.name} work={work} />)}</div></section></div></div>;
}

function AdvancedSemanticRuleCheckPage() { const { example } = useParams<{ example?: ExampleKey }>(); const active = examples.some((item) => item.key === example) ? (example as ExampleKey) : 'claim-evidence-inconsistency'; const content = active === 'novelty-detection' ? <NoveltyExample /> : active === 'baseline-recommendation' ? <BaselineExample /> : <ClaimEvidenceExample />; return <div className="space-y-6"><PageHeader eyebrow="固定演示案例" title="高级语义规则检测" actions={<BookOpenCheck className="size-6 text-violet-600" />} /><ExampleNav active={active} />{content}<p className="text-xs leading-5 text-slate-500">示例结果为随版本提供的固定演示数据，不写入检测台账、统计或师生批阅流程；所有判断均须人工复核。</p></div>; }
export default AdvancedSemanticRuleCheckPage;
