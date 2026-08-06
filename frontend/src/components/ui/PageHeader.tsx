import type { ReactNode } from 'react';
import Breadcrumb, { type BreadcrumbItem } from './Breadcrumb';

type PageHeaderProps = {
  title: string;
  description?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  actions?: ReactNode;
};

function PageHeader({ title, description, breadcrumbs, actions }: PageHeaderProps) {
  return (
    <header className="mb-6">
      {breadcrumbs ? <Breadcrumb items={breadcrumbs} /> : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900">{title}</h1>
          {description ? <p className="mt-1.5 max-w-3xl text-sm leading-6 text-slate-500">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}

export default PageHeader;
