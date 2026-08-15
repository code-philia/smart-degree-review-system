import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Button, Card, LinkButton, LoadingState, ModuleTabs, PageHeader } from '../components/ui';
import {
  createWholePolishResult,
  downloadWholePolishText,
  fetchWholePolishResult,
  type WholePolishLevel,
  type WholePolishResult,
} from '../api/normativeRules';
import { extractThesisFileText, THESIS_FILE_ACCEPT } from '../utils/thesisFileText';

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

function WholePolishPage() {
  const { resultId } = useParams();
  const { status, user } = useAuthSession();
  const [text, setText] = useState('');
  const [level, setLevel] = useState<WholePolishLevel>('standard');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<WholePolishResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
  const [loadingResult, setLoadingResult] = useState(false);

  const canSubmit = useMemo(() => Boolean(text.trim()) && !submitting && !readingFile, [readingFile, text, submitting]);

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
      <PageHeader title="论文润色" description="上传论文或粘贴全文，选择润色强度后生成可追溯结果。" />
      <ModuleTabs
        ariaLabel="论文润色功能导航"
        items={[
          { label: '全文润色', to: '/whole-polish', active: true },
          { label: '局部润色', to: '/local-polish', active: false },
          { label: '润色记录', to: '/polish-history', active: false },
        ]}
      />

      <form
        className="mx-auto max-w-6xl rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
        onSubmit={handleSubmit}
      >
        <div className="mb-5 border-b border-slate-100 pb-5">
          <h2 className="text-lg font-bold text-slate-900">发起整篇润色</h2>
          <p className="mt-1 text-sm text-slate-500">提交后生成可追溯的润色结果与变更明细。</p>
        </div>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(300px,.65fr)]">
          <div>
            <p className="text-sm font-bold text-slate-800">论文内容</p>
            <label className="mt-3 flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 p-5 text-center transition hover:border-brand-400 hover:bg-brand-50/40">
              <span className="text-sm font-bold text-slate-900">
                {selectedFile ? selectedFile.name : '选择论文文件'}
              </span>
              <span className="mt-1 text-xs text-slate-500">支持文本文件与可搜索文本 PDF，最大 50 MB</span>
              <input className="sr-only" type="file" accept={THESIS_FILE_ACCEPT} onChange={handleFileChange} />
            </label>
            <label className="mt-4 block text-sm font-bold text-slate-800" htmlFor="whole-polish-textarea">
              或直接粘贴全文
              <textarea
                id="whole-polish-textarea"
                className="mt-2 min-h-56 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm leading-7 font-normal outline-none focus:border-brand-500"
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="粘贴需要全文润色的文本。"
              />
            </label>
          </div>

          <aside className="flex flex-col rounded-xl border border-slate-200 bg-slate-50 p-5">
            <div>
              <p className="text-sm font-bold text-slate-900">润色方案</p>
              <div className="mt-3 space-y-2">
                {LEVEL_OPTIONS.map((option) => {
                  const selected = option.level === level;
                  return (
                    <button
                      key={option.level}
                      type="button"
                      className={`w-full rounded-lg border p-3 text-left transition ${selected ? 'border-brand-500 bg-brand-50' : 'border-slate-200 bg-white hover:border-slate-300'}`}
                      onClick={() => setLevel(option.level)}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-slate-900">
                        <span
                          className={`size-3 rounded-full border-2 ${selected ? 'border-brand-500 bg-brand-500' : 'border-slate-300 bg-white'}`}
                        />
                        {option.title}
                        {option.recommended ? <span className="ml-auto text-xs text-brand-700">推荐</span> : null}
                      </span>
                      <span className="mt-1 block text-xs leading-5 text-slate-500">{option.summary}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            <Button className="mt-6 w-full" size="lg" type="submit" disabled={!canSubmit}>
              {readingFile ? '正在解析文件…' : submitting ? '正在润色…' : '开始润色'}
            </Button>
          </aside>
        </div>
        {errorMessage ? <p className="mt-4 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
      </form>

      {loadingResult ? <LoadingState label="正在加载润色结果…" /> : null}

      {result ? (
        <section className="mx-auto max-w-6xl px-6 pb-12">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">润色结果</h2>
                <p className="mt-1 text-sm text-slate-500">本次润色已完成，以下内容可继续查看或下载。</p>
              </div>
              <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700">
                已完成
              </span>
            </div>
            <div className="mt-5 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <span className="text-xs text-slate-500">结果编号</span>
                <strong data-testid="whole-polish-result-id" className="mt-1 block truncate text-slate-900">
                  {result.id}
                </strong>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <span className="text-xs text-slate-500">来源</span>
                <strong className="mt-1 block truncate text-slate-900">{result.source_filename || '粘贴文本'}</strong>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <span className="text-xs text-slate-500">润色档位</span>
                <strong className="mt-1 block text-slate-900">
                  {result.level === 'standard' ? '标准优化' : result.level === 'enhanced' ? '增强优化' : '基础校准'}
                </strong>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <span className="text-xs text-slate-500">变更数量</span>
                <strong className="mt-1 block text-slate-900">{result.changes.length}</strong>
              </div>
            </div>
            <p className="mt-4 text-xs text-slate-500">完成时间：{result.created_at}</p>
            <div className="mt-5 rounded-xl border border-slate-200 p-5">
              <h3 className="text-base font-bold text-slate-900">润色后的文本</h3>
              <p className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm leading-7 text-slate-800">
                {result.polished_text}
              </p>
            </div>
            <div className="mt-5 rounded-xl border border-slate-200 p-5">
              <h3 className="text-base font-bold text-slate-900">变更明细</h3>
              <ul className="mt-3 space-y-3" aria-label="变更列表">
                {result.changes.map((change, index) => (
                  <li
                    key={`${change.position}-${index}`}
                    className="rounded-lg border border-slate-200 p-4 text-sm leading-6"
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
            <div className="mt-5 flex flex-wrap gap-3">
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
