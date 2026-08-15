import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  downloadPolishResultText,
  fetchPolishHistory,
  fetchPolishHistoryRecord,
  type PolishHistoryRecord,
} from '../api/normativeRules';
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

const LEVEL_LABELS: Record<PolishHistoryRecord['level'], string> = {
  basic: 'AI 校准',
  standard: 'AI 提质',
  enhanced: 'AI 重构',
};

function getLevelClass(level: PolishHistoryRecord['level']) {
  if (level === 'enhanced') {
    return 'bg-danger-50 text-danger-700';
  }
  if (level === 'standard') {
    return 'bg-brand-50 text-brand-700';
  }
  return 'bg-warning-50 text-warning-700';
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

    const request =
      isDetail && resultId
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
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-[#1F3D62]">润色记录</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后查看本人全文与局部润色记录。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  if (isDetail) {
    return (
      <div className="text-slate-900">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <Link className="text-base font-semibold text-brand-600 hover:underline" to="/polish-history">
              返回润色记录
            </Link>
            <h1 className="mt-2 text-[28px] font-black text-[#1F3D62]">差异查看</h1>
          </div>
          {record ? <span className="text-lg font-semibold text-slate-500">{getModeLabel(record)}</span> : null}
        </div>

        <section>
          {loading ? <LoadingState label="正在加载润色差异…" /> : null}
          {errorMessage ? <ErrorState message={errorMessage} /> : null}
          {record ? (
            <article className="grid gap-5 lg:grid-cols-2">
              <div className="border border-[#DADDE1] bg-white">
                <h2 className="border-b border-[#DADDE1] px-6 py-4 text-xl font-black">原文</h2>
                <p className="min-h-[420px] whitespace-pre-wrap px-6 py-5 text-lg leading-8">{record.original_text}</p>
              </div>
              <div className="border border-[#DADDE1] bg-white">
                <div className="flex items-center justify-between border-b border-[#DADDE1] px-6 py-4">
                  <h2 className="text-xl font-black">润色结果</h2>
                  <button
                    className="font-bold text-[#2F7BFF] hover:underline"
                    type="button"
                    onClick={() => handleDownload(record)}
                  >
                    下载 .txt
                  </button>
                </div>
                <p className="min-h-[420px] whitespace-pre-wrap px-6 py-5 text-lg leading-8">{record.polished_text}</p>
              </div>
            </article>
          ) : null}
        </section>
      </div>
    );
  }

  return (
    <div className="text-slate-900">
      <PageHeader title="论文润色" description="查看本人整篇与局部润色的历史结果。" />
      <ModuleTabs
        ariaLabel="论文润色功能导航"
        items={[
          { label: '整篇润色', to: '/whole-polish', active: false },
          { label: '局部润色', to: '/local-polish', active: false },
          { label: '润色记录', to: '/polish-history', active: true, count: totalCount },
        ]}
      />

      {loading ? <LoadingState label="正在加载润色记录…" /> : null}
      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {!loading && !errorMessage && records.length === 0 ? (
        <EmptyState title="暂无润色记录" description="完成一次全文或局部润色后，记录会展示在这里。" />
      ) : null}
      {!loading && !errorMessage && records.length > 0 ? (
        <section aria-labelledby="polish-history-heading">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
            <h2 id="polish-history-heading" className="text-lg font-semibold text-foreground">
              润色记录
            </h2>
            <p className="text-sm text-muted-foreground">共 {totalCount} 条记录</p>
          </div>
          <DataTable tableClassName="min-w-[920px]" aria-label="论文润色历史记录">
            <thead>
              <DataTableRow className="hover:bg-transparent">
                <DataTableHead className="w-16 text-center">序号</DataTableHead>
                <DataTableHead className="min-w-72">文档名称</DataTableHead>
                <DataTableHead className="w-28 text-center">润色模式</DataTableHead>
                <DataTableHead className="w-28 text-center">润色等级</DataTableHead>
                <DataTableHead className="w-44 text-center">报告生成时间</DataTableHead>
                <DataTableHead className="w-44 text-center">操作</DataTableHead>
              </DataTableRow>
            </thead>
            <tbody>
              {records.map((item, index) => (
                <DataTableRow
                  key={`${item.polish_type}-${item.id}`}
                  className={index % 2 === 0 ? '' : 'bg-slate-50/60'}
                >
                  <DataTableCell className="text-center tabular-nums text-slate-500">{index + 1}</DataTableCell>
                  <DataTableCell className="max-w-md font-semibold text-slate-900">
                    <span className="block truncate" title={item.document_name}>
                      {item.document_name}
                    </span>
                  </DataTableCell>
                  <DataTableCell className="text-center font-medium">{getModeLabel(item)}</DataTableCell>
                  <DataTableCell className="text-center">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${getLevelClass(item.level)}`}
                    >
                      {LEVEL_LABELS[item.level]}
                    </span>
                  </DataTableCell>
                  <DataTableCell className="text-center tabular-nums text-slate-600">{item.created_at}</DataTableCell>
                  <DataTableCell>
                    <div className="flex flex-nowrap justify-center gap-3">
                      <Link
                        className="font-semibold text-brand-600 hover:text-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
                        to={`/polish-history/${item.polish_type}/${item.id}`}
                      >
                        查看差异
                      </Link>
                      <button
                        className="font-semibold text-brand-600 hover:text-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
                        type="button"
                        onClick={() => handleDownload(item)}
                      >
                        下载结果
                      </button>
                    </div>
                  </DataTableCell>
                </DataTableRow>
              ))}
            </tbody>
          </DataTable>
        </section>
      ) : null}
    </div>
  );
}

export default PolishHistoryPage;
