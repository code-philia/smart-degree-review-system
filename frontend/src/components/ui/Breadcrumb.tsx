import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import {
  Breadcrumb as ShadcnBreadcrumb,
  BreadcrumbItem as ShadcnBreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '../shadcn/breadcrumb';

export type BreadcrumbItem = {
  label: string;
  to?: string;
};

function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  if (!items.length) {
    return null;
  }

  return (
    <ShadcnBreadcrumb aria-label="面包屑导航" className="mb-2">
      <BreadcrumbList className="text-xs font-medium">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;

          return (
            <Fragment key={`${item.label}-${index}`}>
              <ShadcnBreadcrumbItem>
                {item.to && !isLast ? (
                  <BreadcrumbLink asChild>
                    <Link to={item.to}>{item.label}</Link>
                  </BreadcrumbLink>
                ) : isLast ? (
                  <BreadcrumbPage className="font-medium">{item.label}</BreadcrumbPage>
                ) : (
                  <span>{item.label}</span>
                )}
              </ShadcnBreadcrumbItem>
              {!isLast ? <BreadcrumbSeparator /> : null}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </ShadcnBreadcrumb>
  );
}

export default Breadcrumb;
