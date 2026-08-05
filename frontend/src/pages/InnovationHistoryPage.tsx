import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  downloadInnovationReportJson,
  fetchInnovationHistory,
  type InnovationHistoryRecord,
} from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';

const PAGE_SIZE = 8;

function formatTimestamp(value: string) {
  return value ? value.replace('T', ' ').replace('Z', '') : '—';
}

function formatScore(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function degreeLabel(value: InnovationHistoryRecord['degree_type']) {
  return value === 'doctoral' ? '博士' : '硕士';
}

function InnovationHistoryPage() {
  const { status, user } = useAuthSession();
  const [records, setRecords] = useState<InnovationHistoryRecord[]>([]);
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (status !== 'authenticated' || !user) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);

    fetchInnovationHistory()
      .then((nextRecords) => {
        if (!cancelled) {
          setRecords(nextRecords);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '创新性评估历史加载失败');
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
  }, [status, user]);

  const filteredRecords = useMemo(() => {
    const normalized = submittedQuery.trim().toLowerCase();
    if (!normalized) {
      return records;
    }
    return records.filter((record) => record.thesis_title.toLowerCase().includes(normalized));
  }, [records, submittedQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredRecords.length / PAGE_SIZE));
  const visibleRecords = filteredRecords.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function handleSearch() {
    setSubmittedQuery(query);
    setPage(1);
  }

  async function handleDownloadJson(recordId: string) {
    const blob = await downloadInnovationReportJson(recordId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `innovation-report-${recordId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (status === 'loading') {
    return <main className="min-h-screen bg-[#F5F7FA] px-7 py-12 text-sm font-semibold text-slate-500">正在加载登录状态…</main>;
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#F5F7FA] px-7 py-12 font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif]">
        <section className="mx-auto max-w-4xl rounded-xl border border-[#E5E7EB] bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-black text-[#1F3F63]">创新性分析历史记录</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后查看本人创新性评估历史。</p>
          <Link className="mt-5 inline-flex h-11 items-center rounded bg-[#2F80ED] px-4 font-semibold text-white" to="/auth">
            前往登录
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F5F7FA] font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif] text-[#1F2D3D]">
      <header className="flex h-11 items-center bg-[#1F3F63] px-3">
        <h1 className="text-[23px] font-black tracking-wide text-white">创新性分析历史记录</h1>
      </header>

      <section className="bg-white px-7 py-5">
        <div className="flex min-h-12 flex-wrap items-center justify-between gap-4">
          <p className="text-[16px] font-semibold text-slate-700">共 {filteredRecords.length} 条记录</p>
          <div className="flex items-center gap-2">
            <input
              className="h-10 w-72 rounded border border-[#D6D9DD] bg-white px-3 text-[15px] outline-none focus:border-[#2F80ED]"
              placeholder="请输入论文题目搜索"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  handleSearch();
                }
              }}
            />
            <button className="h-10 rounded bg-[#2F80ED] px-6 text-[15px] font-bold text-white" type="button" onClick={handleSearch}>
              搜索
            </button>
          </div>
        </div>
      </section>

      {loading ? <p className="px-7 py-6 text-sm font-semibold text-slate-500">正在加载历史记录…</p> : null}
      {errorMessage ? <p className="px-7 py-6 text-sm font-semibold text-red-600">{errorMessage}</p> : null}
      {!loading && !errorMessage && filteredRecords.length === 0 ? (
        <p className="mx-7 mt-6 rounded-xl border border-dashed border-[#E5E7EB] bg-white p-6 text-sm text-slate-600">暂无创新性评估历史记录。</p>
      ) : null}

      {filteredRecords.length > 0 ? (
        <section className="overflow-x-auto bg-white">
          <table className="min-w-full table-fixed text-center text-[15px]">
            <thead className="bg-[#1F3F63] text-[16px] font-bold text-white">
              <tr>
                <th className="w-[34%] px-6 py-4 text-left">论文题目</th>
                <th className="w-[13%] px-6 py-4">学历层次</th>
                <th className="w-[13%] px-6 py-4">综合分</th>
                <th className="w-[12%] px-6 py-4">等级</th>
                <th className="w-[18%] px-6 py-4">生成时间</th>
                <th className="w-[10%] px-6 py-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleRecords.map((record, index) => (
                <tr key={record.id} className={`h-[58px] border-b border-[#E5E7EB] ${index % 2 === 0 ? 'bg-white' : 'bg-[#F8FAFC]'}`}>
                  <td className="truncate px-6 py-4 text-left font-bold text-slate-900" title={record.thesis_title}>{record.thesis_title}</td>
                  <td className="px-6 py-4 font-semibold text-slate-700">{degreeLabel(record.degree_type)}</td>
                  <td className="px-6 py-4 font-black text-[#1F3F63]">{formatScore(record.total_score)}</td>
                  <td className="px-6 py-4 font-black text-[#22B14C]">{record.grade_label}</td>
                  <td className="px-6 py-4 text-slate-700">{formatTimestamp(record.created_at)}</td>
                  <td className="px-6 py-4">
                    <div className="flex flex-nowrap justify-center gap-2">
                      <Link className="inline-flex h-8 items-center rounded border border-[#2F80ED] px-3 text-sm font-bold text-[#2F80ED]" to={`/innovation-assessments/${record.id}`}>报告预览</Link>
                      <button className="h-8 rounded border border-[#22B14C] px-3 text-sm font-bold text-[#22B14C]" type="button" onClick={() => handleDownloadJson(record.id)}>报告下载</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex h-[70px] items-center justify-center gap-4 bg-white text-[15px]">
            <span className="font-semibold text-slate-700">第 {page} / {totalPages} 页</span>
            <button
              className="h-9 rounded border border-[#CFD3D8] px-5 font-semibold text-slate-600 disabled:text-[#CFD3D8]"
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              上一页
            </button>
            <button
              className="h-9 rounded bg-[#2F80ED] px-5 font-semibold text-white disabled:bg-[#CFD3D8]"
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            >
              下一页
            </button>
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default InnovationHistoryPage;
