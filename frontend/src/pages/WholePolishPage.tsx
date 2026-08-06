import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Button, Card, LinkButton, LoadingState } from '../components/ui';
import {
  createWholePolishResult,
  downloadWholePolishText,
  fetchWholePolishResult,
  type WholePolishLevel,
  type WholePolishResult,
} from '../api/normativeRules';

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const ACCEPTED_FILE_EXTENSIONS = ['.txt', '.md'];

const LEVEL_OPTIONS: Array<{
  level: WholePolishLevel;
  title: string;
  summary: string;
  accent: string;
  recommended?: boolean;
}> = [
  { level: 'basic', title: '基础校准', summary: '空白、重复标点与连续重复词校准', accent: 'text-blue-600' },
  {
    level: 'standard',
    title: '标准优化',
    summary: '叠加管理员维护的短语替换映射',
    accent: 'text-orange-600',
    recommended: true,
  },
  { level: 'enhanced', title: '增强优化', summary: '进一步拆分过长且含合法分隔符的句子', accent: 'text-red-500' },
];

function getFileExtension(fileName: string) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

function WholePolishPage() {
  const { resultId } = useParams();
  const { status, user } = useAuthSession();
  const [text, setText] = useState('');
  const [level, setLevel] = useState<WholePolishLevel>('standard');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<WholePolishResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loadingResult, setLoadingResult] = useState(false);

  const canSubmit = useMemo(() => Boolean(text.trim()) && !submitting, [text, submitting]);

  useEffect(() => {
    if (!resultId || !user) {
      return;
    }

    let active = true;
    setLoadingResult(true);
    setErrorMessage(null);
    fetchWholePolishResult(resultId)
      .then((response) => {
        if (active) {
          setResult(response);
        }
      })
      .catch((error) => {
        if (active) {
          setErrorMessage(error instanceof Error ? error.message : '润色结果加载失败');
        }
      })
      .finally(() => {
        if (active) {
          setLoadingResult(false);
        }
      });

    return () => {
      active = false;
    };
  }, [resultId, user]);

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
      setText(await readSelectedFile(file));
    } catch (error) {
      setSelectedFile(null);
      setText('');
      setErrorMessage(error instanceof Error ? error.message : '文件读取失败，请确认文件为 UTF-8 文本');
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await createWholePolishResult({
        text,
        level,
        source_type: selectedFile ? 'file' : 'paste',
        source_filename: selectedFile?.name || null,
      });
      setResult(response);
    } catch (error) {
      setResult(null);
      setErrorMessage(error instanceof Error ? error.message : '全文润色失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDownload() {
    if (!result) {
      return;
    }
    const blob = await downloadWholePolishText(result.id);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `whole-polish-${result.id}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (status === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">全文规则润色</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            请先登录后粘贴文本或上传文档，系统会保存可追溯润色结果。
          </p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  return (
    <div className="text-slate-900">
      <h1 className="text-3xl font-black text-[#1F3D60]">全文润色</h1>

      <form className="mx-auto mt-6 max-w-6xl" onSubmit={handleSubmit}>
        <label className="flex min-h-[320px] cursor-pointer flex-col items-center justify-center rounded-[40px] border-2 border-dashed border-[#AFC2DD] bg-white px-6 text-center transition hover:border-blue-500 hover:bg-blue-50/40">
          <span
            className="flex h-20 w-20 items-center justify-center rounded-full bg-blue-100 text-2xl text-blue-600"
            aria-hidden="true"
          >
            📄
          </span>
          <span className="mt-5 text-2xl font-black">拖拽或点击上传文档</span>
          <span className="mt-3 text-lg text-slate-500">支持 .txt / .md，也可以在下方直接粘贴文本</span>
          <input
            className="sr-only"
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            onChange={handleFileChange}
          />
        </label>

        <label className="mt-6 block text-sm font-bold text-slate-700" htmlFor="whole-polish-textarea">
          粘贴文本
        </label>
        <textarea
          id="whole-polish-textarea"
          className="mt-2 min-h-36 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm leading-7 outline-none focus:border-blue-500"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="粘贴需要全文润色的文本。"
        />

        <h2 className="mt-10 text-2xl font-black">选择润色等级</h2>
        <div className="mt-5 grid gap-5 lg:grid-cols-3">
          {LEVEL_OPTIONS.map((option) => {
            const selected = option.level === level;
            return (
              <button
                key={option.level}
                type="button"
                className={`rounded-3xl border p-6 text-left transition ${selected ? 'border-orange-500 bg-[#FFF9F3]' : 'border-slate-200 bg-white hover:border-blue-300'}`}
                onClick={() => setLevel(option.level)}
              >
                <span className="flex items-center gap-3">
                  <span
                    className={`h-5 w-5 rounded-full border ${selected ? 'border-orange-500 bg-orange-500' : 'border-slate-300'}`}
                  />
                  <span className={`text-2xl font-black ${option.accent}`}>{option.title}</span>
                  {option.recommended ? (
                    <span className="rounded-full bg-orange-500 px-3 py-1 text-xs font-bold text-white">推荐</span>
                  ) : null}
                </span>
                <span className="mt-4 block text-base leading-7 text-slate-600">{option.summary}</span>
              </button>
            );
          })}
        </div>

        {errorMessage ? (
          <p className="mt-5 rounded-xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-600">{errorMessage}</p>
        ) : null}

        <Button
          className="mx-auto mt-10 flex h-20 w-full max-w-md text-2xl"
          size="lg"
          type="submit"
          disabled={!canSubmit}
        >
          {submitting ? '润色中…' : '智能润色'}
        </Button>
      </form>

      {loadingResult ? <LoadingState label="正在加载润色结果…" /> : null}

      {result ? (
        <section className="mx-auto max-w-6xl px-6 pb-12">
          <div className="rounded-3xl border border-slate-200 bg-[#F8FAFC] p-6">
            <div className="grid gap-8 lg:grid-cols-[240px_minmax(0,1fr)]">
              <div className="flex h-52 w-52 flex-col items-center justify-center rounded-full border-[10px] border-green-500 bg-white text-center">
                <span className="text-5xl font-black text-green-500">✓</span>
                <span className="mt-2 font-black">润色完成</span>
              </div>
              <div className="space-y-3 text-sm">
                <p>
                  <span className="text-slate-500">结果编号：</span>
                  <strong data-testid="whole-polish-result-id">{result.id}</strong>
                </p>
                <p>
                  <span className="text-slate-500">文档名称：</span>
                  <strong>{result.source_filename || '粘贴文本'}</strong>
                </p>
                <p>
                  <span className="text-slate-500">润色档位：</span>
                  <strong className="text-orange-600">
                    {result.level === 'standard' ? '标准优化' : result.level === 'enhanced' ? '增强优化' : '基础校准'}
                  </strong>
                </p>
                <p>
                  <span className="text-slate-500">变更数量：</span>
                  <strong>{result.changes.length}</strong>
                </p>
                <p>
                  <span className="text-slate-500">完成时间：</span>
                  <strong>{result.created_at}</strong>
                </p>
              </div>
            </div>
            <div className="mt-6 rounded-2xl bg-white p-5">
              <h2 className="text-xl font-black text-slate-900">润色结果</h2>
              <p className="mt-3 whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm leading-7 text-slate-800">
                {result.polished_text}
              </p>
            </div>
            <div className="mt-6 rounded-2xl bg-white p-5">
              <h2 className="text-xl font-black text-slate-900">变更明细</h2>
              <ul className="mt-3 space-y-3" aria-label="变更列表">
                {result.changes.map((change, index) => (
                  <li
                    key={`${change.position}-${index}`}
                    className="rounded-xl border border-slate-200 p-4 text-sm leading-6"
                  >
                    <p>
                      <span className="font-bold text-slate-500">原文：</span>
                      {change.original_text}
                    </p>
                    <p>
                      <span className="font-bold text-slate-500">新文：</span>
                      {change.new_text}
                    </p>
                    <p>
                      <span className="font-bold text-slate-500">位置：</span>
                      {change.position}
                    </p>
                    <p>
                      <span className="font-bold text-slate-500">规则：</span>
                      {change.rule}
                    </p>
                    {change.reason ? (
                      <p>
                        <span className="font-bold text-slate-500">原因：</span>
                        {change.reason}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
            <div className="mt-6 flex flex-wrap justify-center gap-4">
              <LinkButton to={`/whole-polish/${result.id}`}>查看结果</LinkButton>
              <button
                className="rounded-lg bg-green-500 px-8 py-3 font-bold text-white"
                type="button"
                onClick={handleDownload}
              >
                下载 UTF-8 TXT
              </button>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default WholePolishPage;
