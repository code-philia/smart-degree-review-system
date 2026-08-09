import { ArrowLeft, FileSearch, MapPin } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  fetchPaperLintBuiltInCase,
  fetchPaperLintBuiltInCasePdf,
  fetchPaperLintBuiltInCases,
  type PaperLintBuiltInCase,
  type PaperLintBuiltInCaseSummary,
} from '../api/paperLint';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { PaperLintWorkspace } from '../components/paperLint/Workspace';
import { flattenPaperLintFindings } from '../components/paperLint/model';
import { Card, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader, StatusBadge } from '../components/ui';

function CaseCatalog() {
  const [cases, setCases] = useState<PaperLintBuiltInCaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const response = await fetchPaperLintBuiltInCases();
      setCases(response.cases);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '内置案例加载失败');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!cases) return <LoadingState label="正在加载内置审查案例…" />;
  if (cases.length === 0) return <EmptyState title="暂无内置审查案例" description="案例配置完成后会显示在这里。" />;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {cases.map((item) => (
        <Card
          key={item.id}
          title={item.title}
          description={item.description}
          actions={<StatusBadge tone="warning">{item.finding_count} 项问题</StatusBadge>}
        >
          <dl className="grid gap-3 text-sm sm:grid-cols-3">
            <div className="rounded-lg bg-slate-50 p-3">
              <dt className="text-xs font-semibold text-slate-500">审查规则</dt>
              <dd className="mt-1 font-bold text-slate-900">{item.rule.title}</dd>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <dt className="text-xs font-semibold text-slate-500">问题定位</dt>
              <dd className="mt-1 font-bold text-slate-900">第 {item.claim_page} 页</dd>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <dt className="text-xs font-semibold text-slate-500">关联定位</dt>
              <dd className="mt-1 font-bold text-slate-900">第 {item.evidence_page} 页</dd>
            </div>
          </dl>
          <div className="mt-5">
            <LinkButton to={`/review-cases/${item.id}`}>查看案例</LinkButton>
          </div>
        </Card>
      ))}
    </div>
  );
}

function CaseDetail({ caseId }: { caseId: string }) {
  const [reviewCase, setReviewCase] = useState<PaperLintBuiltInCase | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setReviewCase(null);
    setPdfFile(null);
    try {
      const [caseResponse, pdf] = await Promise.all([
        fetchPaperLintBuiltInCase(caseId),
        fetchPaperLintBuiltInCasePdf(caseId),
      ]);
      setReviewCase(caseResponse);
      setPdfFile(new File([pdf], caseResponse.pdf_filename, { type: 'application/pdf' }));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : '案例详情加载失败');
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const findings = useMemo(() => (reviewCase ? flattenPaperLintFindings(reviewCase.result) : []), [reviewCase]);

  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!reviewCase || !pdfFile) return <LoadingState label="正在加载案例 PDF 与审查结果…" />;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="内置审查案例"
        title={reviewCase.title}
        description={reviewCase.description}
        actions={
          <LinkButton to="/review-cases" variant="secondary">
            <ArrowLeft className="size-4" />
            返回案例列表
          </LinkButton>
        }
      />

      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <div className="flex items-center gap-3">
            <FileSearch className="size-5 text-brand-600" />
            <div>
              <p className="text-xs font-semibold text-slate-500">审查规则</p>
              <p className="mt-1 font-bold text-slate-900">{reviewCase.rule.title}</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <MapPin className="size-5 text-brand-600" />
            <div>
              <p className="text-xs font-semibold text-slate-500">问题定位</p>
              <p className="mt-1 font-bold text-slate-900">第 {reviewCase.claim_page} 页</p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <MapPin className="size-5 text-brand-600" />
            <div>
              <p className="text-xs font-semibold text-slate-500">关联定位</p>
              <p className="mt-1 font-bold text-slate-900">第 {reviewCase.evidence_page} 页</p>
            </div>
          </div>
        </Card>
      </div>

      <PaperLintWorkspace file={pdfFile} findings={findings} rules={[reviewCase.rule]} />
    </div>
  );
}

function BuiltInReviewCasesPage() {
  const { caseId } = useParams();
  const { status, user } = useAuthSession();

  if (status === 'loading') return <LoadingState label="正在恢复登录状态…" />;
  if (!user) {
    return (
      <div className="space-y-5">
        <PageHeader title="内置审查案例" description="查看带 PDF 原文定位的规则审查案例。" />
        <EmptyState
          title="请先登录后查看案例"
          description="内置审查案例面向已登录用户开放。"
          action={<LinkButton to="/auth">前往登录</LinkButton>}
        />
      </div>
    );
  }

  if (caseId) return <CaseDetail caseId={caseId} />;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="规则审查演示"
        title="内置审查案例"
        description="选择案例查看审查结论、修改建议，以及论点与论据在 PDF 原文中的跨页定位。"
      />
      <CaseCatalog />
    </div>
  );
}

export default BuiltInReviewCasesPage;
