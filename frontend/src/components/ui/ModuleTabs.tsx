import { Link } from 'react-router-dom';

export type ModuleTabItem = {
  label: string;
  to: string;
  active: boolean;
  count?: number;
};

type ModuleTabsProps = {
  ariaLabel: string;
  items: ModuleTabItem[];
};

function ModuleTabs({ ariaLabel, items }: ModuleTabsProps) {
  return (
    <nav className="mb-6 flex flex-wrap items-center gap-1 border-b border-slate-200" aria-label={ariaLabel}>
      {items.map((item) => (
        <Link
          key={item.to}
          aria-current={item.active ? 'page' : undefined}
          className={`flex min-h-10 items-center justify-center gap-2 border-b-2 px-4 py-2 text-sm font-bold transition sm:px-5 ${
            item.active
              ? 'border-brand-500 text-brand-700'
              : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-900'
          }`}
          to={item.to}
        >
          <span>{item.label}</span>
          {typeof item.count === 'number' ? (
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${
                item.active ? 'bg-brand-50 text-brand-700' : 'bg-slate-100 text-slate-500'
              }`}
            >
              {item.count}
            </span>
          ) : null}
        </Link>
      ))}
    </nav>
  );
}

export default ModuleTabs;
