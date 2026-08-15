import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  createAiReviewRun,
  fetchReviewRubrics,
  type AiReviewRunResponse,
  type ReviewRubricTemplate,
  type ReviewRubricsResponse,
} from '../api/normativeRules';
import { Card, ErrorState, LinkButton, LoadingState, ModuleTabs, PageHeader } from '../components/ui';
import { extractThesisFileText, THESIS_FILE_ACCEPT } from '../utils/thesisFileText';

const STEPS = ['论文上传', '模板选择', '智能评阅'];
const TEMPLATE_ICON_COLORS = ['bg-[#3b86f6]', 'bg-[#28ae6f]', 'bg-[#f59e0b]', 'bg-[#8b5cf6]', 'bg-[#ef4444]'];

function AiReviewRunPage() {
  const { status, user } = useAuthSession();
  const [rubrics, setRubrics] = useState<ReviewRubricsResponse | null>(null);
  const [rubricError, setRubricError] = useState<string | null>(null);
  const [loadingRubrics, setLoadingRubrics] = useState(false);
  const [thesisTitle, setThesisTitle] = useState('');
  const [text, setText] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
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
        setSelectedTemplateId(
          (current) =>
            current ||
            data.templates.find((template) => template.template_id === 'academic_master')?.template_id ||
            data.templates[0]?.template_id ||
            '',
        );
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
  }, [rubrics, user]);

  const selectedTemplate = useMemo<ReviewRubricTemplate | null>(() => {
    return rubrics?.templates.find((template) => template.template_id === selectedTemplateId) || null;
  }, [rubrics, selectedTemplateId]);

  const canSubmit = Boolean(
    user && thesisTitle.trim() && text.trim() && selectedTemplateId && !submitting && !readingFile,
  );

  async function applyFile(file: File | null) {
    setErrorMessage(null);
    setFieldErrors({});
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
      const maybeErrors = (error as { response?: { data?: { errors?: Array<{ field: string; message: string }> } } })
        ?.response?.data?.errors;
      if (Array.isArray(maybeErrors)) {
        setFieldErrors(Object.fromEntries(maybeErrors.map((item) => [item.field, item.message])));
      }
      setErrorMessage(error instanceof Error ? error.message : '辅助评阅发起失败');
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
          <h1 className="text-3xl font-black text-[#1f3f63]">AI 智能评阅</h1>
          <p className="mt-4 text-slate-600">请先登录后选择模板并发起辅助评阅，后台会在生成结果前执行角色授权。</p>
          <LinkButton className="mt-6" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  return (
    <div className="font-sans text-slate-900">
      <PageHeader title="AI 智能评阅" />
      <ModuleTabs
        ariaLabel="AI 智能评阅功能导航"
        items={[
          { label: '发起评阅', to: '/ai-review', active: true },
          { label: '评阅记录', to: '/ai-review/history', active: false },
        ]}
      />

      <section className="flex h-32 items-center justify-center bg-[#eef0f3]" aria-label="评阅流程进度">
        <div className="flex w-full max-w-4xl items-start justify-between px-8">
          {STEPS.map((step, index) => (
            <div key={step} className="flex flex-1 items-start last:flex-none">
              <div className="flex flex-col items-center">
                <span
                  className={`flex h-12 w-12 items-center justify-center rounded-full text-xl font-black ${index === (result ? 2 : selectedTemplateId && text.trim() ? 1 : 0) ? 'bg-[#3b86f6] text-white' : 'border border-slate-300 bg-[#e5e5e5] text-[#8c8c8c]'}`}
                >
                  {index + 1}
                </span>
                <span
                  className={`mt-2 text-lg font-black ${index === (result ? 2 : selectedTemplateId && text.trim() ? 1 : 0) ? 'text-[#3b86f6]' : 'text-[#8c8c8c]'}`}
                >
                  {step}
                </span>
              </div>
              {index < STEPS.length - 1 ? <span className="mt-6 h-px flex-1 bg-slate-300" /> : null}
            </div>
          ))}
        </div>
      </section>

      <form className="mx-auto max-w-7xl px-8 py-12" onSubmit={handleSubmit}>
        <label className="block text-xl font-black text-[#1f3f63]">
          论文题目
          <input
            className="mt-3 h-14 w-full rounded-lg border border-[#d6d6d6] bg-white px-4 text-base outline-none focus:border-[#3b86f6]"
            value={thesisTitle}
            onChange={(event) => setThesisTitle(event.target.value)}
          />
          {fieldErrors.thesis_title ? (
            <span className="mt-2 block text-sm text-red-600">{fieldErrors.thesis_title}</span>
          ) : null}
        </label>

        <label
          className={`mt-8 flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-md border-[3px] border-dashed px-6 text-center transition ${dragOver ? 'border-[#3b86f6] bg-blue-50' : 'border-[#3b86f6] bg-[#fafafa]'}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragOver(false);
            void applyFile(event.dataTransfer.files?.[0] || null);
          }}
        >
          <span className="flex h-16 w-16 items-center justify-center rounded-full border-2 border-[#3b86f6] text-3xl font-black text-[#3b86f6]">
            ↑
          </span>
          <span className="mt-4 text-3xl font-black text-slate-900">拖拽或点击上传论文</span>
          <span className="mt-2 text-lg text-slate-500">
            文本文件、可搜索文本 PDF 及提取文本最大均为 50 MB；也可在下方直接粘贴文本
          </span>
          <input className="sr-only" type="file" accept={THESIS_FILE_ACCEPT} onChange={handleFileChange} />
          {selectedFile ? <span className="mt-3 text-base font-bold text-[#3b86f6]">{selectedFile.name}</span> : null}
        </label>

        <label className="mt-6 block text-lg font-black text-[#1f3f63]">
          论文文本
          <textarea
            className="mt-3 min-h-56 w-full rounded-lg border border-[#d6d6d6] bg-white p-4 leading-7 outline-none focus:border-[#3b86f6]"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setSelectedFile(null);
            }}
            placeholder="粘贴摘要、关键词、引言、研究方法、结论和参考文献等论文文本。"
          />
          {fieldErrors.text ? <span className="mt-2 block text-sm text-red-600">{fieldErrors.text}</span> : null}
        </label>

        <section className="mt-10" aria-labelledby="review-template-heading">
          <h2 id="review-template-heading" className="text-2xl font-black text-[#1f3f63]">
            选择评阅模板
          </h2>
          {loadingRubrics ? <LoadingState label="正在加载评阅模板…" compact /> : null}
          {rubricError ? <ErrorState message={rubricError} /> : null}
          {rubrics ? (
            <div className="mt-5 grid gap-5 lg:grid-cols-5">
              {rubrics.templates.map((template, index) => {
                const selected = template.template_id === selectedTemplateId;
                return (
                  <button
                    key={template.template_id}
                    aria-label={template.name}
                    className={`relative min-h-[190px] rounded-[10px] border bg-white p-5 text-center transition hover:shadow ${selected ? 'border-[3px] border-[#3b86f6] bg-blue-50' : 'border-[#d6d6d6]'}`}
                    type="button"
                    onClick={() => setSelectedTemplateId(template.template_id)}
                  >
                    {selected ? (
                      <span className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-[#3b86f6] text-sm font-black text-white">
                        ✓
                      </span>
                    ) : null}
                    <span
                      className={`mx-auto flex h-14 w-14 items-center justify-center rounded-xl ${TEMPLATE_ICON_COLORS[index % TEMPLATE_ICON_COLORS.length]} text-xl font-black text-white`}
                    >
                      文
                    </span>
                    <span className="mt-4 block text-xl font-black text-slate-900">{template.name}</span>
                    <span className="mt-2 block text-sm font-bold text-slate-500">
                      最低参考文献 {template.minimum_reference_count} 条
                    </span>
                  </button>
                );
              })}
            </div>
          ) : null}
          {selectedTemplate ? (
            <p className="mt-4 text-sm font-semibold text-slate-600">
              必需章节：{selectedTemplate.required_sections.join('、')}
            </p>
          ) : null}
        </section>

        {rubrics ? (
          <button
            className="mx-auto mt-12 flex h-20 w-full max-w-2xl items-center justify-center rounded-md bg-[#28ae6f] text-3xl font-black text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            type="submit"
            disabled={!canSubmit}
          >
            {readingFile ? '解析中…' : submitting ? '智能评阅中…' : '智能评阅'}
          </button>
        ) : null}
        {errorMessage ? <ErrorState title="提交失败" message={errorMessage} /> : null}
      </form>

      {result ? (
        <section className="mx-auto max-w-7xl px-8 pb-12" aria-labelledby="ai-review-result-heading">
          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
            <h2 id="ai-review-result-heading" className="text-2xl font-black text-[#1f3f63]">
              评阅结果
            </h2>
            <p className="mt-4 text-4xl font-black text-[#3b86f6]">
              {result.total_score} 分 · {result.result_label}
            </p>
            {result.missing_sections.length > 0 ? (
              <p className="mt-3 font-bold text-red-600">缺失章节：{result.missing_sections.join('、')}</p>
            ) : null}
            <dl className="mt-5 grid gap-3 text-sm text-slate-700 sm:grid-cols-3">
              <div>
                <dt className="font-bold">字符数</dt>
                <dd>{result.character_count}</dd>
              </div>
              <div>
                <dt className="font-bold">参考文献条目</dt>
                <dd>{result.reference_count}</dd>
              </div>
              <div>
                <dt className="font-bold">规范问题</dt>
                <dd>{result.normative_issues.length}</dd>
              </div>
            </dl>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default AiReviewRunPage;
