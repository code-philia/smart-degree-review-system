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
    <nav
      className="mb-6 flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm"
      aria-label={ariaLabel}
    >
      {items.map((item) => (
        <Link
          key={item.to}
          aria-current={item.active ? 'page' : undefined}
          className={`flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-black transition sm:flex-none sm:min-w-40 ${
            item.active ? 'bg-[#1F3F63] text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100 hover:text-[#1F3F63]'
          }`}
          to={item.to}
        >
          <span>{item.label}</span>
          {typeof item.count === 'number' ? (
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${
                item.active ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'
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
