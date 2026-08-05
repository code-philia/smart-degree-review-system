import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  createAiReviewRun,
  fetchReviewRubrics,
  type AiReviewRunResponse,
  type ReviewRubricTemplate,
  type ReviewRubricsResponse,
} from '../api/normativeRules';

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const ACCEPTED_FILE_EXTENSIONS = ['.txt', '.md'];
const STEPS = ['论文上传', '模板选择', '智能评阅'];
const TEMPLATE_ICON_COLORS = ['bg-[#3b86f6]', 'bg-[#28ae6f]', 'bg-[#f59e0b]', 'bg-[#8b5cf6]', 'bg-[#ef4444]'];

function getFileExtension(fileName: string) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

async function readSelectedFile(file: File) {
  if (!ACCEPTED_FILE_EXTENSIONS.includes(getFileExtension(file.name))) {
    throw new Error('仅支持上传 .txt 或 .md 文件');
  }
  if (file.size > MAX_FILE_BYTES) {
    throw new Error('文件大小不能超过 5 MB');
  }
  return file.text();
}

function AiReviewRunPage() {
  const { status, user } = useAuthSession();
  const [rubrics, setRubrics] = useState<ReviewRubricsResponse | null>(null);
  const [rubricError, setRubricError] = useState<string | null>(null);
  const [loadingRubrics, setLoadingRubrics] = useState(false);
  const [activeTab, setActiveTab] = useState<'upload' | 'history'>('upload');
  const [thesisTitle, setThesisTitle] = useState('');
  const [text, setText] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<AiReviewRunResponse | null>(null);

  useEffect(() => {
    if (!user || rubrics || loadingRubrics) {
      return;
    }

    let mounted = true;
    setLoadingRubrics(true);
    setRubricError(null);
    fetchReviewRubrics()
      .then((data) => {
        if (!mounted) {
          return;
        }
        setRubrics(data);
        setSelectedTemplateId((current) => current || data.templates[0]?.template_id || '');
      })
      .catch((error) => {
        if (!mounted) {
          return;
        }
        setRubricError(error instanceof Error ? error.message : '评阅模板加载失败');
      })
      .finally(() => {
        if (mounted) {
          setLoadingRubrics(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [loadingRubrics, rubrics, user]);

  const selectedTemplate = useMemo<ReviewRubricTemplate | null>(() => {
    return rubrics?.templates.find((template) => template.template_id === selectedTemplateId) || null;
  }, [rubrics, selectedTemplateId]);

  const canSubmit = Boolean(user && thesisTitle.trim() && text.trim() && selectedTemplateId && !submitting);

  async function applyFile(file: File | null) {
    setErrorMessage(null);
    setFieldErrors({});
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

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    void applyFile(event.target.files?.[0] || null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setErrorMessage(null);
    setFieldErrors({});
    setResult(null);

    try {
      const response = await createAiReviewRun({
        thesis_title: thesisTitle,
        template_id: selectedTemplateId,
        text,
        source_type: selectedFile ? 'file' : 'paste',
        source_filename: selectedFile?.name || null,
      });
      setResult(response);
    } catch (error) {
      const maybeErrors = (error as { response?: { data?: { errors?: Array<{ field: string; message: string }> } } })?.response?.data?.errors;
      if (Array.isArray(maybeErrors)) {
        setFieldErrors(Object.fromEntries(maybeErrors.map((item) => [item.field, item.message])));
      }
      setErrorMessage(error instanceof Error ? error.message : '辅助评阅发起失败');
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
        <h1 className="text-3xl font-black text-[#1f3f63]">AI 智能评阅</h1>
        <p className="mt-4 text-slate-600">请先登录后选择模板并发起辅助评阅，后台会在生成结果前执行角色授权。</p>
        <Link className="mt-6 inline-flex rounded bg-[#3b86f6] px-5 py-3 font-bold text-white" to="/auth">前往登录</Link>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f5f6f8] font-sans text-slate-900">
      <header className="flex h-24 items-center bg-[#1f3f63] px-7">
        <h1 className="text-4xl font-black text-white">AI 智能评阅</h1>
      </header>

      <nav className="grid h-20 grid-cols-2 text-3xl font-black" aria-label="AI 智能评阅导航">
        <button className={activeTab === 'upload' ? 'bg-[#3b86f6] text-white' : 'bg-[#f2f3f5] text-slate-600'} type="button" onClick={() => setActiveTab('upload')}>论文上传</button>
        <button className={activeTab === 'history' ? 'bg-[#3b86f6] text-white' : 'bg-[#f2f3f5] text-slate-600'} type="button" onClick={() => setActiveTab('history')}>评阅记录</button>
      </nav>

      <section className="flex h-32 items-center justify-center bg-[#eef0f3]" aria-label="评阅流程进度">
        <div className="flex w-full max-w-4xl items-start justify-between px-8">
          {STEPS.map((step, index) => (
            <div key={step} className="flex flex-1 items-start last:flex-none">
              <div className="flex flex-col items-center">
                <span className={`flex h-12 w-12 items-center justify-center rounded-full text-xl font-black ${index === (result ? 2 : selectedTemplateId && text.trim() ? 1 : 0) ? 'bg-[#3b86f6] text-white' : 'border border-slate-300 bg-[#e5e5e5] text-[#8c8c8c]'}`}>{index + 1}</span>
                <span className={`mt-2 text-lg font-black ${index === (result ? 2 : selectedTemplateId && text.trim() ? 1 : 0) ? 'text-[#3b86f6]' : 'text-[#8c8c8c]'}`}>{step}</span>
              </div>
              {index < STEPS.length - 1 ? <span className="mt-6 h-px flex-1 bg-slate-300" /> : null}
            </div>
          ))}
        </div>
      </section>

      {activeTab === 'history' ? (
        <section className="mx-auto max-w-6xl px-8 py-12">
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-600">评阅记录列表由历史记录节点提供；当前页面只负责发起新的规则化辅助评阅。</div>
        </section>
      ) : (
        <form className="mx-auto max-w-7xl px-8 py-12" onSubmit={handleSubmit}>
          <label className="block text-xl font-black text-[#1f3f63]">
            论文题目
            <input className="mt-3 h-14 w-full rounded-lg border border-[#d6d6d6] bg-white px-4 text-base outline-none focus:border-[#3b86f6]" value={thesisTitle} onChange={(event) => setThesisTitle(event.target.value)} />
            {fieldErrors.thesis_title ? <span className="mt-2 block text-sm text-red-600">{fieldErrors.thesis_title}</span> : null}
          </label>

          <label
            className={`mt-8 flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-md border-[3px] border-dashed px-6 text-center transition ${dragOver ? 'border-[#3b86f6] bg-blue-50' : 'border-[#3b86f6] bg-[#fafafa]'}`}
            onDragOver={(event) => { event.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragOver(false);
              void applyFile(event.dataTransfer.files?.[0] || null);
            }}
          >
            <span className="flex h-16 w-16 items-center justify-center rounded-full border-2 border-[#3b86f6] text-3xl font-black text-[#3b86f6]">↑</span>
            <span className="mt-4 text-3xl font-black text-slate-900">拖拽或点击上传论文</span>
            <span className="mt-2 text-lg text-slate-500">支持 .txt / .md，UTF-8 编码，最大 5 MB；也可在下方直接粘贴文本</span>
            <input className="sr-only" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={handleFileChange} />
            {selectedFile ? <span className="mt-3 text-base font-bold text-[#3b86f6]">{selectedFile.name}</span> : null}
          </label>

          <label className="mt-6 block text-lg font-black text-[#1f3f63]">
            论文文本
            <textarea className="mt-3 min-h-56 w-full rounded-lg border border-[#d6d6d6] bg-white p-4 leading-7 outline-none focus:border-[#3b86f6]" value={text} onChange={(event) => { setText(event.target.value); setSelectedFile(null); }} placeholder="粘贴摘要、关键词、引言、研究方法、结论和参考文献等论文文本。" />
            {fieldErrors.text ? <span className="mt-2 block text-sm text-red-600">{fieldErrors.text}</span> : null}
          </label>

          <section className="mt-10" aria-labelledby="review-template-heading">
            <h2 id="review-template-heading" className="text-2xl font-black text-[#1f3f63]">选择评阅模板</h2>
            {loadingRubrics ? <p className="mt-4 rounded-lg bg-blue-50 p-4 font-bold text-blue-700">正在加载评阅模板…</p> : null}
            {rubricError ? <p className="mt-4 rounded-lg bg-red-50 p-4 font-bold text-red-700">{rubricError}</p> : null}
            {rubrics ? (
              <div className="mt-5 grid gap-5 lg:grid-cols-5">
                {rubrics.templates.map((template, index) => {
                  const selected = template.template_id === selectedTemplateId;
                  return (
                    <button key={template.template_id} className={`relative min-h-[190px] rounded-[10px] border bg-white p-5 text-center transition hover:shadow ${selected ? 'border-[3px] border-[#3b86f6] bg-blue-50' : 'border-[#d6d6d6]'}`} type="button" onClick={() => setSelectedTemplateId(template.template_id)}>
                      {selected ? <span className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-[#3b86f6] text-sm font-black text-white">✓</span> : null}
                      <span className={`mx-auto flex h-14 w-14 items-center justify-center rounded-xl ${TEMPLATE_ICON_COLORS[index % TEMPLATE_ICON_COLORS.length]} text-xl font-black text-white`}>文</span>
                      <span className="mt-4 block text-xl font-black text-slate-900">{template.name}</span>
                      <span className="mt-2 block text-sm font-bold text-slate-500">最低参考文献 {template.minimum_reference_count} 条</span>
                    </button>
                  );
                })}
              </div>
            ) : null}
            {selectedTemplate ? <p className="mt-4 text-sm font-semibold text-slate-600">必需章节：{selectedTemplate.required_sections.join('、')}</p> : null}
          </section>

          <button className="mx-auto mt-12 flex h-20 w-full max-w-2xl items-center justify-center rounded-md bg-[#28ae6f] text-3xl font-black text-white disabled:cursor-not-allowed disabled:bg-slate-300" type="submit" disabled={!canSubmit}>{submitting ? '智能评阅中…' : '智能评阅'}</button>
          {errorMessage ? <p className="mt-4 text-center text-sm font-bold text-red-600" role="alert">{errorMessage}</p> : null}
        </form>
      )}

      {result ? (
        <section className="mx-auto max-w-7xl px-8 pb-12" aria-labelledby="ai-review-result-heading">
          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
            <h2 id="ai-review-result-heading" className="text-2xl font-black text-[#1f3f63]">评阅结果</h2>
            <p className="mt-4 text-4xl font-black text-[#3b86f6]">{result.total_score} 分 · {result.result_label}</p>
            {result.missing_sections.length > 0 ? <p className="mt-3 font-bold text-red-600">缺失章节：{result.missing_sections.join('、')}</p> : null}
            <dl className="mt-5 grid gap-3 text-sm text-slate-700 sm:grid-cols-3">
              <div><dt className="font-bold">字符数</dt><dd>{result.character_count}</dd></div>
              <div><dt className="font-bold">参考文献条目</dt><dd>{result.reference_count}</dd></div>
              <div><dt className="font-bold">规范问题</dt><dd>{result.normative_issues.length}</dd></div>
            </dl>
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default AiReviewRunPage;
