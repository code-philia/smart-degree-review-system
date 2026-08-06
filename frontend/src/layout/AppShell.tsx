import { useEffect, useMemo, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthSession } from '../auth/AuthSessionProvider';
import {
  findNavItemLabel,
  getVisibleNavGroups,
  roleLabels,
  roleScopeLabels,
  type NavGroup,
} from '../nav/navigationConfig';

const PRODUCT_NAME = '智慧学位 AI 评阅辅助系统';
const PRODUCT_TAGLINE = '试点验证版 V0.9';

function SidebarGroup({
  group,
  expanded,
  onToggle,
  onNavigate,
}: {
  group: NavGroup;
  expanded: boolean;
  onToggle: () => void;
  onNavigate: () => void;
}) {
  return (
    <div className="border-b border-white/5 py-2 last:border-none">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-2 text-xs font-bold uppercase tracking-wide text-blue-200/70 hover:text-white"
        aria-expanded={expanded}
      >
        <span>{group.title}</span>
        <span aria-hidden="true" className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>
          ›
        </span>
      </button>
      {expanded ? (
        <ul className="mt-1 space-y-0.5 px-2">
          {group.items.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                onClick={onNavigate}
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2 text-sm font-semibold transition ${
                    isActive
                      ? 'bg-brand-500 text-white shadow-sm'
                      : 'text-blue-100/85 hover:bg-white/10 hover:text-white'
                  }`
                }
                end
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function AppShell() {
  const { status, user, logout } = useAuthSession();
  const location = useLocation();
  const navigate = useNavigate();
  const role = user?.role ?? null;
  const visibleGroups = useMemo(() => getVisibleNavGroups(role), [role]);
  const currentNavInfo = useMemo(() => findNavItemLabel(location.pathname), [location.pathname]);

  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(() => new Set(visibleGroups.map((g) => g.key)));
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    setExpandedKeys((current) => {
      const activeGroup = visibleGroups.find((group) => group.items.some((item) => currentNavInfo?.label === item.label && currentNavInfo.groupTitle === group.title));
      if (!activeGroup || current.has(activeGroup.key)) {
        return current;
      }
      const next = new Set(current);
      next.add(activeGroup.key);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  function toggleGroup(key: string) {
    setExpandedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  async function handleLogout() {
    await logout();
    navigate('/auth');
  }

  const pageTitle = location.pathname === '/' ? '工作台' : currentNavInfo?.label || '';
  const breadcrumbTrail = [
    '首页',
    currentNavInfo?.groupTitle,
    currentNavInfo?.label,
  ].filter(Boolean) as string[];

  return (
    <div className="min-h-screen bg-slate-100">
      <div className="flex min-h-screen">
        <aside
          className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col bg-brand-900 transition-transform lg:static lg:translate-x-0 ${
            mobileNavOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <Link to="/" className="flex items-center gap-3 border-b border-white/10 px-5 py-5" onClick={() => setMobileNavOpen(false)}>
            <img src="/brand-mark.jpg" alt="" className="h-10 w-10 rounded-full object-cover ring-2 ring-white/20" />
            <div className="min-w-0">
              <p className="truncate text-sm font-black leading-tight text-white">{PRODUCT_NAME}</p>
              <p className="mt-0.5 text-xs font-semibold text-blue-200/70">{PRODUCT_TAGLINE}</p>
            </div>
          </Link>

          <nav className="flex-1 overflow-y-auto py-2" aria-label="主导航">
            {visibleGroups.map((group) => (
              <SidebarGroup
                key={group.key}
                group={group}
                expanded={expandedKeys.has(group.key)}
                onToggle={() => toggleGroup(group.key)}
                onNavigate={() => setMobileNavOpen(false)}
              />
            ))}
          </nav>

          {!user && status !== 'loading' ? (
            <div className="border-t border-white/10 p-4">
              <Link
                to="/auth"
                className="flex h-10 items-center justify-center rounded-lg bg-white text-sm font-bold text-brand-700"
              >
                登录系统
              </Link>
            </div>
          ) : null}
        </aside>

        {mobileNavOpen ? (
          <button
            type="button"
            aria-label="关闭导航菜单"
            className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden"
            onClick={() => setMobileNavOpen(false)}
          />
        ) : null}

        <div className="flex min-h-screen flex-1 flex-col lg:pl-0">
          <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                className="rounded-lg border border-slate-200 p-2 text-slate-500 lg:hidden"
                onClick={() => setMobileNavOpen(true)}
                aria-label="打开导航菜单"
              >
                <span aria-hidden="true">☰</span>
              </button>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-slate-400">{breadcrumbTrail.join(' / ')}</p>
                <h1 className="truncate text-lg font-black text-slate-900">{pageTitle}</h1>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-3">
              {status === 'loading' ? (
                <span className="text-xs font-semibold text-slate-400">正在恢复会话…</span>
              ) : user ? (
                <>
                  <div className="hidden text-right sm:block">
                    <p className="text-sm font-bold text-slate-800">{user.username}</p>
                    <p className="text-xs font-semibold text-slate-400">
                      {roleLabels[user.role]} · {roleScopeLabels[user.role]}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleLogout()}
                    className="h-9 rounded-lg border border-slate-200 px-3 text-sm font-bold text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                  >
                    退出
                  </button>
                </>
              ) : (
                <Link
                  to="/auth"
                  className="h-9 rounded-lg bg-brand-500 px-4 text-sm font-bold leading-9 text-white"
                >
                  登录系统
                </Link>
              )}
            </div>
          </header>

          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
            <div className="mx-auto w-full max-w-[1280px]">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

export default AppShell;
