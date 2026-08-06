import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import RoleAwareHomeMenu from '../auth/RoleAwareHomeMenu';
import type { AuthRole } from '../api/authSession';
import { roleLabels, roleScopeLabels } from '../nav/navigationConfig';
import { Card, EmptyState, ErrorState, LoadingState, LinkButton, StatusBadge } from '../components/ui';
import { fetchStudentReportResults, type StudentReportResultSummary } from '../api/reportStudentResults';
import { fetchSupervisorReviewQueue, type SupervisorReviewQueueItem } from '../api/reportSupervisorQueue';
import {
  fetchDetectionLedgerFilteredStats,
  fetchDetectionLedgerRecords,
  type DetectionLedgerFilteredStats,
  type DetectionLedgerRecord,
} from '../api/normativeRules';

type QuickAction = { label: string; description: string; to: string };

const QUICK_ACTIONS: Record<AuthRole, QuickAction[]> = {
  STUDENT: [
    { label: '规范性检测', description: '检查章节、标点和参考文献问题', to: '/normative-check' },
    { label: '论文相似度检测', description: '与试点样本库比对相似片段', to: '/duplication-detect' },
    { label: '创新性量表评估', description: '五维度量表评估创新参考分', to: '/innovation-assessment' },
    { label: '论文润色', description: '生成整篇或局部改写建议', to: '/whole-polish' },
    { label: '提交报告给导师', description: '推送已完成报告给导师批阅', to: '/student-report-submissions' },
    { label: '查看批阅结果', description: '查看导师反馈和历史轮次', to: '/student-report-results' },
  ],
  SUPERVISOR: [
    { label: '导师待批阅中心', description: '处理分配给本人的待办任务', to: '/supervisor-review-queue' },
    { label: '检测记录台账', description: '查看所指导学生的检测记录', to: '/ledger-records' },
    { label: '检测统计', description: '查看数量趋势和类型分布', to: '/ledger-stats' },
    { label: '群体质量仪表盘', description: '查看学生论文质量指标', to: '/quality-dashboard' },
  ],
  COLLEGE_ADMIN: [
    { label: '学院规则配置', description: '维护本学院规则覆盖', to: '/rule-config' },
    { label: '检测记录台账', description: '查看本学院检测记录', to: '/ledger-records' },
    { label: '检测统计', description: '按类型和时间筛选统计', to: '/ledger-stats' },
    { label: '群体质量仪表盘', description: '查看学院质量指标分布', to: '/quality-dashboard' },
  ],
  SCHOOL_ADMIN: [
    { label: '学校规则配置', description: '维护全校默认规则', to: '/rule-config' },
    { label: '比对样本库', description: '维护相似度检测样本', to: '/duplication-corpus' },
    { label: '检测记录台账', description: '查看全校检测记录', to: '/ledger-records' },
    { label: '群体质量仪表盘', description: '查看全校质量指标汇总', to: '/quality-dashboard' },
  ],
};

function QuickActionGrid({ actions }: { actions: QuickAction[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {actions.map((action) => (
        <Link
          key={action.to}
          to={action.to}
          className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-brand-500 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <p className="font-bold text-slate-900">{action.label}</p>
          <p className="mt-1.5 text-sm leading-6 text-slate-500">{action.description}</p>
        </Link>
      ))}
    </div>
  );
}

function StudentTodoPanel() {
  const [results, setResults] = useState<StudentReportResultSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchStudentReportResults({});
      setResults(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : '待处理事项加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) return <LoadingState compact label="正在加载待处理事项…" />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!results || results.length === 0) {
    return <EmptyState title="暂无提交记录" description="完成一次检测或评估后，可在此提交报告给导师批阅。" action={<LinkButton to="/student-report-submissions" size="sm">去提交报告</LinkButton>} />;
  }

  const awaitingView = results.filter((item) => item.status === 'review_completed_feedback');
  const recent = [...results].sort((a, b) => (a.submitted_at < b.submitted_at ? 1 : -1)).slice(0, 5);

  return (
    <div>
      <p className="text-sm leading-6 text-slate-600">
        {awaitingView.length > 0 ? (
          <>有 <span className="font-black text-brand-600">{awaitingView.length}</span> 份报告已收到导师反馈，尚未查看。</>
        ) : (
          '当前没有待查看的导师反馈。'
        )}
      </p>
      <ul className="mt-4 divide-y divide-slate-100">
        {recent.map((item) => (
          <li key={item.submission_id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
            <span className="text-slate-600">提交批次 {item.batch_id.slice(0, 8)} · {item.submitted_at}</span>
            <div className="flex items-center gap-2">
              <StatusBadge tone={item.status === 'review_completed_feedback' ? 'info' : item.status === 'student_viewed_feedback' ? 'success' : 'neutral'}>
                {item.status === 'submitted_pending_review' ? '待批阅' : item.status === 'review_completed_feedback' ? '已反馈' : '已查看'}
              </StatusBadge>
              <Link className="font-semibold text-brand-600 hover:underline" to={`/student-report-results/${item.submission_id}`}>
                查看
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SupervisorTodoPanel() {
  const [records, setRecords] = useState<SupervisorReviewQueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchSupervisorReviewQueue({ status: 'pending' });
      setRecords(response.records);
    } catch (err) {
      setError(err instanceof Error ? err.message : '待批阅任务加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) return <LoadingState compact label="正在加载待批阅任务…" />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!records || records.length === 0) {
    return <EmptyState title="当前没有待批阅任务" description="学生提交报告后，待办会出现在这里。" />;
  }

  return (
    <div>
      <p className="text-sm leading-6 text-slate-600">
        共有 <span className="font-black text-brand-600">{records.length}</span> 条待批阅任务。
      </p>
      <ul className="mt-4 divide-y divide-slate-100">
        {records.slice(0, 5).map((item) => (
          <li key={item.todo_id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
            <span className="truncate text-slate-600">{item.title || item.submission_id} · {item.created_at}</span>
            <Link className="shrink-0 font-semibold text-brand-600 hover:underline" to={`/supervisor-review-queue/${item.submission_id}`}>
              去批阅
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AdminOverviewPanel({ role }: { role: 'COLLEGE_ADMIN' | 'SCHOOL_ADMIN' }) {
  const [stats, setStats] = useState<DetectionLedgerFilteredStats | null>(null);
  const [records, setRecords] = useState<DetectionLedgerRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [statsResponse, recordsResponse] = await Promise.all([
        fetchDetectionLedgerFilteredStats({}),
        fetchDetectionLedgerRecords({}),
      ]);
      setStats(statsResponse);
      setRecords(recordsResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : '统计数据加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) return <LoadingState compact label="正在加载统计数据…" />;
  if (error) return <ErrorState message={error} onRetry={() => void load()} />;
  if (!stats || !records) return null;

  return (
    <div>
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg bg-brand-50 p-3 text-center">
          <p className="text-2xl font-black text-brand-700">{stats.total_records}</p>
          <p className="mt-1 text-xs font-semibold text-slate-500">{role === 'SCHOOL_ADMIN' ? '全校记录数' : '学院记录数'}</p>
        </div>
        <div className="rounded-lg bg-brand-50 p-3 text-center">
          <p className="text-2xl font-black text-brand-700">{stats.total_students}</p>
          <p className="mt-1 text-xs font-semibold text-slate-500">覆盖学生数</p>
        </div>
        <div className="rounded-lg bg-brand-50 p-3 text-center">
          <p className="text-2xl font-black text-brand-700">{stats.today_count}</p>
          <p className="mt-1 text-xs font-semibold text-slate-500">今日新增</p>
        </div>
      </div>

      {records.length === 0 ? (
        <div className="mt-4">
          <EmptyState title="暂无检测记录" description="学生完成检测后，记录会出现在台账中。" />
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-slate-100">
          {records.slice(0, 5).map((record) => (
            <li key={record.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
              <span className="min-w-0 flex-1 truncate text-slate-600">{record.thesis_title || record.student_name}</span>
              <StatusBadge tone="neutral">{record.detection_type_label}</StatusBadge>
              <Link className="shrink-0 font-semibold text-brand-600 hover:underline" to={record.detail_url}>
                详情
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AnonymousLanding() {
  return (
    <div className="mx-auto max-w-3xl py-10 text-center">
      <p className="text-sm font-bold text-brand-500">试点验证版 V0.9</p>
      <h1 className="mt-3 text-3xl font-black text-slate-900 md:text-4xl">智慧学位 AI 评阅辅助系统</h1>
      <p className="mx-auto mt-4 max-w-xl text-base leading-7 text-slate-600">
        面向学生、导师、学院管理人员和学校管理人员，提供规范性检测、相似度检测、创新性评估、辅助评阅、论文润色和师生报告流转等一体化功能。
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <LinkButton to="/auth" size="lg">
          登录系统
        </LinkButton>
        <Link className="inline-flex h-11 items-center rounded-lg border border-slate-300 px-5 text-sm font-bold text-slate-600" to="/about">
          了解系统说明
        </Link>
      </div>
    </div>
  );
}

function HomePage() {
  const { status, user } = useAuthSession();

  if (status === 'loading') {
    return <LoadingState label="正在恢复登录状态…" />;
  }

  if (!user) {
    return <AnonymousLanding />;
  }

  const quickActions = QUICK_ACTIONS[user.role];

  return (
    <div>
      <header className="mb-6">
        <p className="text-sm font-bold text-brand-500">{roleLabels[user.role]}工作台</p>
        <h1 className="mt-1 text-2xl font-black text-slate-900">欢迎回来，{user.username}</h1>
        <p className="mt-1.5 text-sm text-slate-500">
          当前身份：{roleLabels[user.role]} · 数据范围：{roleScopeLabels[user.role]}
        </p>
      </header>

      <div className="mb-6">
        <RoleAwareHomeMenu />
      </div>

      <section className="mb-6">
        <h2 className="mb-3 text-base font-bold text-slate-800">常用操作</h2>
        <QuickActionGrid actions={quickActions} />
      </section>

      <div className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
        <Card title={user.role === 'STUDENT' ? '待处理事项' : user.role === 'SUPERVISOR' ? '待批阅任务' : '数据概览'}>
          {user.role === 'STUDENT' ? <StudentTodoPanel /> : null}
          {user.role === 'SUPERVISOR' ? <SupervisorTodoPanel /> : null}
          {(user.role === 'COLLEGE_ADMIN' || user.role === 'SCHOOL_ADMIN') ? <AdminOverviewPanel role={user.role} /> : null}
        </Card>

        <Card title="能力概览" actions={<Link className="text-sm font-bold text-brand-600 hover:underline" to="/about">系统说明</Link>}>
          <ul className="space-y-2.5 text-sm leading-6 text-slate-600">
            <li>规范性检测按当前生效规则定位问题到具体行列。</li>
            <li>相似度检测覆盖试点样本库，给出相似片段和风险提示。</li>
            <li>创新性评估和辅助评阅使用可解释规则与公式计算参考分。</li>
            <li>检测台账与质量看板按角色数据范围呈现。</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}

export default HomePage;
