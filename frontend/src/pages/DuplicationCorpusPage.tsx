import { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  createDuplicationCorpusSample,
  deleteDuplicationCorpusSample,
  fetchDuplicationCorpusSamples,
  type DuplicationCorpusSample,
} from '../api/duplicationCorpus';
import { useAuthSession } from '../auth/AuthSessionProvider';

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const ACCEPTED_FILE_EXTENSIONS = ['.txt', '.md'];

function getFileExtension(fileName: string) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

function readTextFile(file: File): Promise<string> {
  if (typeof file.text === 'function') {
    return file.text();
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '');
    reader.onerror = () => reject(reader.error || new Error('file-read-failed'));
    reader.readAsText(file, 'utf-8');
  });
}

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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (status !== 'authenticated' || user?.role !== 'SCHOOL_ADMIN') {
      return;
    }

    let active = true;
    setLoading(true);
    setErrorMessage(null);
    fetchDuplicationCorpusSamples()
      .then((records) => {
        if (active) {
          setSamples(records);
        }
      })
      .catch((error) => {
        if (active) {
          setErrorMessage(error instanceof Error ? error.message : '样本库加载失败');
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
  }, [status, user?.role]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    setErrorMessage(null);
    setSelectedFileName(null);

    if (!file) {
      return;
    }
    if (!ACCEPTED_FILE_EXTENSIONS.includes(getFileExtension(file.name))) {
      setErrorMessage('仅支持上传 .txt 或 .md 文件');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setErrorMessage('文件大小不能超过 5 MB');
      return;
    }

    try {
      setContent(await readTextFile(file));
      setSelectedFileName(file.name);
    } catch {
      setErrorMessage('文件读取失败，请确认文件为 UTF-8 文本');
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
    return <main className="px-6 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">本地比对样本库</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录学校管理人员账号后管理本地原型比对样本。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-blue-600 px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  if (user.role !== 'SCHOOL_ADMIN') {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-red-200 bg-red-50 p-6">
          <h1 className="text-2xl font-black text-red-900">无权访问本地比对样本库</h1>
          <p className="mt-3 text-sm leading-6 text-red-700">该功能仅开放给学校管理人员，后端接口同样会拒绝其他角色。</p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F5FAFF] px-6 py-10">
      <section className="mx-auto max-w-6xl">
        <div className="rounded-3xl border border-blue-100 bg-white p-6 shadow-sm">
          <p className="text-sm font-semibold text-blue-600">SQLite 本地原型数据</p>
          <h1 className="mt-2 text-3xl font-black text-slate-950">本地比对样本库</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            样本仅用于本地原型相似度检测，不表示已接入真实校内论文库。
          </p>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <form className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm" onSubmit={handleSubmit}>
            <h2 className="text-lg font-black text-slate-900">新增样本</h2>
            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              <label className="block text-sm font-semibold text-slate-700">
                标题
                <input className="mt-2 h-11 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500" value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label className="block text-sm font-semibold text-slate-700">
                学科
                <input className="mt-2 h-11 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500" value={subject} onChange={(event) => setSubject(event.target.value)} />
              </label>
              <label className="block text-sm font-semibold text-slate-700">
                年份
                <input className="mt-2 h-11 w-full rounded-xl border border-slate-300 px-3 outline-none focus:border-blue-500" value={year} onChange={(event) => setYear(event.target.value)} inputMode="numeric" />
              </label>
            </div>

            <label className="mt-5 block text-sm font-semibold text-slate-700">
              样本文本
              <textarea className="mt-2 min-h-[260px] w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm leading-7 outline-none focus:border-blue-500" value={content} onChange={(event) => setContent(event.target.value)} placeholder="粘贴非空 UTF-8 文本，或上传 .txt/.md 文件后自动填充。" />
            </label>

            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="inline-flex h-11 cursor-pointer items-center justify-center rounded-xl border border-blue-200 bg-blue-50 px-4 text-sm font-semibold text-blue-700">
                上传 .txt / .md
                <input className="sr-only" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={handleFileChange} />
              </label>
              {selectedFileName ? <span className="text-sm font-semibold text-blue-700">已选择：{selectedFileName}</span> : null}
              <button className="inline-flex h-11 items-center justify-center rounded-xl bg-blue-600 px-5 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300" type="submit" disabled={submitting}>
                {submitting ? '保存中…' : '保存样本'}
              </button>
            </div>
            {errorMessage ? <p className="mt-4 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
          </form>

          <aside className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-black text-slate-900">样本列表</h2>
            {loading ? <p className="mt-4 text-sm text-slate-500">正在加载样本…</p> : null}
            {!loading && samples.length === 0 ? <p className="mt-4 text-sm leading-6 text-slate-500">暂无样本。新增后将从后端 SQLite 读取展示。</p> : null}
            <div className="mt-4 space-y-3">
              {samples.map((sample) => (
                <article key={sample.id} className="rounded-2xl border border-slate-200 p-4">
                  <h3 className="font-bold text-slate-900">{sample.title}</h3>
                  <p className="mt-1 text-xs text-slate-500">{sample.subject} · {sample.year} · {sample.source_type === 'file' ? sample.source_filename : '粘贴文本'}</p>
                  <button className="mt-3 text-sm font-semibold text-red-600" type="button" onClick={() => handleDelete(sample.id)}>
                    删除样本
                  </button>
                </article>
              ))}
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}

export default DuplicationCorpusPage;
