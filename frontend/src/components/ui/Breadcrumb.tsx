import { Link } from 'react-router-dom';

export type BreadcrumbItem = {
  label: string;
  to?: string;
};

function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  if (!items.length) {
    return null;
  }

  return (
    <nav aria-label="面包屑导航" className="mb-2 flex flex-wrap items-center gap-1.5 text-xs font-semibold text-slate-500">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <span key={`${item.label}-${index}`} className="flex items-center gap-1.5">
            {item.to && !isLast ? (
              <Link className="hover:text-brand-600" to={item.to}>
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? 'text-slate-800' : ''}>{item.label}</span>
            )}
            {!isLast ? <span aria-hidden="true" className="text-slate-300">/</span> : null}
          </span>
        );
      })}
    </nav>
  );
}

export default Breadcrumb;
