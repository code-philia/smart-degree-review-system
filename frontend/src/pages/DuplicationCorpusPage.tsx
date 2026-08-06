import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createDuplicationCorpusSample,
  deleteDuplicationCorpusSample,
  fetchDuplicationCorpusSamples,
  type DuplicationCorpusSample,
} from '../api/duplicationCorpus';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { Button, Card, EmptyState, ErrorState, LoadingState, LinkButton, PageHeader } from '../components/ui';
import { extractThesisFileText, THESIS_FILE_ACCEPT } from '../utils/thesisFileText';

function DuplicationCorpusPage() {
  const { status, user } = useAuthSession();
  const [samples, setSamples] = useState<DuplicationCorpusSample[]>([]);
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [content, setContent] = useState('');
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  function loadSamples() {
    if (status !== 'authenticated' || user?.role !== 'SCHOOL_ADMIN') {
      return () => {};
    }

    let active = true;
    setLoading(true);
    setListError(null);
    fetchDuplicationCorpusSamples()
      .then((records) => {
        if (active) {
          setSamples(records);
        }
      })
      .catch((error) => {
        if (active) {
          setListError(error instanceof Error ? error.message : '样本库加载失败');
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }

  useEffect(() => {
    return loadSamples();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, user?.role]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    setErrorMessage(null);
    setSelectedFileName(null);

    if (!file) {
      return;
    }

    setReadingFile(true);
    try {
      const result = await extractThesisFileText(file);
      setContent(result.text);
      setSelectedFileName(file.name);
    } catch (error) {
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
      const sample = await createDuplicationCorpusSample({
        title,
        subject,
        year: Number(year),
        content,
        source_type: selectedFileName ? 'file' : 'paste',
        source_filename: selectedFileName,
      });
      setSamples((current) => [sample, ...current]);
      setTitle('');
      setSubject('');
      setContent('');
      setSelectedFileName(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '样本保存失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(sampleId: string) {
    setErrorMessage(null);
    try {
      await deleteDuplicationCorpusSample(sampleId);
      setSamples((current) => current.filter((sample) => sample.id !== sampleId));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '样本删除失败');
    }
  }

  if (status === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">本地比对样本库</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录学校管理人员账号后管理比对样本。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  if (user.role !== 'SCHOOL_ADMIN') {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">无权访问本地比对样本库</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">该功能仅开放给学校管理人员，其他角色无法访问。</p>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="本地比对样本库"
        breadcrumbs={[{ label: '首页', to: '/' }, { label: '管理配置' }, { label: '比对样本库' }]}
        description="维护相似度检测所依据的试点样本库。样本仅用于试点相似度检测比对，不表示已接入真实校内论文库。"
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Card title="新增样本">
          <form onSubmit={handleSubmit}>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="block text-sm font-semibold text-slate-700">
                标题
                <input
                  className="mt-2 h-11 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-brand-500"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label className="block text-sm font-semibold text-slate-700">
                学科
                <input
                  className="mt-2 h-11 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-brand-500"
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                />
              </label>
              <label className="block text-sm font-semibold text-slate-700">
                年份
                <input
                  className="mt-2 h-11 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-brand-500"
                  value={year}
                  onChange={(event) => setYear(event.target.value)}
                  inputMode="numeric"
                />
              </label>
            </div>

            <label className="mt-5 block text-sm font-semibold text-slate-700">
              样本文本
              <textarea
                className="mt-2 min-h-[260px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm leading-7 outline-none focus:border-brand-500"
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="粘贴非空 UTF-8 文本，或上传 .txt/.md/可搜索文本 PDF 后自动填充。"
              />
            </label>

            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="inline-flex h-11 cursor-pointer items-center justify-center rounded-xl border border-brand-100 bg-brand-50 px-4 text-sm font-semibold text-brand-700">
                上传 .txt / .md / PDF
                <input className="sr-only" type="file" accept={THESIS_FILE_ACCEPT} onChange={handleFileChange} />
              </label>
              {selectedFileName ? (
                <span className="text-sm font-semibold text-brand-700">已选择：{selectedFileName}</span>
              ) : null}
              <Button type="submit" disabled={submitting || readingFile}>
                {readingFile ? '解析中…' : submitting ? '保存中…' : '保存样本'}
              </Button>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              文本文件最大 5 MB；可搜索文本 PDF 最大 50 MB，提取文本最大 5 MB
            </p>
            {errorMessage ? <p className="mt-4 text-sm font-semibold text-danger-600">{errorMessage}</p> : null}
          </form>
        </Card>

        <Card title="样本列表">
          {loading ? <LoadingState compact label="正在加载样本…" /> : null}
          {!loading && listError && samples.length === 0 ? (
            <ErrorState message={listError} onRetry={() => loadSamples()} />
          ) : null}
          {!loading && !listError && samples.length === 0 ? (
            <EmptyState title="暂无样本" description="新增样本后将出现在这里，供相似度检测比对使用。" />
          ) : null}
          <div className="mt-4 space-y-3">
            {samples.map((sample) => (
              <article key={sample.id} className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">{sample.title}</h3>
                <p className="mt-1 text-xs text-slate-500">
                  {sample.subject} · {sample.year} ·{' '}
                  {sample.source_type === 'file' ? sample.source_filename : '粘贴文本'}
                </p>
                <button
                  className="mt-3 text-sm font-semibold text-danger-600"
                  type="button"
                  onClick={() => handleDelete(sample.id)}
                >
                  删除样本
                </button>
              </article>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

export default DuplicationCorpusPage;
