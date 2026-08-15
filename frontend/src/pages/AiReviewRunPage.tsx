import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { Check, FileText, FileUp, Info, ListChecks, Sparkles } from 'lucide-react';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  createAiReviewRun,
  fetchReviewRubrics,
  type AiReviewRunResponse,
  type ReviewRubricTemplate,
  type ReviewRubricsResponse,
} from '../api/normativeRules';
import { Button, Card, ErrorState, LinkButton, LoadingState, PageHeader } from '../components/ui';
import { extractThesisFileText, THESIS_FILE_ACCEPT } from '../utils/thesisFileText';

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
      <PageHeader
        title="AI 智能评阅"
        description="为论文准备一份结构化的辅助评阅底稿，供作者完善和导师后续复核。"
        actions={
          <LinkButton size="sm" variant="secondary" to="/ai-review/history">
            评阅记录
          </LinkButton>
        }
      />

      <section className="border-y border-slate-200 bg-white" aria-label="评阅说明">
        <div className="mx-auto flex max-w-7xl items-start gap-3 px-6 py-4 lg:px-8">
          <ListChecks className="mt-0.5 h-5 w-5 shrink-0 text-brand-700" aria-hidden="true" />
          <div className="text-sm leading-6 text-slate-600">
            <span className="font-semibold text-slate-800">使用方式：</span>
            填写题目与论文文本，选择适用的评阅模板后生成辅助结果。结果用于完善论文和支持人工判断，不替代导师或专家评阅。
          </div>
        </div>
      </section>

      <form className="mx-auto max-w-7xl px-6 py-8 lg:px-8" onSubmit={handleSubmit}>
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.8fr)]">
          <Card title="论文材料" description="上传可提取文本的论文文件，或直接粘贴需要评阅的文本。" className="p-6">
            <label className="block text-sm font-semibold text-slate-800">
              论文题目
              <input
                className="mt-2 h-11 w-full rounded-lg border border-slate-300 bg-white px-3.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                aria-label="论文题目"
                value={thesisTitle}
                onChange={(event) => setThesisTitle(event.target.value)}
                placeholder="例如：高校数字治理平台评阅研究"
              />
              {fieldErrors.thesis_title ? (
                <span className="mt-2 block text-sm font-normal text-red-600">{fieldErrors.thesis_title}</span>
              ) : null}
            </label>

            <label
              className={`mt-6 flex cursor-pointer items-center gap-4 rounded-lg border border-dashed px-5 py-4 transition ${dragOver ? 'border-brand-500 bg-brand-50' : 'border-slate-300 bg-slate-50 hover:border-brand-500 hover:bg-brand-50/60'}`}
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
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
                <FileUp className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="min-w-0 text-left">
                <span className="block text-sm font-semibold text-slate-800">上传论文文件</span>
                <span className="mt-0.5 block text-xs leading-5 text-slate-500">
                  支持 .txt、.md 与可搜索文本 PDF，最大 50 MB
                </span>
                {selectedFile ? (
                  <span className="mt-1 block truncate text-xs font-semibold text-brand-700">
                    已选择：{selectedFile.name}
                  </span>
                ) : null}
              </span>
              <span className="ml-auto hidden rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-600 sm:block">
                选择文件
              </span>
              <input className="sr-only" type="file" accept={THESIS_FILE_ACCEPT} onChange={handleFileChange} />
            </label>

            <div className="my-5 flex items-center gap-3 text-xs text-slate-400" aria-hidden="true">
              <span className="h-px flex-1 bg-slate-200" />
              或直接粘贴文本
              <span className="h-px flex-1 bg-slate-200" />
            </div>

            <label className="block text-sm font-semibold text-slate-800">
              论文文本
              <textarea
                className="mt-2 min-h-72 w-full resize-y rounded-lg border border-slate-300 bg-white p-3.5 text-sm leading-7 outline-none transition placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                aria-label="论文文本"
                value={text}
                onChange={(event) => {
                  setText(event.target.value);
                  setSelectedFile(null);
                }}
                placeholder="建议包含摘要、关键词、引言、研究方法、结论和参考文献等正文内容。"
              />
              <span className="mt-2 flex items-center justify-between text-xs font-normal text-slate-500">
                <span>仅用于本次辅助评阅。</span>
                <span>{text.length.toLocaleString()} 字</span>
              </span>
              {fieldErrors.text ? (
                <span className="mt-2 block text-sm font-normal text-red-600">{fieldErrors.text}</span>
              ) : null}
            </label>
          </Card>

          <div className="space-y-6 xl:sticky xl:top-6">
            <Card title="评阅设置" description="选择与当前培养类型相符的模板。" className="p-6">
              <section aria-labelledby="review-template-heading">
                <h2 id="review-template-heading" className="sr-only">
                  选择评阅模板
                </h2>
                {loadingRubrics ? <LoadingState label="正在加载评阅模板…" compact /> : null}
                {rubricError ? <ErrorState message={rubricError} /> : null}
                {rubrics ? (
                  <div className="space-y-2">
                    {rubrics.templates.map((template) => {
                      const selected = template.template_id === selectedTemplateId;
                      return (
                        <button
                          key={template.template_id}
                          aria-label={template.name}
                          aria-pressed={selected}
                          className={`flex w-full items-center gap-3 rounded-lg border p-3.5 text-left transition ${selected ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-slate-200 bg-white hover:border-brand-300 hover:bg-slate-50'}`}
                          type="button"
                          onClick={() => setSelectedTemplateId(template.template_id)}
                        >
                          <span
                            className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${selected ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white'}`}
                          >
                            {selected ? <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden="true" /> : null}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-semibold text-slate-800">{template.name}</span>
                            <span className="mt-0.5 block text-xs text-slate-500">
                              最低参考文献 {template.minimum_reference_count} 条
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
                {selectedTemplate ? (
                  <div className="mt-5 rounded-lg border border-brand-100 bg-brand-50/70 p-4">
                    <div className="flex gap-2">
                      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-brand-700" aria-hidden="true" />
                      <div>
                        <p className="text-xs font-semibold text-brand-900">本模板关注的必要章节</p>
                        <p className="mt-1 text-xs leading-5 text-slate-600">
                          必需章节：{selectedTemplate.required_sections.join('、')}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : null}
              </section>
              {rubrics ? (
                <Button className="mt-6 w-full" size="lg" type="submit" disabled={!canSubmit} aria-label="智能评阅">
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  {readingFile ? '正在解析文件…' : submitting ? '正在生成辅助结果…' : '生成辅助评阅'}
                </Button>
              ) : null}
            </Card>

            <div className="flex gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3.5 text-xs leading-5 text-slate-500 shadow-sm">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
              <p>系统根据文本结构和已配置规则形成检查意见；请结合论文实际情况作出判断。</p>
            </div>
          </div>
        </div>
        {errorMessage ? (
          <div className="mt-6">
            <ErrorState title="提交失败" message={errorMessage} />
          </div>
        ) : null}
      </form>

      {result ? (
        <section className="mx-auto max-w-7xl px-8 pb-12" aria-labelledby="ai-review-result-heading">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
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
