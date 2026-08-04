import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  downloadPolishResultText,
  fetchPolishHistory,
  fetchPolishHistoryRecord,
  type PolishHistoryRecord,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';

const LEVEL_LABELS: Record<PolishHistoryRecord['level'], string> = {
  basic: 'AI 校准',
  standard: 'AI 提质',
  enhanced: 'AI 重构',
};

function getLevelClass(level: PolishHistoryRecord['level']) {
  if (level === 'enhanced') {
    return 'text-[#F04438]';
  }
  if (level === 'standard') {
    return 'text-[#2F7BFF]';
  }
  return 'text-[#F28A18]';
}

function getModeLabel(record: PolishHistoryRecord) {
  return record.polish_type === 'whole' ? '全文润色' : '局部润色';
}

function createFileName(record: PolishHistoryRecord) {
  return `${record.document_name || 'polish-result'}-${record.id}.txt`;
}

function PolishHistoryPage() {
  const { polishType, resultId } = useParams();
  const { status, user } = useAuthSession();
  const [records, setRecords] = useState<PolishHistoryRecord[]>([]);
  const [record, setRecord] = useState<PolishHistoryRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isDetail = polishType === 'whole' || polishType === 'local' ? Boolean(resultId) : false;
  const totalCount = useMemo(() => records.length, [records]);

  useEffect(() => {
    if (status !== 'authenticated' || !user) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);

    const request = isDetail && resultId
      ? fetchPolishHistoryRecord(polishType as PolishHistoryRecord['polish_type'], resultId)
      : fetchPolishHistory();

    request
      .then((response) => {
        if (cancelled) {
          return;
        }
        if (Array.isArray(response)) {
          setRecords(response);
          setRecord(null);
        } else {
          setRecord(response);
          setRecords([]);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '润色记录加载失败');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isDetail, polishType, resultId, status, user]);

  async function handleDownload(target: PolishHistoryRecord) {
    const blob = await downloadPolishResultText(target.polish_type, target.id);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = createFileName(target);
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (status === 'loading') {
    return <main className="px-8 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-[#1F3D62]">润色记录</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后查看本人全文与局部润色记录。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-[#2F7BFF] px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  if (isDetail) {
    return (
      <main className="min-h-screen bg-[#F6F7F9] text-slate-900">
        <header className="flex min-h-[90px] items-center justify-between bg-[#1F3D62] px-8 text-white">
          <div>
            <Link className="text-base font-semibold text-blue-100 hover:underline" to="/polish-history">返回润色记录</Link>
            <h1 className="mt-2 text-[32px] font-black">差异查看</h1>
          </div>
          {record ? <span className="text-lg font-semibold text-blue-100">{getModeLabel(record)}</span> : null}
        </header>

        <section className="px-8 py-8">
          {loading ? <p className="font-semibold text-slate-500">正在加载润色差异…</p> : null}
          {errorMessage ? <p className="font-semibold text-red-600">{errorMessage}</p> : null}
          {record ? (
            <article className="grid gap-5 lg:grid-cols-2">
              <div className="border border-[#DADDE1] bg-white">
                <h2 className="border-b border-[#DADDE1] px-6 py-4 text-xl font-black">原文</h2>
                <p className="min-h-[420px] whitespace-pre-wrap px-6 py-5 text-lg leading-8">{record.original_text}</p>
              </div>
              <div className="border border-[#DADDE1] bg-white">
                <div className="flex items-center justify-between border-b border-[#DADDE1] px-6 py-4">
                  <h2 className="text-xl font-black">润色结果</h2>
                  <button className="font-bold text-[#2F7BFF] hover:underline" type="button" onClick={() => handleDownload(record)}>
                    下载 .txt
                  </button>
                </div>
                <p className="min-h-[420px] whitespace-pre-wrap px-6 py-5 text-lg leading-8">{record.polished_text}</p>
              </div>
            </article>
          ) : null}
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-white text-slate-900">
      <header className="flex min-h-[90px] items-center justify-between bg-[#1F3D62] px-8 text-white">
        <h1 className="text-[32px] font-black">润色记录</h1>
        <span className="text-xl font-semibold text-blue-100">共 {totalCount} 条记录</span>
      </header>

      <section className="overflow-x-auto">
        <table className="min-w-[1120px] w-full border-collapse text-center text-[20px]">
          <thead className="bg-[#1F3D62] text-[22px] font-black text-white">
            <tr className="border-t border-blue-100/40">
              <th className="w-24 px-6 py-7">序号</th>
              <th className="min-w-80 px-6 py-7 text-left">文档名称</th>
              <th className="w-40 px-6 py-7">润色模式</th>
              <th className="w-40 px-6 py-7">润色等级</th>
              <th className="w-64 px-6 py-7">报告生成时间</th>
              <th className="w-72 px-6 py-7">操作</th>
            </tr>
          </thead>
          <tbody>
            {records.map((item, index) => (
              <tr key={`${item.polish_type}-${item.id}`} className={`border-b border-[#DADDE1] ${index % 2 === 0 ? 'bg-white' : 'bg-[#F6F7F9]'}`}>
                <td className="border-r border-[#DADDE1] px-6 py-9 font-medium">{index + 1}</td>
                <td className="border-r border-[#DADDE1] px-6 py-9 text-left font-semibold">{item.document_name}</td>
                <td className="border-r border-[#DADDE1] px-6 py-9">{getModeLabel(item)}</td>
                <td className={`border-r border-[#DADDE1] px-6 py-9 font-black ${getLevelClass(item.level)}`}>{LEVEL_LABELS[item.level]}</td>
                <td className="border-r border-[#DADDE1] px-6 py-9 text-lg">{item.created_at}</td>
                <td className="px-6 py-9">
                  <div className="flex flex-nowrap justify-center gap-5 text-lg font-bold text-[#2F7BFF]">
                    <Link className="hover:underline focus:outline-none focus:ring-2 focus:ring-[#2F7BFF]" to={`/polish-history/${item.polish_type}/${item.id}`}>查看差异</Link>
                    <button className="hover:underline focus:outline-none focus:ring-2 focus:ring-[#2F7BFF]" type="button" onClick={() => handleDownload(item)}>下载结果</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {loading ? <p className="px-8 py-6 text-sm font-semibold text-slate-500">正在加载润色记录…</p> : null}
      {errorMessage ? <p className="px-8 py-6 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
      {!loading && !errorMessage && records.length === 0 ? <p className="mx-8 mt-6 border border-dashed border-[#DADDE1] bg-[#F6F7F9] p-6 text-base text-slate-600">暂无润色记录。</p> : null}
    </main>
  );
}

export default PolishHistoryPage;
