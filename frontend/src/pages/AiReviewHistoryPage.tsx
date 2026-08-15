import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchAiReviewHistory, type AiReviewHistoryRecord } from '../api/normativeRules';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  Card,
  DataTable,
  DataTableCell,
  DataTableHead,
  DataTableRow,
  EmptyState,
  ErrorState,
  LinkButton,
  LoadingState,
  ModuleTabs,
  PageHeader,
} from '../components/ui';

function formatTimestamp(value: string) {
  return value ? value.replace('T', ' ').replace('Z', '') : '—';
}

function AiReviewHistoryPage() {
  const { status, user } = useAuthSession();
  const [records, setRecords] = useState<AiReviewHistoryRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const totalCount = useMemo(() => records.length, [records]);

  useEffect(() => {
    if (status !== 'authenticated' || !user) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    fetchAiReviewHistory()
      .then((nextRecords) => {
        if (!cancelled) {
          setRecords(nextRecords);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '辅助评阅历史加载失败');
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

  if (status === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-3xl font-black text-[#1F3F66]">AI 智能评阅</h1>
          <p className="mt-4 text-slate-600">请先登录后查看本人辅助评阅历史记录。</p>
          <LinkButton className="mt-6" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  return (
    <div className="font-['Microsoft_YaHei','PingFang_SC','Noto_Sans_SC',Arial,sans-serif] text-[#1F2D3D]">
      <PageHeader title="AI 智能评阅" />
      <ModuleTabs
        ariaLabel="AI 智能评阅功能导航"
        items={[
          { label: '发起评阅', to: '/ai-review', active: false },
          { label: '评阅记录', to: '/ai-review/history', active: true, count: totalCount },
        ]}
      />

      <section className="px-8 py-7">
        <div className="flex items-end justify-between">
          <h2 className="text-[30px] font-black text-[#1F3F66]">智能评阅记录</h2>
          <p className="text-sm font-semibold text-[#8A8A8A]">共 {totalCount} 条记录</p>
        </div>

        <div className="mt-6 flex h-[85px] items-center gap-5 bg-[#F1F4F8] px-6">
          <input
            className="h-11 w-72 border border-[#D6DCE5] bg-white px-4 outline-none focus:border-[#3A86F4]"
            placeholder="请输入文档名称搜索"
            readOnly
          />
          <select
            className="h-11 border border-[#D6DCE5] bg-white px-4 outline-none focus:border-[#3A86F4]"
            defaultValue="all"
            disabled
          >
            <option value="all">全部结果</option>
          </select>
          <button className="h-11 bg-[#3A86F4] px-7 font-black text-white" type="button" disabled>
            查询
          </button>
          <button
            className="h-11 border border-[#D6DCE5] bg-white px-7 font-black text-slate-600"
            type="button"
            disabled
          >
            重置
          </button>
        </div>

        {loading ? <LoadingState label="正在加载评阅记录…" /> : null}
        {errorMessage ? <ErrorState message={errorMessage} /> : null}
        {!loading && !errorMessage && records.length === 0 ? (
          <EmptyState title="暂无辅助评阅历史记录。" description="完成一次 AI 智能评阅后，记录会展示在这里。" />
        ) : null}

        {records.length > 0 ? (
          <DataTable className="mt-6" aria-label="辅助评阅历史记录">
            <thead>
              <DataTableRow className="hover:bg-transparent">
                <DataTableHead className="text-center">序号</DataTableHead>
                <DataTableHead>论文题目</DataTableHead>
                <DataTableHead>模板</DataTableHead>
                <DataTableHead className="text-center">总分</DataTableHead>
                <DataTableHead>结论</DataTableHead>
                <DataTableHead>时间</DataTableHead>
                <DataTableHead className="text-center">操作</DataTableHead>
              </DataTableRow>
            </thead>
            <tbody>
              {records.map((record, index) => (
                <DataTableRow key={record.id}>
                  <DataTableCell className="text-center">{index + 1}</DataTableCell>
                  <DataTableCell className="max-w-sm truncate font-semibold text-slate-900">
                    {record.thesis_title}
                  </DataTableCell>
                  <DataTableCell>{record.template_id}</DataTableCell>
                  <DataTableCell className="bg-brand-50 text-center text-base font-bold text-brand-600">
                    {record.total_score}
                  </DataTableCell>
                  <DataTableCell className="font-semibold">{record.result_label}</DataTableCell>
                  <DataTableCell className="tabular-nums">{formatTimestamp(record.created_at)}</DataTableCell>
                  <DataTableCell className="text-center">
                    <Link
                      className="font-semibold text-brand-600 hover:text-brand-700"
                      to={`/ai-review/results/${record.id}`}
                    >
                      查看结果
                    </Link>
                  </DataTableCell>
                </DataTableRow>
              ))}
            </tbody>
          </DataTable>
        ) : null}
      </section>
    </div>
  );
}

export default AiReviewHistoryPage;
