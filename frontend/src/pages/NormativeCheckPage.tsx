import { ChangeEvent, FormEvent, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  createNormativeDetectionTask,
  type DetectionTaskResponse,
  type NormativeIssue,
} from '../api/normativeRules';

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const ACCEPTED_FILE_EXTENSIONS = ['.txt', '.md'];

type RuleOption = {
  rule_id: string;
  title?: string;
  category?: string;
  source?: string;
};

function getFileExtension(fileName: string) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

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
  const [touched, setTouched] = useState(false);

  const hasIssues = issues.length > 0;
  const ruleOptions = useMemo<RuleOption[]>(() => {
    return (task?.rule_snapshot || []).map((rule) => ({
      rule_id: String(rule.rule_id || ''),
      title: typeof rule.title === 'string' ? rule.title : undefined,
      category: typeof rule.category === 'string' ? rule.category : undefined,
      source: typeof rule.source === 'string' ? rule.source : undefined,
    })).filter((rule) => rule.rule_id);
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

  async function readSelectedFile(file: File) {
    if (!ACCEPTED_FILE_EXTENSIONS.includes(getFileExtension(file.name))) {
      throw new Error('仅支持上传 .txt 或 .md 文件');
    }
    if (file.size > MAX_FILE_BYTES) {
      throw new Error('文件大小不能超过 5 MB');
    }
    return file.text();
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    setErrorMessage(null);
    setSelectedFile(file);

    if (!file) {
      return;
    }

    try {
      const fileText = await readSelectedFile(file);
      setText(fileText);
    } catch (error) {
      setSelectedFile(null);
      setText('');
      setErrorMessage(error instanceof Error ? error.message : '文件读取失败，请确认文件为 UTF-8 文本');
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
    return <main className="px-6 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">发起规范检测</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后选择当前生效规则并创建规范检测任务。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F5FAFF] px-6 py-10">
      <section className="mx-auto max-w-6xl">
        <h1 className="text-3xl font-black text-slate-950">文档上传</h1>

        <form className="mt-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm" onSubmit={handleSubmit}>
          <div>
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-base font-bold text-slate-900">请选择检测模板</h2>
              <span className="text-xs font-semibold text-slate-500">使用当前账号生效的学校/学院规则</span>
            </div>

            {ruleOptions.length > 0 ? (
              <div className="mt-4 divide-y divide-slate-100 rounded-2xl border border-slate-200">
                {ruleOptions.map((rule) => (
                  <label key={rule.rule_id} className="flex items-center gap-3 px-4 py-3 text-sm text-slate-700">
                    <input checked readOnly type="checkbox" className="h-4 w-4 accent-blue-600" />
                    <span className="min-w-0 flex-1 truncate font-semibold">{rule.title || rule.rule_id}</span>
                    <span className="text-xs text-slate-400">{rule.source || rule.category || '当前生效'}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="mt-4 rounded-2xl border border-dashed border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                发起检测后将从后端返回当次规则快照；页面不展示硬编码模板。
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
                <span className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-sm font-black text-blue-600">UPLOAD</span>
                <span className="mt-4 text-sm font-bold text-slate-900">拖拽或点击上传论文文件</span>
                <span className="mt-2 text-xs leading-5 text-slate-500">支持 .txt / .md，UTF-8 编码，最大 5 MB</span>
                <input className="sr-only" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={handleFileChange} />
                {selectedFile ? <span className="mt-3 text-xs font-semibold text-blue-700">{selectedFile.name}</span> : null}
              </label>

              <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <h2 className="text-base font-bold text-slate-900">执行状态</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">{resultLabel}</p>
                {errorMessage ? <p className="mt-2 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
                <button
                  className="mt-4 inline-flex h-11 w-full items-center justify-center rounded-xl bg-blue-600 px-4 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                  type="submit"
                  disabled={submitting}
                >
                  {submitting ? '检测中…' : '发起检测'}
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
                  <div><dt className="font-semibold">任务状态</dt><dd>{task.status}</dd></div>
                  <div><dt className="font-semibold">创建时间</dt><dd>{task.created_at}</dd></div>
                  <div><dt className="font-semibold">问题总数</dt><dd>{issues.length}</dd></div>
                  <div><dt className="font-semibold">规则快照</dt><dd>{task.rule_snapshot.length} 条</dd></div>
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
            <p className="mt-3 text-sm leading-6 text-slate-600">{touched ? '本次检测未返回问题。' : '尚未检测任何文本。'}</p>
          )}
        </section>
      </section>
    </main>
  );
}

export default NormativeCheckPage;
