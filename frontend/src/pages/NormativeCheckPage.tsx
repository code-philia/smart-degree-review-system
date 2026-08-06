import { ChangeEvent, FormEvent, useMemo, useState } from 'react';
import ReviewRubricSelector from '../components/ReviewRubricSelector';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Card, LinkButton, LoadingState } from '../components/ui';
import { createNormativeDetectionTask, type DetectionTaskResponse, type NormativeIssue } from '../api/normativeRules';
import { extractThesisFileText, THESIS_FILE_ACCEPT } from '../utils/thesisFileText';

type RuleOption = {
  rule_id: string;
  title?: string;
  category?: string;
  source?: string;
};

function countBySeverity(issues: NormativeIssue[]) {
  return issues.reduce<Record<string, number>>((counts, issue) => {
    counts[issue.severity] = (counts[issue.severity] || 0) + 1;
    return counts;
  }, {});
}

function NormativeCheckPage() {
  const { status, user } = useAuthSession();
  const [text, setText] = useState('');
  const [issues, setIssues] = useState<NormativeIssue[]>([]);
  const [task, setTask] = useState<DetectionTaskResponse | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
  const [touched, setTouched] = useState(false);
  const [rubricSelectorOpen, setRubricSelectorOpen] = useState(false);

  const hasIssues = issues.length > 0;
  const ruleOptions = useMemo<RuleOption[]>(() => {
    return (task?.rule_snapshot || [])
      .map((rule) => ({
        rule_id: String(rule.rule_id || ''),
        title: typeof rule.title === 'string' ? rule.title : undefined,
        category: typeof rule.category === 'string' ? rule.category : undefined,
        source: typeof rule.source === 'string' ? rule.source : undefined,
      }))
      .filter((rule) => rule.rule_id);
  }, [task]);
  const severityCounts = task?.severity_counts || countBySeverity(issues);
  const resultLabel = useMemo(() => {
    if (!touched) {
      return '待检测：选择当前生效规则后粘贴文本或上传文件。';
    }
    if (submitting) {
      return '检测中：后端正在同一请求内完成检测。';
    }
    if (task) {
      return '已完成：任务、规则快照和问题列表已保存。';
    }
    return '待检测：尚未创建检测任务。';
  }, [submitting, task, touched]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    setErrorMessage(null);
    setSelectedFile(file);

    if (!file) {
      return;
    }

    setReadingFile(true);
    try {
      const result = await extractThesisFileText(file);
      setText(result.text);
    } catch (error) {
      setSelectedFile(null);
      setText('');
      setErrorMessage(error instanceof Error ? error.message : '文件解析失败');
    } finally {
      setReadingFile(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    setErrorMessage(null);
    setSubmitting(true);

    try {
      const response = await createNormativeDetectionTask({
        text,
        source_type: selectedFile ? 'file' : 'paste',
        source_filename: selectedFile?.name || null,
      });
      setTask(response);
      setIssues(response.issues);
    } catch (error) {
      const message = error instanceof Error ? error.message : '规范检测任务创建失败';
      setErrorMessage(message);
      setTask(null);
      setIssues([]);
    } finally {
      setSubmitting(false);
    }
  }

  if (status === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">发起规范检测</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后选择当前生效规则并创建规范检测任务。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <section>
        <h1 className="text-3xl font-black text-slate-950">文档上传</h1>

        <form className="mt-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm" onSubmit={handleSubmit}>
          <div>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-slate-900">辅助评阅模板</h2>
                <p className="mt-1 text-xs font-semibold text-slate-500">
                  展示内置五类评阅模板、必需章节、最低文献数和共享计分项
                </p>
              </div>
              <button
                className="h-10 rounded-lg border border-blue-200 px-4 text-sm font-bold text-blue-700 transition hover:border-blue-500 hover:bg-blue-50"
                type="button"
                onClick={() => setRubricSelectorOpen((open) => !open)}
              >
                {rubricSelectorOpen ? '收起模板选择器' : '打开模板选择器'}
              </button>
            </div>

            <ReviewRubricSelector isOpen={rubricSelectorOpen} />

            {ruleOptions.length > 0 ? (
              <div className="mt-6 divide-y divide-slate-100 rounded-2xl border border-slate-200">
                {ruleOptions.map((rule) => (
                  <label key={rule.rule_id} className="flex items-center gap-3 px-4 py-3 text-sm text-slate-700">
                    <input checked readOnly type="checkbox" className="h-4 w-4 accent-blue-600" />
                    <span className="min-w-0 flex-1 truncate font-semibold">{rule.title || rule.rule_id}</span>
                    <span className="text-xs text-slate-400">{rule.source || rule.category || '当前生效'}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="mt-6 rounded-2xl border border-dashed border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                发起检测后将展示本次实际生效的规则清单。
              </p>
            )}
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-slate-700">论文文本</span>
              <textarea
                className="min-h-[280px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm leading-7 outline-none focus:border-blue-500"
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="粘贴摘要、关键词、引言、结论和参考文献等论文文本。"
              />
            </label>

            <aside className="space-y-4">
              <label className="flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed border-blue-200 bg-blue-50/60 px-5 text-center transition hover:border-blue-500 hover:bg-blue-50">
                <span
                  className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-2xl text-blue-600"
                  aria-hidden="true"
                >
                  📄
                </span>
                <span className="mt-4 text-sm font-bold text-slate-900">拖拽或点击上传论文文件</span>
                <span className="mt-2 text-xs leading-5 text-slate-500">
                  文本文件最大 5 MB，可搜索文本 PDF 最大 50 MB（提取文本最大 5 MB）
                </span>
                <input className="sr-only" type="file" accept={THESIS_FILE_ACCEPT} onChange={handleFileChange} />
                {selectedFile ? (
                  <span className="mt-3 text-xs font-semibold text-blue-700">{selectedFile.name}</span>
                ) : null}
              </label>

              <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <h2 className="text-base font-bold text-slate-900">执行状态</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{resultLabel}</p>
                {errorMessage ? <p className="mt-2 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
                <button
                  className="mt-4 inline-flex h-11 w-full items-center justify-center rounded-xl bg-blue-600 px-4 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                  type="submit"
                  disabled={submitting || readingFile}
                >
                  {readingFile ? '解析中…' : submitting ? '检测中…' : '发起检测'}
                </button>
              </section>
            </aside>
          </div>
        </form>

        {task ? (
          <section className="mt-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
              <div className="flex items-center justify-center">
                <div className="flex h-48 w-48 items-center justify-center rounded-full border-[18px] border-blue-500 bg-blue-50 text-center">
                  <div>
                    <p className="text-4xl font-black text-blue-700">100%</p>
                    <p className="mt-1 text-sm font-semibold text-blue-700">已完成</p>
                  </div>
                </div>
              </div>
              <div className="rounded-2xl border border-dashed border-blue-300 p-5">
                <h2 className="text-lg font-black text-slate-900">检测报告摘要</h2>
                <dl className="mt-4 grid gap-3 text-sm text-slate-700 sm:grid-cols-2">
                  <div>
                    <dt className="font-semibold">任务状态</dt>
                    <dd>{task.status}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold">创建时间</dt>
                    <dd>{task.created_at}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold">问题总数</dt>
                    <dd>{issues.length}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold">规则快照</dt>
                    <dd>{task.rule_snapshot.length} 条</dd>
                  </div>
                </dl>
              </div>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-3">
              {Object.entries(severityCounts).map(([severity, count]) => (
                <div key={severity} className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-sm font-semibold text-slate-500">{severity}</p>
                  <p className="mt-2 text-2xl font-black text-blue-700">{count}</p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
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
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {touched ? '本次检测未返回问题。' : '尚未检测任何文本。'}
            </p>
          )}
        </section>
      </section>
    </div>
  );
}

export default NormativeCheckPage;
