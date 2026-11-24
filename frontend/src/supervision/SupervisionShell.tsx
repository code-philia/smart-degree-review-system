import { useEffect, useLayoutEffect, useState, type ReactNode } from 'react';
import { Files, MessageSquareText, ShieldCheck, Users, ThumbsDown, RefreshCw, LogOut, ChevronRight } from 'lucide-react';
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import { getLocale, setLocale } from '../i18n/locale';
import { OriginalTextContext } from '../i18n/jsx-runtime';
import { fetchSupervisionSummary, type SupervisionSummary } from '../api/supervision';
import './supervision.css';
import { SupervisionThemeButton } from './SupervisionThemeButton';

export function SupervisionChinese({ children }: { children: ReactNode }) {
  useLayoutEffect(() => {
    const before = getLocale();
    if (before !== 'zh') setLocale('zh');
    return () => { if (before !== 'zh') setLocale(before); };
  }, []);
  return <OriginalTextContext.Provider value={true}>{children}</OriginalTextContext.Provider>;
}

export function RequireSupervision() {
  const { status, user } = useAuthSession();
  if (status === 'loading') return <div className="sup-session-loading">正在验证管理员身份…</div>;
  if (!user) return <Navigate replace to="/admin/login" />;
  if (user.accessMode !== 'supervision') return <Navigate replace to="/paper-upload" />;
  return <Outlet />;
}

export type SupervisionOutlet = { refreshKey: number };
export default function SupervisionShell() {
  const { user, logout } = useAuthSession();
  const location = useLocation(), navigate = useNavigate();
  const [summary, setSummary] = useState<SupervisionSummary | null>(null);
  const [refreshKey, refresh] = useState(0);
  const [updating, setUpdating] = useState(false), [updated, setUpdated] = useState('');
  const [summaryError, setSummaryError] = useState(false), [leaving, setLeaving] = useState(false);
  const [exitError, setExitError] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setUpdating(true); setSummaryError(false);
    fetchSupervisionSummary(controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setSummary(value); setUpdated(new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' }).format(new Date()));
    }).catch(() => { if (!controller.signal.aborted) setSummaryError(true); })
      .finally(() => { if (!controller.signal.aborted) setUpdating(false); });
    return () => controller.abort();
  }, [refreshKey]);
  const feedback = location.pathname.toLowerCase().startsWith('/admin/feedback');
  async function exit() {
    setLeaving(true); setExitError(false);
    try { await logout(); navigate('/admin/login', { replace: true }); }
    catch { setExitError(true); }
    finally { setLeaving(false); }
  }
  const cards = [
    { name: '用户总数', value: summary?.users, icon: Users, tone: 'blue', note: '已注册的系统账号' },
    { name: '检测报告', value: summary?.reports, icon: Files, tone: 'teal', note: '全部用户的已存报告' },
    { name: '用户反馈', value: summary?.feedback, icon: MessageSquareText, tone: 'purple', note: '使用反馈与报告评价' },
    { name: '负面反馈', value: summary?.negative_feedback, icon: ThumbsDown, tone: 'amber', note: '点踩及低满意度反馈' },
  ];
  return <div className="supervision-app">
    <aside className="sup-sidebar">
      <NavLink to="/admin/reports" className="sup-brand"><img src="/login-schoolmark.jpg" alt="上海交通大学" /><span>智慧学位<strong>监管工作台</strong></span></NavLink>
      <p className="sup-nav-label">数据监管</p>
      <nav aria-label="监管导航">
        <NavLink to="/admin/reports" className={({ isActive }) => `sup-nav-item ${isActive ? 'active' : ''}`}><Files size={19} /><span>报告监管</span><ChevronRight size={15} /></NavLink>
        <NavLink to="/admin/feedback" className={({ isActive }) => `sup-nav-item ${isActive ? 'active' : ''}`}><MessageSquareText size={19} /><span>反馈监管</span><ChevronRight size={15} /></NavLink>
      </nav>
      <div className="sup-account"><span className="sup-avatar">管</span><div><strong>{user?.username}</strong><span>监管管理员</span></div><span className="sup-account-dot" title="已登录" /></div>
    </aside>
    <main className="sup-main">
      <header className="sup-topbar"><div className="sup-breadcrumb"><span>监管工作台</span><ChevronRight size={14} /><strong>{feedback ? '反馈监管' : '报告监管'}</strong></div>
        <div className="sup-header-actions"><SupervisionThemeButton />{exitError ? <span role="alert">退出失败，请重试</span> : null}<button onClick={() => void exit()} disabled={leaving} className="sup-text-button"><LogOut size={16} />{leaving ? '退出中…' : '退出登录'}</button></div>
      </header>
      <div className="sup-content">
        <div className="sup-intro"><div><p className="sup-eyebrow">管理概览</p><h2>每一份报告，每一条反馈</h2><p>汇集平台检测记录与用户评价，快速定位需要关注的内容。</p></div>
          <button className="sup-button sup-refresh" onClick={() => refresh(v => v + 1)} disabled={updating}><RefreshCw size={16} className={updating ? 'sup-spinning' : ''} />{updating ? '正在刷新' : '刷新数据'}</button>
        </div>
        <section className="sup-stats" aria-label="监管数据概览">{cards.map(card => <div className="sup-stat" key={card.name}><div className="sup-stat-top"><span>{card.name}</span><span className={`sup-stat-icon ${card.tone}`}><card.icon size={18} /></span></div><strong>{card.value?.toLocaleString('zh-CN') ?? '—'}</strong><p>{card.note}</p></div>)}</section>
        <div className="sup-update-status">{summaryError ? '概览暂未更新，请刷新重试' : updated ? `数据更新于 ${updated}（北京时间）` : '正在读取平台数据…'}</div>
        <Outlet context={{ refreshKey } satisfies SupervisionOutlet} />
        <footer className="sup-footer"><ShieldCheck size={13} />智慧学位 · 管理员监管工作台</footer>
      </div>
    </main>
  </div>;
}
