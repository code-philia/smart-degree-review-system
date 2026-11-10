import { preserveText, RichMessage } from "../i18n/jsx-runtime";
import { FileText, LoaderCircle, Trash2 } from 'lucide-react';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../components/shadcn/alert-dialog';
import { REVIEW_ROUTES } from '../nav/reviewRoutes';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { deletePaperLintReport, deletePaperLintReports, fetchPaperLintReports, type PaperLintReportListItem } from '../api/paperLint';
import { formatChinaDateTime } from '../utils/dateTime';
import { THIRTY_RULE_IDS } from '../utils/paperLintRuleGroups';
import { DetectionPageHeader } from '../components/paperLint/DetectionPageHeader';
import { ReportHistoryTable } from '../components/paperLint/ReportHistoryTable';
import {
  downloadNormativeReportJson,
  fetchNormativeDetectionHistory,
  fetchNormativeDetectionReport,
  type DetectionTaskResponse,
  type NormativeIssue,
} from '../api/normativeRules';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LinkButton,
  LoadingState,
  ModuleTabs,
  PageHeader,
} from '../components/ui';

type ActiveIssue = {
  issue: NormativeIssue;
  index: number;
};

function NormativeReportPage({ mode = 'basic' }: { mode?: 'basic' | 'thirty' }) {
  const isThirty = mode === 'thirty';
  const checkPath = isThirty ? REVIEW_ROUTES.upload : '/normative-check';
  const historyPath = isThirty ? REVIEW_ROUTES.history : '/normative-reports';
  const { reportId } = useParams();
  const { status, user } = useAuthSession();
  const userId = user?.id;
  const [history, setHistory] = useState<DetectionTaskResponse[]>([]);
  const [report, setReport] = useState<DetectionTaskResponse | null>(null);
  const [pdfReports, setPdfReports] = useState<PaperLintReportListItem[]>([]);
  const [selectedReportIds, setSelectedReportIds] = useState<string[]>([]);
  const [deleting, setDeleting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<{ ids: string[]; batch: boolean; filename: string } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deletionInFlight = useRef(false);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);
  const historyRootRef = useRef<HTMLDivElement>(null);
  const [activeIssue, setActiveIssue] = useState<ActiveIssue | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const lineRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const lines = useMemo(() => (report?.original_text || '').split('\n'), [report]);

  useEffect(() => {
    if (status !== 'authenticated' || !userId) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setErrorMessage(null);
    setSelectedReportIds([]);
    setPendingDelete(null);
    setDeleteError(null);

    const request = reportId
      ? fetchNormativeDetectionReport(reportId)
      : Promise.all([
          isThirty ? Promise.resolve([] as DetectionTaskResponse[]) : fetchNormativeDetectionHistory(),
          fetchPaperLintReports().catch(() => []),
        ]);
    request
      .then((response) => {
        if (cancelled) {
          return;
        }
        if (Array.isArray(response) && Array.isArray(response[0])) {
          const [legacyHistory, savedPdfReports] = response as [DetectionTaskResponse[], PaperLintReportListItem[]];
          setHistory(legacyHistory);
          setPdfReports(
            isThirty
              ? savedPdfReports.filter((savedReport) =>
                  savedReport.selected_rule_ids.length > 0 &&
                  savedReport.selected_rule_ids.every((ruleId) => THIRTY_RULE_IDS.has(ruleId)),
                )
              : savedPdfReports,
          );
          setReport(null);
        } else if (!Array.isArray(response)) {
          setReport(response);
          setHistory([]);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : '检测报告加载失败');
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
  }, [reportId, status, userId, mode]);

  function handleIssueClick(issue: NormativeIssue, index: number) {
    setActiveIssue({ issue, index });
    lineRefs.current[issue.line]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  async function handleDownloadJson(taskId: string) {
    const blob = await downloadNormativeReportJson(taskId);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `normative-report-${taskId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function requestDeleteReports(ids: string[], batch = false) {
    if (deletionInFlight.current) return;
    const owned = new Set(pdfReports.map(record => record.id));
    const snapshot = [...new Set(ids)].filter(id => owned.has(id));
    if (!snapshot.length) return;
    deleteTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDeleteError(null);
    setPendingDelete({ ids: snapshot, batch, filename: pdfReports.find(record => record.id === snapshot[0])!.source_filename });
  }

  async function confirmDeleteReports() {
    if (!pendingDelete || deletionInFlight.current) return;
    const { ids, batch } = pendingDelete;
    deletionInFlight.current = true;
    setDeleting(true);
    setDeleteError(null);
    try {
      if (batch) await deletePaperLintReports(ids);
      else await deletePaperLintReport(ids[0]);
      setPdfReports(current => current.filter(record => !ids.includes(record.id)));
      setSelectedReportIds(current => current.filter(id => !ids.includes(id)));
      setPendingDelete(null);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : '报告删除失败，请重试');
    } finally {
      deletionInFlight.current = false;
      setDeleting(false);
    }
  }

  if (status === 'loading') {
    return <LoadingState label="正在加载登录状态…" />;
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-4xl">
        <Card>
          <h1 className="text-2xl font-black text-slate-900">历史检测记录</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">请先登录后查看本人检测历史和报告。</p>
          <LinkButton className="mt-5" to="/auth">
            前往登录
          </LinkButton>
        </Card>
      </div>
    );
  }

  if (reportId) {
    return (
      <div>
        <PageHeader
          title="检测报告"
          breadcrumbs={[
            { label: '首页', to: '/' },
            { label: '历史检测记录', to: '/normative-reports' },
            { label: '检测报告' },
          ]}
          actions={
            <>
              <Button type="button" disabled={!report} onClick={() => report && handleDownloadJson(report.id)}>
                下载 UTF-8 JSON
              </Button>
              <Button type="button" variant="secondary" onClick={() => window.print()}>
                浏览器打印
              </Button>
            </>
          }
        />

        {loading ? <LoadingState label="正在加载报告…" /> : null}
        {errorMessage ? <ErrorState message={errorMessage} /> : null}

        {report ? (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
            <section className="max-h-[720px] overflow-auto rounded-2xl border border-[#E1E7EF] bg-white font-mono text-sm leading-7 text-slate-800">
              {lines.map((line, index) => {
                const lineNumber = index + 1;
                const isActive = activeIssue?.issue.line === lineNumber;
                return (
                  <div
                    key={lineNumber}
                    ref={(element) => {
                      lineRefs.current[lineNumber] = element;
                    }}
                    className={`grid grid-cols-[64px_minmax(0,1fr)] border-b border-slate-100 ${isActive ? 'bg-yellow-100' : ''}`}
                  >
                    <span className="select-none bg-slate-50 px-3 text-right text-slate-400">{lineNumber}</span>
                    <span className="whitespace-pre-wrap px-4">{line || ' '}</span>
                  </div>
                );
              })}
            </section>

            <aside className="rounded-2xl border border-[#E1E7EF] bg-white p-5 shadow-sm">
              <h2 className="text-xl font-black text-[#1F3760]">问题列表</h2>
              <div className="mt-4 space-y-3">
                {report.issues.map((issue, index) => (
                  <button
                    key={`${issue.rule_id}-${index}`}
                    aria-label={`${issue.severity} 第 ${issue.line} 行，第 ${issue.column} 列`}
                    className={`w-full rounded-xl border p-4 text-left text-sm ${activeIssue?.index === index ? 'border-[#D62020] bg-red-50' : 'border-slate-200 bg-white'}`}
                    type="button"
                    onClick={() => handleIssueClick(issue, index)}
                  >
                    <span className="font-black text-[#D62020]">{issue.severity}</span>
                    <span className="ml-2 text-slate-500">
                      第 {issue.line} 行，第 {issue.column} 列
                    </span>
                    <p className="mt-2 font-semibold text-slate-900">{issue.message}</p>
                    <p className="mt-1 text-slate-600">{issue.excerpt}</p>
                  </button>
                ))}
              </div>
            </aside>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div ref={historyRootRef} tabIndex={-1} className={isThirty ? 'mx-auto w-full max-w-6xl space-y-5' : undefined}>
      <AlertDialog open={Boolean(pendingDelete)} onOpenChange={open => {
        if (!open && !deletionInFlight.current) { setPendingDelete(null); setDeleteError(null); }
      }}>
        <AlertDialogContent className="report-delete-dialog" aria-busy={deleting}
          onEscapeKeyDown={event => { if (deletionInFlight.current) event.preventDefault(); }}
          onCloseAutoFocus={event => {
            event.preventDefault();
            const trigger = deleteTriggerRef.current;
            if (trigger?.isConnected && !trigger.hasAttribute('disabled')) trigger.focus({ preventScroll: true });
            else historyRootRef.current?.focus({ preventScroll: true });
          }}>
          <AlertDialogHeader className="report-delete-header">
            <span className="report-delete-icon" aria-hidden="true"><Trash2 size={21} /></span>
            <AlertDialogTitle>{pendingDelete && pendingDelete.ids.length > 1 ? '删除选中的报告？' : '删除报告？'}</AlertDialogTitle>
          </AlertDialogHeader>
          <div className="report-delete-body">
            <AlertDialogDescription>{pendingDelete && pendingDelete.ids.length > 1 ? '选中的报告及其 PDF 将被永久删除，此操作无法撤销。' : '报告及其 PDF 将被永久删除，此操作无法撤销。'}</AlertDialogDescription>
            {pendingDelete?.batch ? <p className="report-delete-count"><RichMessage name="history-selected" count={pendingDelete.ids.length}>已选择 <strong>{pendingDelete.ids.length}</strong> 份报告</RichMessage></p>
              : <div className="report-delete-file"><FileText size={18} aria-hidden="true" /><p>{preserveText(pendingDelete?.filename || '')}</p></div>}
            {deleteError ? <p role="alert" className="report-delete-error">{deleteError}</p> : null}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>取消</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={deleting} onClick={event => { event.preventDefault(); void confirmDeleteReports(); }}>
              {deleting ? <LoaderCircle size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
              {deleting ? '正在删除…' : '确认删除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {isThirty ? <DetectionPageHeader showEyebrow={false} title="历史报告" description="查找已保存的检测报告，查看问题定位与修改建议。" /> : <>
      <PageHeader
        title={isThirty ? '历史报告' : '基础规则检测'}
        description={isThirty ? '查看已保存的 PDF 规则检测报告。' : '查看本人已保存的基础规则检测记录和报告。'}
      />
      <ModuleTabs
        ariaLabel={isThirty ? 'PDF 规则检测功能导航' : '基础规则检测功能导航'}
        items={[
          { label: '发起检测', to: checkPath, active: false },
          { label: '历史报告', to: historyPath, active: true, count: history.length + pdfReports.length },
        ]}
      />
      </>}
      {loading ? <LoadingState label="正在加载历史记录…" /> : null}
      {errorMessage ? <ErrorState message={errorMessage} /> : null}
      {!loading && !errorMessage && history.length === 0 && pdfReports.length === 0 ? (
        <EmptyState
          title="暂无检测记录"
          description={
            isThirty ? '规范性检测完成之后，检测报告将展示在这里。' : '完成一次基础规则检测后，报告会出现在这里。'
          }
        />
      ) : null}
      {pdfReports.length > 0 ? (
        <ReportHistoryTable
          key={historyPath}
          reports={pdfReports}
          historyPath={historyPath}
          selectedReportIds={selectedReportIds}
          onSelectionChange={setSelectedReportIds}
          deleting={deleting}
          onDelete={requestDeleteReports}
        />
      ) : null}
      {history.length > 0 ? (
        <section>
          <div className="mb-3">
            <h2 className="font-bold text-slate-900">文本规范检测记录</h2>
            <p className="mt-1 text-sm text-slate-500">历史文本检测报告保留原有的行号定位方式。</p>
          </div>
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-[#1F3760] text-white">
                <tr>
                  <th className="px-6 py-4">文档名称</th>
                  <th className="px-6 py-4">问题总数</th>
                  <th className="px-6 py-4">严重/一般/轻微</th>
                  <th className="px-6 py-4">检测时间</th>
                  <th className="px-6 py-4">操作</th>
                </tr>
              </thead>
              <tbody>
                {history.map((record, index) => (
                  <tr key={record.id} className={index % 2 === 0 ? 'bg-white' : 'bg-[#F5F9FC]'}>
                    <td className="px-6 py-6 font-bold text-slate-900">
                      📄 {preserveText(record.source_filename || '粘贴文本检测')}
                    </td>
                    <td className="px-6 py-6 font-black text-[#D62020]">{record.issues.length}</td>
                    <td className="px-6 py-6 text-slate-700">
                      {record.severity_counts.high || 0} / {record.severity_counts.medium || 0} /{' '}
                      {record.severity_counts.low || 0}
                    </td>
                    <td className="px-6 py-6 text-slate-700">{formatChinaDateTime(record.created_at)}</td>
                    <td className="px-6 py-6">
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="rounded-lg bg-[#1F3760] px-3 py-2 font-bold text-white"
                          type="button"
                          onClick={() => handleDownloadJson(record.id)}
                        >
                          报告下载
                        </button>
                        <LinkButton size="sm" to={`/normative-reports/${record.id}`}>
                          报告预览
                        </LinkButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default NormativeReportPage;
