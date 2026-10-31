import { ClipboardList, History, Sparkles } from 'lucide-react';
import { NavLink } from 'react-router-dom';

const destinations = [
  { to: '/thirty-rules-check', label: '论文上传', icon: ClipboardList },
  { to: '/semantic-rules-check', label: '摘要数值语义检测', icon: Sparkles },
  { to: '/thirty-rules-check/reports', label: '历史报告', icon: History },
];

export function DetectionPageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <header className="space-y-5">
      <div className="px-1 pt-1">
        <p className="mb-1.5 text-sm font-medium text-brand-700">论文规范性检测</p>
        <h1 className="text-2xl font-bold tracking-tight text-slate-950 sm:text-3xl">{title}</h1>
        {description ? <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p> : null}
      </div>
      <nav aria-label="论文检测页面切换" className="grid grid-cols-3 gap-1.5 rounded-2xl border border-slate-200/80 bg-white p-1.5 shadow-sm sm:gap-2 sm:p-2">
        {destinations.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end className={({ isActive }) =>
            `flex min-h-12 items-center justify-center gap-2 rounded-xl px-2 py-3 text-center text-sm font-semibold leading-5 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 motion-reduce:transition-none ${isActive ? 'bg-brand-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'}`
          }>
            <Icon className="hidden size-[18px] shrink-0 min-[500px]:block" aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
