import { ChangeEvent, FormEvent, useMemo, useState } from 'react';
import { createDuplicationDetection, type DuplicationDetectionResponse } from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Card, LinkButton, LoadingState, PageHeader } from '../components/ui';
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

  const progress = useMemo(() => (submitting ? 68 : report ? 100 : 0), [report, submitting]);

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
      <section className="mx-auto max-w-5xl">
        <form className="rounded-[28px] border border-[#B8B8B8] bg-white p-8" onSubmit={handleSubmit}>
          <div className="flex items-center gap-3 text-3xl font-black text-[#111111]">
            <span className="flex h-8 w-8 items-center justify-center rounded-full border-4 border-black text-sm">
              ◎
            </span>
            文档上传
          </div>

          <label className="mt-8 flex min-h-[340px] cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed border-transparent text-center transition hover:border-blue-300 hover:bg-blue-50/40">
            <span className="text-6xl leading-none">▯</span>
            <span className="mt-5 text-2xl font-black text-[#111111]">
              {selectedFile ? selectedFile.name : '点击或将文件拖拽至此处上传'}
            </span>
            <span className="mt-3 text-sm font-bold text-slate-500">
              文本文件、可搜索文本 PDF 及提取文本最大均为 50 MB，也可在下方粘贴文本
            </span>
            <input className="sr-only" type="file" accept={THESIS_FILE_ACCEPT} onChange={handleFileChange} />
          </label>

          <textarea
            className="mt-5 min-h-[160px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm leading-7 outline-none focus:border-blue-500"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="粘贴待检测论文文本，系统将与试点样本库比对相似片段。"
          />

          <div className="mt-6 flex flex-col items-center justify-center gap-5 sm:flex-row">
            <select
              className="h-16 rounded-full border border-[#B8B8B8] bg-white px-8 text-lg font-black text-[#111111] outline-none focus:border-blue-500"
              value={selectedType}
              onChange={(event) => setSelectedType(event.target.value)}
            >
              {DETECTION_TYPES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              className="h-16 rounded-full bg-[#2448E8] px-16 text-xl font-black text-white shadow-[0_5px_0_#1736C8] disabled:cursor-not-allowed disabled:opacity-50"
              type="submit"
              disabled={readingFile || submitting || !text.trim() || selectedType !== 'local-similarity'}
            >
              {readingFile ? '解析中…' : submitting ? '检测中…' : '检测'}
            </button>
          </div>
          {errorMessage ? <p className="mt-5 text-center text-sm font-semibold text-red-600">{errorMessage}</p> : null}
        </form>

        {submitting || report ? (
          <section className="mt-8 rounded-[28px] border border-[#9A9A9A] bg-white p-8">
            <div className="flex items-center gap-3 text-2xl font-black text-[#111111]">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-sm text-white">
                ●
              </span>
              检测进度
            </div>
            <div className="mt-8 flex flex-col items-center">
              <div className="flex h-44 w-44 items-center justify-center rounded-full border-[18px] border-blue-600 bg-white text-4xl font-black text-blue-700">
                {progress}%
              </div>
              <p className="mt-5 text-lg font-black text-[#111111]">
                {submitting ? '检测进行中，请稍后' : '检测已完成'}
              </p>
              <div className="mt-5 h-3 w-full rounded-full bg-[#DCEBFA]">
                <div
                  className="h-3 rounded-full bg-gradient-to-r from-[#294FE0] to-[#1F43C8]"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {report ? (
              <div className="mt-8 space-y-6">
                <p className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-bold text-blue-800">
                  写作风险分为启发式风险提示，并非 AI 真伪结论。
                </p>
                <dl className="grid gap-3 text-sm font-bold text-slate-800 sm:grid-cols-2">
                  <div>比对样本数：{report.sample_count}</div>
                  <div>总相似率：{Math.round(report.total_similarity_rate * 100)}%</div>
                  <div>有效字符数：{report.effective_character_count}</div>
                  <div>风险分：{Math.round(report.risk.score)}</div>
                </dl>
                {report.status === 'no_samples' ? (
                  <p className="rounded-2xl border border-dashed border-slate-300 px-4 py-3 text-sm font-semibold text-slate-600">
                    无可用样本，未伪造比对结果。
                  </p>
                ) : null}
                <div className="space-y-3">
                  {report.top_matches.map((match) => (
                    <article key={match.sample_id} className="rounded-2xl border border-slate-200 p-4">
                      <h2 className="font-black text-slate-900">{match.title}</h2>
                      <p className="mt-1 text-sm text-slate-500">
                        Jaccard：{match.jaccard_score.toFixed(3)} · 命中字符：{match.matched_character_count}
                      </p>
                      <div className="mt-3 space-y-2">
                        {match.segments.map((segment) => (
                          <blockquote
                            key={`${segment.source_start}-${segment.sample_start}`}
                            className="rounded-xl border-l-4 border-blue-500 bg-slate-50 px-3 py-2 text-sm font-semibold leading-6 text-slate-700"
                          >
                            {segment.source_excerpt}
                          </blockquote>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
        ) : null}
      </section>
    </div>
  );
}

export default DuplicationDetectPage;
