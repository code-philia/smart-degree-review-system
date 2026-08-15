import { ChangeEvent, FormEvent, useState } from 'react';
import { FileText, Upload } from 'lucide-react';
import { createDuplicationDetection, type DuplicationDetectionResponse } from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Button, Card, LinkButton, LoadingState, PageHeader, StatusBadge } from '../components/ui';
import { extractThesisFileText, THESIS_FILE_ACCEPT } from '../utils/thesisFileText';

const DETECTION_TYPES = [{ value: 'local-similarity', label: '论文相似度检测' }];

function DuplicationDetectPage() {
  const { status, user } = useAuthSession();
  const [text, setText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedType, setSelectedType] = useState(DETECTION_TYPES[0].value);
  const [report, setReport] = useState<DuplicationDetectionResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
    setSubmitting(true);
    setErrorMessage(null);
    setReport(null);

    try {
      const result = await createDuplicationDetection({
        text,
        source_type: selectedFile ? 'file' : 'paste',
        source_filename: selectedFile?.name || null,
      });
      setReport(result);
      setText('');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '相似度检测失败');
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
          <h1 className="text-2xl font-black text-slate-900">发起论文相似度检测</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后发起相似度与写作风险检测。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="论文相似度检测"
        description="上传论文或粘贴文本，与试点样本库比对相似片段。"
        actions={
          <LinkButton size="sm" variant="secondary" to="/duplication-history">
            历史记录
          </LinkButton>
        }
      />
      <section className="mx-auto max-w-6xl space-y-6">
        <form className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" onSubmit={handleSubmit}>
          <div className="mb-5 border-b border-slate-100 pb-5">
            <h2 className="text-lg font-bold text-slate-900">发起检测</h2>
            <p className="mt-1 text-sm text-slate-500">提交后将与当前试点样本库进行相似片段比对。</p>
          </div>
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,.65fr)]">
            <div className="space-y-4">
              <div>
                <p className="text-sm font-bold text-slate-800">论文内容</p>
                <p className="mt-1 text-xs text-slate-500">上传文件后将提取文本；也可直接粘贴待检测内容。</p>
              </div>
              <label className="flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 p-5 text-center transition hover:border-brand-400 hover:bg-brand-50/40">
                {selectedFile ? (
                  <FileText className="size-8 text-brand-600" />
                ) : (
                  <Upload className="size-8 text-brand-600" />
                )}
                <span className="mt-3 max-w-full truncate text-sm font-bold text-slate-900">
                  {selectedFile ? selectedFile.name : '选择论文文件'}
                </span>
                <span className="mt-1 text-xs text-slate-500">支持文本文件与可搜索文本 PDF，最大 50 MB</span>
                <input className="sr-only" type="file" accept={THESIS_FILE_ACCEPT} onChange={handleFileChange} />
              </label>
              <label className="block text-sm font-bold text-slate-800">
                或直接粘贴文本
                <textarea
                  className="mt-2 min-h-44 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm leading-7 font-normal outline-none focus:border-brand-500"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="粘贴待检测论文文本，系统将与试点样本库比对相似片段。"
                />
              </label>
            </div>

            <aside className="flex flex-col rounded-xl border border-slate-200 bg-slate-50 p-5">
              <div>
                <p className="text-sm font-bold text-slate-900">检测设置</p>
                <label className="mt-4 block text-sm font-medium text-slate-700">
                  检测类型
                  <select
                    className="mt-2 h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-brand-500"
                    value={selectedType}
                    onChange={(event) => setSelectedType(event.target.value)}
                  >
                    {DETECTION_TYPES.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="mt-5 text-xs leading-5 text-slate-500">
                  检测范围为当前试点样本库；结果中的写作风险仅作启发式提示。
                </p>
              </div>
              <Button
                className="mt-6 w-full"
                size="lg"
                type="submit"
                disabled={readingFile || submitting || !text.trim() || selectedType !== 'local-similarity'}
              >
                {readingFile ? '正在解析文件…' : submitting ? '正在检测…' : '开始检测'}
              </Button>
            </aside>
          </div>
          {errorMessage ? <p className="mt-4 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
        </form>

        {submitting ? (
          <Card>
            <div className="flex items-center gap-3">
              <span className="size-2 animate-pulse rounded-full bg-brand-500" />
              <div>
                <p className="font-bold text-slate-900">正在与试点样本库比对</p>
                <p className="mt-1 text-sm text-slate-500">完成后将展示真实的检测结果。</p>
              </div>
            </div>
          </Card>
        ) : null}

        {report ? (
          <Card
            title="检测结果"
            description="本次检测已完成，可依据相似片段进一步核对。"
            actions={<StatusBadge tone={report.status === 'no_samples' ? 'neutral' : 'success'}>已完成</StatusBadge>}
          >
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {[
                ['比对样本数', report.sample_count],
                ['总相似率', `${Math.round(report.total_similarity_rate * 100)}%`],
                ['有效字符数', report.effective_character_count],
                ['风险分', Math.round(report.risk.score)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">{label}</p>
                  <p className="mt-1 text-2xl font-black text-slate-900">{value}</p>
                </div>
              ))}
            </div>
            <div className="mt-5 space-y-4">
              <p className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                写作风险分为启发式风险提示，并非 AI 真伪结论。
              </p>
              {report.status === 'no_samples' ? (
                <p className="rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm text-slate-600">
                  当前样本库没有可用比对样本，因此未生成相似片段。
                </p>
              ) : null}
              {report.top_matches.length > 0 ? (
                <section aria-labelledby="similarity-matches-heading" className="space-y-3">
                  <h3 id="similarity-matches-heading" className="text-sm font-bold text-slate-900">
                    相似片段
                  </h3>
                  {report.top_matches.map((match) => (
                    <article key={match.sample_id} className="rounded-lg border border-slate-200 p-4">
                      <h4 className="font-bold text-slate-900">{match.title}</h4>
                      <p className="mt-1 text-sm text-slate-500">
                        Jaccard：{match.jaccard_score.toFixed(3)} · 命中字符：{match.matched_character_count}
                      </p>
                      <div className="mt-3 space-y-2">
                        {match.segments.map((segment) => (
                          <blockquote
                            key={`${segment.source_start}-${segment.sample_start}`}
                            className="rounded-md border-l-4 border-brand-500 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700"
                          >
                            {segment.source_excerpt}
                          </blockquote>
                        ))}
                      </div>
                    </article>
                  ))}
                </section>
              ) : null}
            </div>
          </Card>
        ) : null}
      </section>
    </div>
  );
}

export default DuplicationDetectPage;
