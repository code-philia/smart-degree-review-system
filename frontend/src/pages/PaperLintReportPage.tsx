import { FileCheck2, FileText } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  fetchPaperLintReport,
  fetchPaperLintReportPdf,
  fetchReviewPilotPaperLintRules,
  type PaperLintRule,
  type PaperLintRunResponse,
} from '../api/paperLint';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { flattenPaperLintFindings } from '../components/paperLint/model';
import { Card, ErrorState, LoadingState, PageHeader, StatusBadge } from '../components/ui';

function PaperLintReportPage() {
  const { reportId } = useParams();
  const [report, setReport] = useState<PaperLintRunResponse | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [rules, setRules] = useState<PaperLintRule[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reportId) return;
    let cancelled = false;
    Promise.all([
      fetchPaperLintReport(reportId),
      fetchPaperLintReportPdf(reportId),
      fetchReviewPilotPaperLintRules().catch(() => null),
    ])
      .then(([nextReport, blob, catalog]) => {
        if (cancelled) return;
        setReport(nextReport);
        setFile(new File([blob], nextReport.source_filename, { type: 'application/pdf' }));
        setRules(catalog?.rules || []);
      })
      .catch((loadError) => !cancelled && setError(loadError instanceof Error ? loadError.message : '报告加载失败'));
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  const findings = useMemo(() => (report ? flattenPaperLintFindings(report.result) : []), [report]);
  if (error) return <ErrorState title="报告暂不可用" message={error} />;
  if (!report || !file) return <LoadingState label="正在加载检测报告和原文定位…" />;
  const { summary } = report.result;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="已完成检测"
        title={report.result.paper_title || report.source_filename}
        description={`检测于 ${new Date(report.created_at).toLocaleString('zh-CN')} 完成。请优先处理严重和警告问题。`}
        breadcrumbs={[
          { label: '首页', to: '/' },
          { label: '基础规则检测', to: '/normative-check' },
          { label: '历史报告', to: '/normative-reports' },
          { label: '检测报告' },
        ]}
        actions={
          <Link className="text-sm font-semibold text-brand-700 hover:underline" to="/normative-reports">
            返回历史报告
          </Link>
        }
      />
      <Card
        title="检测结论"
        description="以下结论用于修改前自查，不替代导师或学院的正式审核。"
        actions={
          <StatusBadge
            tone={summary.error_finding_count ? 'danger' : summary.warning_finding_count ? 'warning' : 'success'}
          >
            {summary.finding_count ? `待处理 ${summary.finding_count} 项` : '基础检查通过'}
          </StatusBadge>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {[
            ['检查项', summary.rule_count],
            ['严重', summary.error_finding_count],
            ['警告', summary.warning_finding_count],
            ['提示', summary.info_finding_count],
            ['问题总数', summary.finding_count],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs text-slate-500">{label}</p>
              <p className="mt-1 text-2xl font-black text-slate-900">{value}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 flex items-center gap-2 text-sm text-slate-600">
          <FileCheck2 className="size-4 text-brand-600" />
          规则版本：{report.summary.ruleset_label || '当前发布版本'} · 原文可定位问题{' '}
          {findings.filter((item) => item.finding.location || item.finding.anchors?.length).length} 项
        </p>
      </Card>
      <div className="flex items-center gap-2">
        <FileText className="size-5 text-brand-600" />
        <h2 className="text-lg font-black text-slate-900">逐项处理问题</h2>
      </div>
      <PaperLintWorkspace file={file} findings={findings} rules={rules} />
    </div>
  );
}

export default PaperLintReportPage;
