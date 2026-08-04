import { FormEvent, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  createLocalPolishResult,
  type LocalPolishLevel,
  type LocalPolishResult,
} from '../api/normativeRules';

const LEVEL_OPTIONS: Array<{ level: LocalPolishLevel; title: string; summary: string; recommended?: boolean }> = [
  { level: 'basic', title: 'AI 校准', summary: '修正空白、重复标点与基础表达' },
  { level: 'standard', title: 'AI 提质', summary: '推荐：叠加规则版本下的表达优化', recommended: true },
  { level: 'enhanced', title: 'AI 重构', summary: '在可解释差异中进行更强结构调整' },
];

function renderResultText(result: LocalPolishResult | null) {
  if (!result) {
    return <p className="text-slate-400">处理后将在这里显示带差异标注的结果。</p>;
  }

  if (!result.diff_segments.length) {
    return <p className="whitespace-pre-wrap">{result.polished_text}</p>;
  }

  return (
    <p className="whitespace-pre-wrap">
      {result.diff_segments.map((segment, index) => (
        <span
          key={`${segment.type}-${index}-${segment.text.slice(0, 8)}`}
          data-diff-type={segment.type}
          className={
            segment.type === 'added'
              ? 'text-[#22B573]'
              : segment.type === 'deleted'
                ? 'text-[#E74C3C] line-through'
                : segment.type === 'replaced' || segment.type === 'replacement'
                  ? 'bg-orange-50 text-[#F07E2E]'
                  : segment.type === 'format'
                    ? 'bg-slate-100 text-slate-700'
                    : undefined
          }
        >
          {segment.text}
        </span>
      ))}
    </p>
  );
}

function LocalPolishPage() {
  const { status, user } = useAuthSession();
  const [text, setText] = useState('');
  const [level, setLevel] = useState<LocalPolishLevel>('standard');
  const [result, setResult] = useState<LocalPolishResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  const canSubmit = useMemo(() => Boolean(text.trim()) && !submitting, [text, submitting]);
  const characterCount = text.length;

  async function submitPolish(retryOf?: string) {
    setSubmitting(true);
    setErrorMessage(null);
    setCopyMessage(null);

    try {
      const response = await createLocalPolishResult({ text, level, retry_of: retryOf || null });
      setResult(response);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '局部润色失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitPolish();
  }

  async function handleRetry() {
    if (!result) {
      return;
    }
    await submitPolish(result.id);
  }

  async function handleCopy() {
    if (!result) {
      return;
    }
    await navigator.clipboard.writeText(result.polished_text);
    setCopyMessage('已复制润色结果');
  }

  function handleReset() {
    setText('');
    setResult(null);
    setErrorMessage(null);
    setCopyMessage(null);
  }

  if (status === 'loading') {
    return <main className="px-6 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">局部文本润色</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后使用局部文本润色与差异对比。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F5F6F8] text-slate-900">
      <header className="flex h-[70px] items-center bg-[#213C5E] px-8 text-white">
        <h1 className="text-3xl font-black">局部文本润色与差异对比</h1>
      </header>

      <form className="px-8 py-8" onSubmit={handleSubmit}>
        <section className="grid gap-5 lg:grid-cols-2">
          <article className="overflow-hidden border border-[#D9DDE3] bg-white">
            <div className="flex items-center justify-between bg-slate-100 px-6 py-4 text-xl font-black">
              <span>原始文本输入</span>
              <span className="text-base font-semibold text-[#9AA1AA]">{characterCount} 字符</span>
            </div>
            <textarea
              aria-label="原始文本输入"
              className="min-h-[460px] w-full resize-none px-8 py-8 text-2xl leading-relaxed outline-none"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="请输入需要局部润色的文本。"
            />
          </article>

          <article className="overflow-hidden border border-[#D9DDE3] bg-white">
            <div className="flex items-center justify-between bg-slate-100 px-6 py-4 text-xl font-black">
              <span>AI 润色结果</span>
              <span className="text-base font-bold text-[#22B573]">{submitting ? '处理中' : result ? '润色完成' : '等待处理'}</span>
            </div>
            <div className="min-h-[460px] px-8 py-8 text-2xl leading-relaxed">
              <div data-testid="local-polish-result-id" className="sr-only">{result?.id || ''}</div>
              <div data-testid="local-polish-result-text">{result?.polished_text || ''}</div>
              <div data-testid="local-polish-diff-segments">{renderResultText(result)}</div>
            </div>
          </article>
        </section>

        <section className="mt-7 flex flex-wrap items-center gap-4">
          <h2 className="text-xl font-black">润色等级选择</h2>
          {LEVEL_OPTIONS.map((option) => {
            const selected = option.level === level;
            return (
              <button
                key={option.level}
                type="button"
                className={`relative flex min-w-40 items-center gap-3 rounded-xl border px-5 py-3 text-lg font-black ${selected ? 'border-[#F07E2E] bg-orange-50 text-[#F07E2E]' : 'border-[#D9DDE3] bg-white text-slate-700'}`}
                onClick={() => setLevel(option.level)}
              >
                <span className={`h-4 w-4 rounded-full border ${selected ? 'border-[#F07E2E] bg-[#F07E2E]' : 'border-slate-300'}`} />
                {option.title}
                {option.recommended ? <span className="rounded-full bg-[#F07E2E] px-2 py-0.5 text-xs text-white">推荐</span> : null}
              </button>
            );
          })}
        </section>

        <section className="mt-7 flex flex-wrap items-center justify-between gap-5">
          <div className="flex gap-4">
            <button className="rounded-xl bg-[#3B82F6] px-8 py-4 text-2xl font-black text-white disabled:opacity-50" type="submit" disabled={!canSubmit}>
              {submitting ? '润色中…' : '智能润色'}
            </button>
            <button className="rounded-xl border border-slate-300 bg-white px-8 py-4 text-2xl font-black text-slate-600" type="button" onClick={handleReset}>
              清除输入
            </button>
          </div>
          <div className="flex gap-4">
            <button className="rounded-xl bg-[#22B573] px-8 py-4 text-2xl font-black text-white disabled:opacity-50" type="button" disabled={!result} onClick={handleCopy}>
              复制文本
            </button>
            <button className="rounded-xl border border-[#3B82F6] bg-white px-8 py-4 text-2xl font-black text-[#3B82F6] disabled:opacity-50" type="button" disabled={!result || submitting} onClick={handleRetry}>
              重新润色
            </button>
          </div>
        </section>

        <section className="mt-3 grid gap-4 text-sm font-semibold text-[#9AA1AA] lg:grid-cols-2">
          <p>输入内容不会使用截图示例，字符数与段落由实时输入生成。</p>
          <p>相同原文、档位和规则版本下重新润色应返回完全一致的结果与变更列表。</p>
        </section>

        {errorMessage ? <p className="mt-5 rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
        {copyMessage ? <p className="mt-5 rounded-xl bg-green-50 px-4 py-3 text-sm font-semibold text-green-700">{copyMessage}</p> : null}
      </form>

      <footer className="border-t border-[#D9DDE3] bg-slate-100 px-8 py-5 text-sm font-semibold text-slate-600">
        <div className="grid gap-3 lg:grid-cols-4">
          <span className="text-[#E74C3C]">删除内容</span>
          <span className="text-[#22B573]">新增内容</span>
          <span className="text-[#F07E2E]">旧→新</span>
          <span className="bg-slate-200 px-2 text-slate-700">浅灰底纹</span>
        </div>
      </footer>
    </main>
  );
}

export default LocalPolishPage;
