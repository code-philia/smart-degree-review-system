import { FormEvent, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { analyzeDefaultNormativeText, type NormativeIssue } from '../api/normativeRules';

function NormativeCheckPage() {
  const { status, user } = useAuthSession();
  const [text, setText] = useState('');
  const [issues, setIssues] = useState<NormativeIssue[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  const hasIssues = issues.length > 0;
  const resultLabel = useMemo(() => {
    if (!touched) {
      return '等待提交文本进行默认规则检测。';
    }
    if (submitting) {
      return '正在运行默认规范检测规则…';
    }
    if (hasIssues) {
      return `已返回 ${issues.length} 条问题。`;
    }
    return '未返回问题。';
  }, [hasIssues, issues.length, submitting, touched]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    setErrorMessage(null);
    setSubmitting(true);

    try {
      const response = await analyzeDefaultNormativeText({ text });
      setIssues(response.issues);
    } catch (error) {
      const message = error instanceof Error ? error.message : '默认规范检测失败';
      setErrorMessage(message);
      setIssues([]);
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
          <h1 className="text-2xl font-black text-slate-900">默认规范检测</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后运行章节顺序、标点配对、重复标点和文本质量规则。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 pb-5">
          <p className="text-sm font-semibold tracking-[0.25em] text-blue-700">DEFAULT NORMATIVE CHECK</p>
          <div>
            <h1 className="text-3xl font-black text-slate-950">默认规范检测规则</h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              当前登录用户：{user.username}（{user.role}）。规则覆盖章节顺序、标点配对、重复标点、日期格式、参考文献与文本质量。
            </p>
          </div>
        </div>

        <form className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]" onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-slate-700">待检测文本</span>
            <textarea
              className="min-h-[340px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm leading-7 outline-none focus:border-blue-500"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="粘贴论文片段后运行默认规则检测。"
            />
          </label>

          <aside className="space-y-4">
            <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <h2 className="text-base font-bold text-slate-900">执行状态</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{resultLabel}</p>
              {errorMessage ? <p className="mt-2 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
              <button
                className="mt-4 inline-flex h-11 items-center rounded-lg bg-blue-600 px-4 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                type="submit"
                disabled={submitting}
              >
                {submitting ? '检测中…' : '运行默认规则'}
              </button>
            </section>

            <section className="rounded-2xl border border-slate-200 p-4">
              <h2 className="text-base font-bold text-slate-900">结果字段</h2>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-slate-600">
                <li>rule_id、类别、严重程度</li>
                <li>行号、列号、原文片段</li>
                <li>问题说明、修改建议</li>
              </ul>
            </section>
          </aside>
        </form>

        <section className="mt-8 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <h2 className="text-lg font-black text-slate-900">检测问题</h2>
          {hasIssues ? (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full border-separate border-spacing-y-2 text-left text-sm">
                <thead className="text-slate-500">
                  <tr>
                    <th className="px-2 py-1">rule_id</th>
                    <th className="px-2 py-1">类别</th>
                    <th className="px-2 py-1">严重程度</th>
                    <th className="px-2 py-1">行号</th>
                    <th className="px-2 py-1">列号</th>
                    <th className="px-2 py-1">原文片段</th>
                    <th className="px-2 py-1">问题说明</th>
                    <th className="px-2 py-1">修改建议</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.map((issue, index) => (
                    <tr key={`${issue.rule_id}-${index}`} className="align-top text-slate-800">
                      <td className="px-2 py-2 font-mono text-xs">{issue.rule_id}</td>
                      <td className="px-2 py-2">{issue.category}</td>
                      <td className="px-2 py-2">{issue.severity}</td>
                      <td className="px-2 py-2">{issue.line}</td>
                      <td className="px-2 py-2">{issue.column}</td>
                      <td className="px-2 py-2">{issue.excerpt}</td>
                      <td className="px-2 py-2">{issue.message}</td>
                      <td className="px-2 py-2">{issue.suggestion}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-3 text-sm leading-6 text-slate-600">{touched ? '本次检测未返回问题。' : '尚未检测任何文本。'}</p>
          )}
        </section>
      </section>
    </main>
  );
}

export default NormativeCheckPage;
