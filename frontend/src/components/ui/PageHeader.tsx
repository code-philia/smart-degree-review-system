import type { ReactNode } from 'react';
import Breadcrumb, { type BreadcrumbItem } from './Breadcrumb';

type PageHeaderProps = {
  eyebrow?: ReactNode;
  title: string;
  description?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  actions?: ReactNode;
};

function PageHeader({ eyebrow, title, description, breadcrumbs, actions }: PageHeaderProps) {
  return (
    <header className="mb-6 space-y-3">
      {breadcrumbs ? <Breadcrumb items={breadcrumbs} /> : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {eyebrow ? <p className="mb-1 text-sm font-bold text-brand-500">{eyebrow}</p> : null}
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
          {description ? (
            <p className="mt-1.5 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}

export default PageHeader;
